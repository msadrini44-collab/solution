"""
AntiDeepfake AI — FastAPI application.

Endpoints
---------
* ``POST /api/auth/register``      — create an account, returns JWT + API key.
* ``POST /api/auth/login``         — log in, returns JWT + API key.
* ``POST /api/detect``             — upload image/video, run detection pipeline.
* ``GET  /api/results/{scan_id}``  — fetch results for a completed scan.
* ``GET  /api/history``            — scan history for the authenticated user.
* ``GET  /api/health``             — liveness probe.
* ``GET  /docs``                   — interactive Swagger UI (provided by FastAPI).

Scans run in a background task; clients poll ``/api/results/{scan_id}`` until
``status == "done"``. Anonymous scans are allowed (for the sales-page demo) but
are associated with the user when credentials are supplied.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from pathlib import Path
from typing import Optional

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from . import auth, config, pipeline
from .database import Scan, User, get_session, init_db
from .schemas import (
    AuthResponse,
    DetectResponse,
    HistoryResponse,
    LoginRequest,
    RegisterRequest,
    ScanSummary,
)

app = FastAPI(
    title="AntiDeepfake AI",
    description="Multi-method deepfake and synthetic-media detection engine.",
    version="1.0.0",
)

# CORS defaults to open for local/static demos. In production set
# ADF_CORS_ORIGINS="https://antideepfakeai.com,https://www.antideepfakeai.com".
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ALLOW_ORIGINS,
    allow_credentials=config.CORS_ALLOW_ORIGINS != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# Ensure tables exist as soon as the module is imported (covers ASGI servers,
# Celery workers, and test clients that don't fire startup events).
init_db()


@app.on_event("startup")
def _startup() -> None:
    init_db()


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
@app.post("/api/auth/register", response_model=AuthResponse, tags=["auth"])
def register(req: RegisterRequest, db: Session = Depends(get_session)):
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    user = User(
        email=req.email,
        password_hash=auth.hash_password(req.password),
        api_key=auth.generate_api_key(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return AuthResponse(
        access_token=auth.create_access_token(user),
        api_key=user.api_key,
        email=user.email,
    )


@app.post("/api/auth/login", response_model=AuthResponse, tags=["auth"])
def login(req: LoginRequest, db: Session = Depends(get_session)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user or not auth.verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return AuthResponse(
        access_token=auth.create_access_token(user),
        api_key=user.api_key,
        email=user.email,
    )


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #
def _process_scan(scan_id: str, file_path: str, filename: str) -> None:
    """Background worker: run the pipeline and persist results."""
    from .database import SessionLocal

    db = SessionLocal()
    try:
        scan = db.query(Scan).filter(Scan.scan_id == scan_id).first()
        if scan is None:
            return
        try:
            result = pipeline.run_pipeline(scan_id, file_path, filename)
            scan.status = "done"
            scan.score = result["score"]
            scan.verdict = result["verdict"]
            scan.media_type = result["media_type"]
            scan.result_json = json.dumps(result)
        except Exception as exc:  # mark errored but keep the record
            scan.status = "error"
            scan.result_json = json.dumps({"error": str(exc)})
        db.commit()
    finally:
        db.close()


def _scan_response(scan: Scan, result: dict, filename: Optional[str] = None) -> DetectResponse:
    return DetectResponse(
        scan_id=scan.scan_id,
        status=scan.status,
        filename=filename or scan.filename,
        media_type=scan.media_type,
        score=result.get("score"),
        fake_probability=result.get("fake_probability"),
        verdict=result.get("verdict"),
        verdict_confidence=result.get("verdict_confidence"),
        detectors_used=result.get("detectors_used"),
        num_detectors_contributing=result.get("num_detectors_contributing"),
        evidence_grade=result.get("evidence_grade"),
        risk_band=result.get("risk_band"),
        decision_notes=result.get("decision_notes"),
        recommended_action=result.get("recommended_action"),
        premium_signals_available=result.get("premium_signals_available"),
        file_sha256=result.get("file_sha256"),
        breakdown=result.get("breakdown"),
        processing_time_sec=result.get("processing_time_sec"),
        artifacts=result.get("artifacts"),
    )


@app.post("/api/detect", response_model=DetectResponse, tags=["detection"])
async def detect(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    sync: bool = False,
    db: Session = Depends(get_session),
    user: Optional[User] = Depends(auth.get_optional_user),
):
    """Accept an upload and start the detection pipeline.

    Pass ``?sync=true`` to run synchronously and get results in the response
    (handy for the API/CLI); otherwise poll ``/api/results/{scan_id}``.
    """
    filename = file.filename or "upload"
    media_type = pipeline.media_type_for(filename)
    if media_type is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type. Supported: "
                f"images {config.SUPPORTED_IMAGE_FORMATS}, "
                f"videos {config.SUPPORTED_VIDEO_FORMATS}."
            ),
        )

    scan_id = str(uuid.uuid4())
    dest = config.UPLOAD_DIR / f"{scan_id}_{Path(filename).name}"

    # Stream to disk while enforcing the size limit.
    size = 0
    with dest.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > config.MAX_UPLOAD_BYTES:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds {config.MAX_UPLOAD_MB} MB limit.",
                )
            out.write(chunk)

    scan = Scan(
        scan_id=scan_id,
        user_id=user.id if user else None,
        filename=filename,
        media_type=media_type,
        status="processing",
    )
    db.add(scan)
    db.commit()

    if sync:
        await asyncio.to_thread(_process_scan, scan_id, str(dest), filename)
        db.refresh(scan)
        result = scan.result() or {}
        return _scan_response(scan, result, filename)

    background_tasks.add_task(_process_scan, scan_id, str(dest), filename)
    return DetectResponse(
        scan_id=scan_id,
        status="processing",
        filename=filename,
        media_type=media_type,
    )


@app.get("/api/results/{scan_id}", response_model=DetectResponse, tags=["detection"])
def get_results(scan_id: str, db: Session = Depends(get_session)):
    scan = db.query(Scan).filter(Scan.scan_id == scan_id).first()
    if scan is None:
        raise HTTPException(status_code=404, detail="Scan not found")
    result = scan.result() or {}
    if scan.status == "error":
        raise HTTPException(status_code=500, detail=result.get("error", "Processing failed"))
    return _scan_response(scan, result)


@app.get("/api/history", response_model=HistoryResponse, tags=["detection"])
def history(
    db: Session = Depends(get_session),
    user: User = Depends(auth.get_current_user),
):
    scans = (
        db.query(Scan)
        .filter(Scan.user_id == user.id)
        .order_by(Scan.created_at.desc())
        .limit(200)
        .all()
    )
    return HistoryResponse(
        scans=[
            ScanSummary(
                scan_id=s.scan_id,
                filename=s.filename,
                media_type=s.media_type,
                status=s.status,
                score=s.score,
                verdict=s.verdict,
                created_at=s.created_at.isoformat() if s.created_at else "",
            )
            for s in scans
        ]
    )


@app.get("/api/health", tags=["meta"])
def health():
    return {
        "status": "ok",
        "service": "antideepfake-ai",
        "version": app.version,
        "premium_provider_count": len(config.PREMIUM_PROVIDERS) if config.ENABLE_PAID_APIS else 0,
    }


@app.get("/", tags=["meta"])
def root():
    return {
        "service": "AntiDeepfake AI",
        "docs": "/docs",
        "detectors": list(config.DETECTOR_WEIGHTS.keys()),
    }

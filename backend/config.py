"""
Central configuration for the AntiDeepfake AI detection engine.

Values can be overridden via environment variables so the same image can run
locally (developer laptop), in docker-compose, or in production without code
changes. Optional paid third-party APIs are disabled unless their keys are
provided.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, TypedDict


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_list(name: str, default: List[str]) -> List[str]:
    raw = os.getenv(name)
    if not raw:
        return default
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


class PremiumProvider(TypedDict):
    name: str
    url: str
    api_key_env: str


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
BASE_DIR = Path(__file__).resolve().parent
# Directory where pretrained model weights are downloaded/cached.
MODEL_DIR = Path(os.getenv("ADF_MODEL_DIR", str(BASE_DIR / "weights")))
# Directory where uploaded files and generated reports are stored.
DATA_DIR = Path(os.getenv("ADF_DATA_DIR", str(BASE_DIR / "data")))
UPLOAD_DIR = DATA_DIR / "uploads"
REPORT_DIR = DATA_DIR / "reports"

for _d in (MODEL_DIR, DATA_DIR, UPLOAD_DIR, REPORT_DIR):
    _d.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------- #
# Database / queue
# --------------------------------------------------------------------------- #
# Defaults to a local SQLite file so the API runs with zero external services.
# docker-compose overrides this to point at PostgreSQL.
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'antideepfake.db'}")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
JWT_SECRET = os.getenv("ADF_JWT_SECRET", "change-me-in-production-please")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = _env_int("ADF_JWT_EXPIRE_MINUTES", 60 * 24 * 7)  # 1 week


# --------------------------------------------------------------------------- #
# Uploads / supported formats
# --------------------------------------------------------------------------- #
MAX_UPLOAD_MB = _env_int("ADF_MAX_UPLOAD_MB", 100)
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

SUPPORTED_IMAGE_FORMATS = _env_list(
    "ADF_IMAGE_FORMATS", ["jpg", "jpeg", "png", "webp", "bmp"]
)
SUPPORTED_VIDEO_FORMATS = _env_list(
    "ADF_VIDEO_FORMATS", ["mp4", "mov", "avi", "mkv", "webm"]
)


# --------------------------------------------------------------------------- #
# Video processing
# --------------------------------------------------------------------------- #
# Sample one frame every N frames to keep processing time reasonable.
VIDEO_FRAME_SAMPLE_RATE = _env_int("ADF_FRAME_SAMPLE_RATE", 10)
# Hard cap on number of frames analysed per video.
VIDEO_MAX_FRAMES = _env_int("ADF_VIDEO_MAX_FRAMES", 60)


# --------------------------------------------------------------------------- #
# Ensemble scoring weights
# --------------------------------------------------------------------------- #
# Each detector contributes a "fakeness" probability in [0, 1]. The ensemble is
# a weighted average over the detectors that apply to a given file. Weights do
# not need to sum to 1 — they are normalised over the applicable detectors.
DETECTOR_WEIGHTS = {
    "face_forgery": float(os.getenv("ADF_W_FACE_FORGERY", 0.22)),
    "frequency_analysis": float(os.getenv("ADF_W_FREQUENCY", 0.12)),
    "liveness": float(os.getenv("ADF_W_LIVENESS", 0.10)),
    "temporal_analysis": float(os.getenv("ADF_W_TEMPORAL", 0.12)),
    "audio_sync": float(os.getenv("ADF_W_AUDIO_SYNC", 0.10)),
    "gan_fingerprint": float(os.getenv("ADF_W_GAN", 0.14)),
    "metadata_forensics": float(os.getenv("ADF_W_METADATA", 0.08)),
    "pixel_forensics": float(os.getenv("ADF_W_PIXEL", 0.12)),
    "premium_consensus": float(os.getenv("ADF_W_PREMIUM", 0.18)),
}

# Verdict thresholds applied to the final 0-100 confidence-of-authenticity score
# (100 = almost certainly real, 0 = almost certainly fake).
VERDICT_THRESHOLDS = [
    (80, "REAL"),
    (60, "LIKELY REAL"),
    (40, "SUSPICIOUS"),
    (20, "LIKELY FAKE"),
    (0, "FAKE"),
]


# --------------------------------------------------------------------------- #
# API / CORS
# --------------------------------------------------------------------------- #
CORS_ORIGINS = os.getenv("ADF_CORS_ORIGINS", "*")
CORS_ALLOW_ORIGINS = (
    ["*"]
    if CORS_ORIGINS.strip() == "*"
    else [origin.strip().rstrip("/") for origin in CORS_ORIGINS.split(",") if origin.strip()]
)


# --------------------------------------------------------------------------- #
# Optional premium/provider detectors (disabled unless explicitly configured)
# --------------------------------------------------------------------------- #
ENABLE_PAID_APIS = _env_bool("ADF_ENABLE_PAID_APIS", False)


def _premium_providers() -> List[PremiumProvider]:
    raw = os.getenv("ADF_PREMIUM_DETECTORS", "").strip()
    if not raw:
        return []
    try:
        providers = json.loads(raw)
    except json.JSONDecodeError:
        return []
    parsed: List[PremiumProvider] = []
    if not isinstance(providers, list):
        return parsed
    for item in providers:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        url = str(item.get("url", "")).strip()
        api_key_env = str(item.get("api_key_env", "")).strip()
        if name and url and api_key_env:
            parsed.append({"name": name, "url": url, "api_key_env": api_key_env})
    return parsed


PREMIUM_PROVIDERS = _premium_providers()


# --------------------------------------------------------------------------- #
# Runtime
# --------------------------------------------------------------------------- #
# When True, detectors that require unavailable heavy dependencies (torch,
# mediapipe, dlib, librosa) fall back to lightweight heuristic implementations
# instead of raising. This keeps the product demoable without a multi-GB
# model download. Set ADF_STRICT_MODELS=1 to require real weights.
STRICT_MODELS = _env_bool("ADF_STRICT_MODELS", False)

DEVICE = os.getenv("ADF_DEVICE", "cpu")

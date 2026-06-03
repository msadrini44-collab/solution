"""
Detection pipeline orchestration.

Decides which media type was uploaded, samples video frames, runs every
applicable detector, aggregates the scores, and builds the evidence report.

Frame sampling keeps video processing bounded: one frame every
``VIDEO_FRAME_SAMPLE_RATE`` frames, capped at ``VIDEO_MAX_FRAMES``.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import List, Optional

import numpy as np

from . import config, report_generator, scoring
from .models import (
    audio_sync,
    face_forgery,
    frequency_analysis,
    gan_fingerprint,
    liveness,
    metadata_forensics,
    pixel_forensics,
    temporal_analysis,
)

# Order is cosmetic (report ordering); weighting lives in config.
_DETECTORS = [
    face_forgery,
    frequency_analysis,
    liveness,
    temporal_analysis,
    audio_sync,
    gan_fingerprint,
    metadata_forensics,
    pixel_forensics,
]


def media_type_for(filename: str) -> Optional[str]:
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext in config.SUPPORTED_IMAGE_FORMATS:
        return "image"
    if ext in config.SUPPORTED_VIDEO_FORMATS:
        return "video"
    return None


def _sample_video_frames(path: str) -> List[np.ndarray]:
    """Sample frames from a video using OpenCV. Returns [] if unavailable."""
    try:
        import cv2  # type: ignore
    except Exception:
        return []
    frames: List[np.ndarray] = []
    cap = cv2.VideoCapture(path)
    idx = 0
    try:
        while len(frames) < config.VIDEO_MAX_FRAMES:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % config.VIDEO_FRAME_SAMPLE_RATE == 0:
                # OpenCV is BGR; convert to RGB for the detectors.
                frames.append(frame[:, :, ::-1].copy())
            idx += 1
    finally:
        cap.release()
    return frames


def run_pipeline(scan_id: str, file_path: str, filename: str) -> dict:
    """Run the full detection pipeline and return the aggregated report dict."""
    started = time.time()
    media_type = media_type_for(filename)
    if media_type is None:
        raise ValueError(f"Unsupported file type: {filename}")

    frames: List[np.ndarray] = []
    if media_type == "video":
        frames = _sample_video_frames(file_path)

    results = []
    for mod in _DETECTORS:
        results.append(
            mod.run(file_path, media_type=media_type, frames=frames or None)
        )

    aggregate = scoring.aggregate(results)

    # Collect anomaly regions (from pixel forensics) for visualization.
    regions = []
    for r in results:
        if r.name == pixel_forensics.NAME:
            regions = r.regions

    report = report_generator.build_report(scan_id, filename, media_type, aggregate)
    report_generator.save_json(report)

    image_for_viz = file_path if media_type == "image" else None
    artifacts = report_generator.render_visualizations(scan_id, image_for_viz, regions)
    pdf = report_generator.export_pdf(report, artifacts)

    aggregate["scan_id"] = scan_id
    aggregate["filename"] = filename
    aggregate["media_type"] = media_type
    aggregate["processing_time_sec"] = round(time.time() - started, 2)
    aggregate["artifacts"] = {
        **artifacts,
        "report_json": str(config.REPORT_DIR / f"{scan_id}.json"),
        **({"report_pdf": str(pdf)} if pdf else {}),
    }
    return aggregate

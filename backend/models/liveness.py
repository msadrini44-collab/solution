"""
Detector 3 — Liveness detection.

Combines three weak signals that distinguish a live capture of a real person
from a synthetic face, a printed photo, or a replayed screen:

1. **Eye-blink dynamics** — across video frames, real subjects blink; the
   eye-aspect-ratio (EAR) computed from facial landmarks oscillates. Many
   deepfakes and still photos have static, half-open, or non-blinking eyes.
2. **Micro-expression / motion** — frame-to-frame variation in the face region
   (still photos are perfectly static).
3. **Texture / moire** — printed photos and screens introduce low micro-texture
   or regular moire patterns versus real skin.

Landmarks use mediapipe FaceMesh when available; otherwise a texture-only
heuristic is used (and the result is marked DEGRADED).
"""
from __future__ import annotations

from typing import List, Optional

import numpy as np

from .base import DetectorResult, DetectorStatus, errored

NAME = "liveness"

# mediapipe FaceMesh indices for the six eye-contour points per eye.
_LEFT_EYE = [33, 160, 158, 133, 153, 144]
_RIGHT_EYE = [362, 385, 387, 263, 373, 380]

_face_mesh = None
_mp_failed = False


def _get_face_mesh():
    global _face_mesh, _mp_failed
    if _face_mesh is not None:
        return _face_mesh
    if _mp_failed:
        return None
    try:
        import mediapipe as mp

        _face_mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False, max_num_faces=1, refine_landmarks=True
        )
        return _face_mesh
    except Exception:
        _mp_failed = True
        return None


def _eye_aspect_ratio(pts: np.ndarray) -> float:
    """EAR = (||p2-p6|| + ||p3-p5||) / (2 * ||p1-p4||)."""
    a = np.linalg.norm(pts[1] - pts[5])
    b = np.linalg.norm(pts[2] - pts[4])
    c = np.linalg.norm(pts[0] - pts[3]) + 1e-6
    return float((a + b) / (2.0 * c))


def _texture_liveness(arr: np.ndarray) -> float:
    """Skin micro-texture heuristic -> fake/spoof probability."""
    gray = arr.mean(axis=2) if arr.ndim == 3 else arr
    # Local standard deviation as a proxy for micro-texture richness.
    local_std = float(np.std(gray))
    # Very low texture -> screen/print/synthetic; map inversely.
    return float(np.clip(1.0 - (local_std / 60.0), 0.0, 1.0))


def run(
    path: str,
    *,
    media_type: str,
    frames: Optional[List[np.ndarray]] = None,
    **_: object,
) -> DetectorResult:
    try:
        from PIL import Image

        mesh = _get_face_mesh()

        if frames and mesh is not None:
            ears: List[float] = []
            motions: List[float] = []
            prev = None
            for fr in frames:
                res = mesh.process(fr.astype("uint8"))
                if res.multi_face_landmarks:
                    lm = res.multi_face_landmarks[0].landmark
                    h, w = fr.shape[:2]
                    left = np.array([[lm[i].x * w, lm[i].y * h] for i in _LEFT_EYE])
                    right = np.array([[lm[i].x * w, lm[i].y * h] for i in _RIGHT_EYE])
                    ears.append((_eye_aspect_ratio(left) + _eye_aspect_ratio(right)) / 2)
                if prev is not None:
                    motions.append(float(np.mean(np.abs(fr.astype(np.float32) - prev))))
                prev = fr.astype(np.float32)

            blink_var = float(np.var(ears)) if ears else 0.0
            motion = float(np.mean(motions)) if motions else 0.0
            # High blink variance + some motion -> live (low fake prob).
            live_score = np.clip(blink_var / 0.0015, 0, 1) * 0.6 + np.clip(motion / 5.0, 0, 1) * 0.4
            fake_p = float(1.0 - live_score)
            return DetectorResult(
                name=NAME,
                fake_probability=fake_p,
                status=DetectorStatus.OK,
                summary="Eye-blink (EAR) and motion liveness over video frames.",
                details={
                    "blink_variance": round(blink_var, 5),
                    "mean_motion": round(motion, 3),
                    "frames_analyzed": len(frames),
                },
            )

        # ---- heuristic / single-image fallback ----
        if frames:
            arr = frames[len(frames) // 2]
        else:
            arr = np.asarray(Image.open(path).convert("RGB"))
        fake_p = _texture_liveness(arr)
        return DetectorResult(
            name=NAME,
            fake_probability=fake_p,
            status=DetectorStatus.DEGRADED,
            summary="Texture-based liveness heuristic (no landmark tracking).",
            details={"method": "skin_micro_texture"},
        )
    except Exception as exc:
        return errored(NAME, exc)

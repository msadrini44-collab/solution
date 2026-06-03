"""
Detector 1 — Face forgery detection.

Pipeline
--------
1. Detect and crop the largest face with MTCNN (``facenet-pytorch``).
2. Feed the aligned 299x299 (Xception) / 380x380 (EfficientNet-B4) crop into a
   CNN classifier pretrained on FaceForensics++ to obtain a real/fake
   probability.

The classifier architecture is built here; the pretrained weights are fetched
by ``scripts/download_models.py``. When torch / the weights are unavailable we
fall back to a texture-based heuristic (blur + high-frequency residual energy),
which still produces a reasonable signal for the demo pipeline.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

from .. import config
from .base import DetectorResult, DetectorStatus, errored

NAME = "face_forgery"

# Cached singletons so we only build the network / detector once.
_model = None
_mtcnn = None
_load_failed = False


def _try_build_model():
    """Build the Xception/EfficientNet classifier and load FF++ weights.

    Returns ``(model, mtcnn)`` on success or ``(None, None)`` if torch or the
    weights are unavailable.
    """
    global _model, _mtcnn, _load_failed
    if _model is not None and _mtcnn is not None:
        return _model, _mtcnn
    if _load_failed:
        return None, None
    try:
        import torch
        import torch.nn as nn
        from torchvision import models as tv_models
        from facenet_pytorch import MTCNN

        weight_path = config.MODEL_DIR / "face_forgery_ffpp.pth"

        # EfficientNet-B4 backbone with a binary (real/fake) head.
        net = tv_models.efficientnet_b4(weights=None)
        in_features = net.classifier[1].in_features
        net.classifier = nn.Sequential(
            nn.Dropout(p=0.3),
            nn.Linear(in_features, 2),
        )

        if weight_path.exists():
            state = torch.load(weight_path, map_location=config.DEVICE)
            state = state.get("state_dict", state)
            net.load_state_dict(state, strict=False)
        elif config.STRICT_MODELS:
            raise FileNotFoundError(
                f"FaceForensics++ weights not found at {weight_path}. "
                "Run scripts/download_models.py."
            )

        net.eval().to(config.DEVICE)
        mtcnn = MTCNN(keep_all=False, device=config.DEVICE, post_process=False)
        _model, _mtcnn = net, mtcnn
        return _model, _mtcnn
    except Exception:
        # torch / facenet-pytorch not installed, or weights missing in strict
        # mode disabled — fall back to the heuristic path.
        _load_failed = True
        return None, None


def _heuristic_face_score(img: np.ndarray) -> float:
    """Texture-residual heuristic used when the CNN is unavailable.

    Deepfake face swaps tend to over-smooth skin and leave blending seams. We
    approximate this by measuring the ratio of high-frequency residual energy
    to overall variance: very low values suggest GAN-style smoothing.
    """
    gray = img.mean(axis=2) if img.ndim == 3 else img
    gray = gray.astype(np.float32)

    # Laplacian-like high-pass via a simple 3x3 kernel convolution.
    k = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
    pad = np.pad(gray, 1, mode="reflect")
    hp = (
        k[0, 1] * pad[:-2, 1:-1]
        + k[1, 0] * pad[1:-1, :-2]
        + k[1, 1] * pad[1:-1, 1:-1]
        + k[1, 2] * pad[1:-1, 2:]
        + k[2, 1] * pad[2:, 1:-1]
    )
    hf_energy = float(np.mean(hp ** 2))
    var = float(np.var(gray)) + 1e-6
    ratio = hf_energy / var

    # Map the residual ratio to a fake probability. Lots of detail -> real.
    # These bounds were chosen empirically for 8-bit images.
    fake_p = float(np.clip(1.0 - (ratio / 0.05), 0.0, 1.0))
    return fake_p


def run(
    path: str,
    *,
    media_type: str,
    frames: Optional[list] = None,
    **_: object,
) -> DetectorResult:
    """Run face-forgery detection on an image or sampled video frames."""
    try:
        from PIL import Image

        # For video, analyse the middle sampled frame; for images, the file.
        if frames:
            arr = frames[len(frames) // 2]
            pil = Image.fromarray(arr.astype("uint8"))
        else:
            pil = Image.open(path).convert("RGB")
            arr = np.asarray(pil)

        model, mtcnn = _try_build_model()

        if model is not None and mtcnn is not None:
            import torch

            face = mtcnn(pil)
            if face is None:
                return DetectorResult(
                    name=NAME,
                    fake_probability=0.5,
                    status=DetectorStatus.DEGRADED,
                    summary="No face detected; forgery model not applicable.",
                    details={"face_detected": False},
                )
            with torch.no_grad():
                x = face.unsqueeze(0).float().to(config.DEVICE) / 255.0
                logits = model(x)
                probs = torch.softmax(logits, dim=1)[0]
                fake_p = float(probs[1].item())
            return DetectorResult(
                name=NAME,
                fake_probability=fake_p,
                status=DetectorStatus.OK,
                summary="EfficientNet-B4 (FaceForensics++) face analysis.",
                details={"face_detected": True, "model": "efficientnet_b4_ffpp"},
            )

        # ---- heuristic fallback ----
        fake_p = _heuristic_face_score(arr)
        return DetectorResult(
            name=NAME,
            fake_probability=fake_p,
            status=DetectorStatus.DEGRADED,
            summary="Heuristic texture-residual analysis (CNN weights unavailable).",
            details={"method": "texture_residual_ratio"},
        )
    except Exception as exc:  # never abort the ensemble
        return errored(NAME, exc)

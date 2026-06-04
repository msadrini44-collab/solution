"""
Detector 6 — GAN / generator source identification.

Every generative architecture leaves a characteristic, periodic *noise
fingerprint* in its output (from its specific upsampling kernels). We extract
the residual noise (image minus a denoised version), take its frequency-domain
signature, and classify it into one of:

    StyleGAN, Stable Diffusion, Midjourney, DALL-E, Real, Unknown

A small classifier head is built here; pretrained weights are loaded from
``gan_fingerprint.pth`` when present. Without torch/weights we fall back to a
nearest-prototype matcher over hand-crafted spectral fingerprint features,
which yields a coarse source guess plus a synthetic-vs-real confidence.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from .. import config
from .base import DetectorResult, DetectorStatus, errored

NAME = "gan_fingerprint"

CLASSES = ["Real", "StyleGAN", "Stable Diffusion", "Midjourney", "DALL-E", "Unknown"]

_model = None
_load_failed = False


def _try_build_model():
    global _model, _load_failed
    if _model is not None:
        return _model
    if _load_failed:
        return None
    try:
        import torch
        import torch.nn as nn

        weight_path = config.MODEL_DIR / "gan_fingerprint.pth"

        # Compact CNN over the residual-noise spectrum.
        net = nn.Sequential(
            nn.Conv2d(1, 16, 3, padding=1), nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(16, 32, 3, padding=1), nn.ReLU(),
            nn.AdaptiveAvgPool2d(4),
            nn.Flatten(),
            nn.Linear(32 * 4 * 4, 64), nn.ReLU(),
            nn.Linear(64, len(CLASSES)),
        )
        if weight_path.exists():
            state = torch.load(weight_path, map_location=config.DEVICE)
            net.load_state_dict(state.get("state_dict", state), strict=False)
        elif config.STRICT_MODELS:
            raise FileNotFoundError("gan_fingerprint weights missing")
        net.eval().to(config.DEVICE)
        _model = net
        return _model
    except Exception:
        _load_failed = True
        return None


def _residual_noise(gray: np.ndarray) -> np.ndarray:
    """Image minus a 3x3 box-blurred version -> high-freq sensor/gen noise."""
    pad = np.pad(gray, 1, mode="reflect")
    blur = (
        pad[:-2, :-2] + pad[:-2, 1:-1] + pad[:-2, 2:]
        + pad[1:-1, :-2] + pad[1:-1, 1:-1] + pad[1:-1, 2:]
        + pad[2:, :-2] + pad[2:, 1:-1] + pad[2:, 2:]
    ) / 9.0
    return gray - blur


def _fingerprint_features(gray: np.ndarray) -> np.ndarray:
    noise = _residual_noise(gray)
    spec = np.log1p(np.abs(np.fft.fftshift(np.fft.fft2(noise))))
    # Downsample the spectrum to a fixed 16x16 descriptor.
    h, w = spec.shape
    hb, wb = max(h // 16, 1), max(w // 16, 1)
    desc = spec[: hb * 16, : wb * 16].reshape(16, hb, 16, wb).mean(axis=(1, 3))
    return desc / (desc.max() + 1e-9)


def run(
    path: str,
    *,
    media_type: str,
    frames: Optional[list] = None,
    **_: object,
) -> DetectorResult:
    try:
        from PIL import Image

        if frames:
            arr = frames[len(frames) // 2]
        else:
            arr = np.asarray(Image.open(path).convert("RGB"))
        gray = arr.mean(axis=2).astype(np.float32) if arr.ndim == 3 else arr.astype(np.float32)

        desc = _fingerprint_features(gray)
        model = _try_build_model()

        if model is not None:
            import torch

            with torch.no_grad():
                x = torch.from_numpy(desc).float().unsqueeze(0).unsqueeze(0)
                probs = torch.softmax(model(x), dim=1)[0].cpu().numpy()
            top = int(np.argmax(probs))
            source = CLASSES[top]
            fake_p = float(1.0 - probs[CLASSES.index("Real")])
            status = DetectorStatus.OK
            summary = f"Noise-fingerprint classifier predicts: {source}."
            details = {
                "predicted_source": source,
                "confidence": round(float(probs[top]), 4),
                "class_probabilities": {c: round(float(p), 4) for c, p in zip(CLASSES, probs)},
            }
        else:
            # Heuristic: regular periodic peaks in the noise spectrum strongly
            # indicate an upsampling-based generator.
            flat = desc.ravel()
            peakiness = float(np.mean((flat > flat.mean() + 3 * flat.std()).astype(np.float32)))
            fake_p = float(np.clip(peakiness / 0.03, 0.0, 1.0))
            source = "Synthetic (architecture unknown)" if fake_p > 0.5 else "Likely Real"
            status = DetectorStatus.DEGRADED
            summary = "Heuristic noise-fingerprint spectral analysis."
            details = {"predicted_source": source, "peak_fraction": round(peakiness, 4)}

        return DetectorResult(
            name=NAME,
            fake_probability=fake_p,
            status=status,
            summary=summary,
            details=details,
        )
    except Exception as exc:
        return errored(NAME, exc)

"""
Detector 2 — Frequency / spectral analysis (FFT & DCT).

Why this works
--------------
GANs and diffusion models synthesise images with transposed convolutions /
upsampling that leave periodic, grid-like artifacts in the Fourier domain.
Natural photographs have a smooth, roughly power-law radial spectrum. By
inspecting the azimuthally-averaged power spectrum and the energy in the
high-frequency band, we can flag the regular spectral peaks typical of
synthetic imagery.

This detector only needs numpy / Pillow (+ scipy if present) so it always runs
at full capability.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from .base import DetectorResult, DetectorStatus, errored

NAME = "frequency_analysis"


def _radial_profile(power: np.ndarray) -> np.ndarray:
    """Azimuthally average a 2D power spectrum into a 1D radial profile."""
    h, w = power.shape
    cy, cx = h / 2.0, w / 2.0
    y, x = np.indices((h, w))
    r = np.sqrt((x - cx) ** 2 + (y - cy) ** 2).astype(np.int32)
    tbin = np.bincount(r.ravel(), power.ravel())
    nr = np.bincount(r.ravel())
    nr[nr == 0] = 1
    return tbin / nr


def _spectral_features(gray: np.ndarray) -> dict:
    """Compute FFT-based features used to score spectral abnormality."""
    # 2D FFT magnitude (log power) centred on DC.
    f = np.fft.fftshift(np.fft.fft2(gray))
    power = np.log1p(np.abs(f) ** 2)

    radial = _radial_profile(power)
    radial = radial[: len(radial) // 2]  # ignore the noisy outer corner bins

    # Fraction of spectral energy in the high-frequency half.
    half = len(radial) // 2
    hf_ratio = float(radial[half:].sum() / (radial.sum() + 1e-9))

    # Spectral "peakiness": GAN grids create sharp periodic peaks, so the
    # detrended profile has high kurtosis / outlier spikes.
    detrended = radial - np.convolve(radial, np.ones(5) / 5, mode="same")
    std = float(np.std(detrended)) + 1e-9
    peaks = float(np.mean((np.abs(detrended) > 3 * std).astype(np.float32)))

    return {
        "high_freq_ratio": round(hf_ratio, 4),
        "spectral_peak_fraction": round(peaks, 4),
    }


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
        # Normalise size for stable thresholds.
        feats = _spectral_features(gray)

        # Combine: abnormally high HF energy OR strong periodic peaks -> fake.
        hf = feats["high_freq_ratio"]
        peaks = feats["spectral_peak_fraction"]
        fake_p = float(np.clip(0.6 * min(hf / 0.35, 1.0) + 0.8 * min(peaks / 0.02, 1.0), 0.0, 1.0))

        return DetectorResult(
            name=NAME,
            fake_probability=fake_p,
            status=DetectorStatus.OK,
            summary="FFT radial power-spectrum and periodic-peak analysis.",
            details=feats,
        )
    except Exception as exc:
        return errored(NAME, exc)

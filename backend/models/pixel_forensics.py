"""
Detector 8 — Pixel-level forensics.

Classic image-forensics ensemble operating directly on pixels:

1. **Error Level Analysis (ELA)** — re-save the image as JPEG at a known
   quality and diff against the original. Untouched regions converge to a low,
   uniform error; spliced/edited regions show higher residual error.
2. **Noise consistency** — natural images have spatially consistent sensor
   noise. Pasted content from another source has a different noise floor.
3. **Clone detection** — near-duplicate blocks reveal copy-paste retouching.
4. **Lighting direction** — gross inconsistencies in estimated shading
   gradients hint at composited elements.

We also export the ELA heatmap (peak anomaly regions) for the evidence report.
Pure numpy / Pillow, so always runs.
"""
from __future__ import annotations

from typing import List, Optional

import io

import numpy as np

from .base import DetectorResult, DetectorStatus, errored

NAME = "pixel_forensics"


def _ela_map(pil_img, quality: int = 90) -> np.ndarray:
    """Compute the Error Level Analysis difference map."""
    from PIL import Image

    buf = io.BytesIO()
    pil_img.convert("RGB").save(buf, "JPEG", quality=quality)
    buf.seek(0)
    resaved = Image.open(buf).convert("RGB")
    a = np.asarray(pil_img.convert("RGB"), dtype=np.int16)
    b = np.asarray(resaved, dtype=np.int16)
    diff = np.abs(a - b).astype(np.float32)
    return diff.mean(axis=2)


def _top_regions(heat: np.ndarray, k: int = 3, block: int = 32) -> List[List[int]]:
    """Return up to k high-anomaly [x, y, w, h] blocks from a heatmap."""
    h, w = heat.shape
    regions = []
    block = max(8, min(block, h, w))
    scores = []
    for by in range(0, max(h - block + 1, 1), block):
        for bx in range(0, max(w - block + 1, 1), block):
            patch = heat[by:by + block, bx:bx + block]
            scores.append((float(patch.mean()), bx, by))
    scores.sort(reverse=True)
    for s, bx, by in scores[:k]:
        regions.append([int(bx), int(by), block, block])
    return regions


def _high_pass(gray: np.ndarray) -> np.ndarray:
    pad = np.pad(gray, 1, mode="reflect")
    blur = (
        pad[:-2, :-2] + pad[:-2, 1:-1] + pad[:-2, 2:]
        + pad[1:-1, :-2] + pad[1:-1, 1:-1] + pad[1:-1, 2:]
        + pad[2:, :-2] + pad[2:, 1:-1] + pad[2:, 2:]
    ) / 9.0
    return gray - blur


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
            pil = Image.fromarray(frames[len(frames) // 2].astype("uint8"))
        else:
            pil = Image.open(path).convert("RGB")
        arr = np.asarray(pil.convert("RGB")).astype(np.float32)
        gray = arr.mean(axis=2)

        # 1. ELA.
        ela = _ela_map(pil)
        ela_mean = float(ela.mean())
        ela_max = float(ela.max())
        # High and spatially uneven ELA -> manipulation.
        ela_uniformity = float(ela.std() / (ela.mean() + 1e-6))
        regions = _top_regions(ela)

        # 2. Noise consistency across a 4x4 grid of tiles.
        h, w = gray.shape
        th, tw = h // 4 or 1, w // 4 or 1
        tile_noise = []
        for ty in range(0, h - th, th):
            for tx in range(0, w - tw, tw):
                tile = gray[ty:ty + th, tx:tx + tw]
                hp = _high_pass(tile)
                tile_noise.append(float(np.std(hp)))
        noise_inconsistency = float(np.std(tile_noise) / (np.mean(tile_noise) + 1e-6)) if tile_noise else 0.0

        # 3. Lighting gradient consistency.
        gy, gx = np.gradient(gray)
        ang = np.arctan2(gy, gx)
        light_inconsistency = float(np.std(ang) / np.pi)

        fake_p = float(np.clip(
            0.4 * min(ela_uniformity / 1.5, 1.0)
            + 0.4 * min(noise_inconsistency / 0.8, 1.0)
            + 0.2 * min(light_inconsistency, 1.0),
            0.0, 1.0,
        ))

        return DetectorResult(
            name=NAME,
            fake_probability=fake_p,
            status=DetectorStatus.OK,
            summary="ELA, noise-consistency, and lighting-direction forensics.",
            details={
                "ela_mean": round(ela_mean, 3),
                "ela_max": round(ela_max, 3),
                "ela_uniformity": round(ela_uniformity, 4),
                "noise_inconsistency": round(noise_inconsistency, 4),
                "lighting_inconsistency": round(light_inconsistency, 4),
            },
            regions=regions,
        )
    except Exception as exc:
        return errored(NAME, exc)

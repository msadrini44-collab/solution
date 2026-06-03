"""
Detector 4 — Video temporal consistency.

Deepfake video generators operate frame-by-frame (or with weak temporal
constraints), so they tend to produce:

* **Flicker** — per-frame brightness/identity jitter on the manipulated region.
* **Inconsistent lighting** — global illumination that changes unnaturally.
* **Unnatural motion** — optical-flow magnitudes that are either too erratic or
  unrealistically smooth/frozen.

We sample frames (done upstream), compute dense optical flow between
consecutive frames (Farneback via OpenCV when available, else a brightness-
difference proxy), and score the temporal stability of flow magnitude and
luminance.

Only applies to video; images are SKIPPED.
"""
from __future__ import annotations

from typing import List, Optional

import numpy as np

from .base import DetectorResult, DetectorStatus, errored, skipped

NAME = "temporal_analysis"


def _gray(fr: np.ndarray) -> np.ndarray:
    return fr.mean(axis=2).astype(np.float32) if fr.ndim == 3 else fr.astype(np.float32)


def run(
    path: str,
    *,
    media_type: str,
    frames: Optional[List[np.ndarray]] = None,
    **_: object,
) -> DetectorResult:
    if media_type != "video" or not frames or len(frames) < 2:
        return skipped(NAME, "Temporal analysis requires multiple video frames.")
    try:
        try:
            import cv2  # type: ignore

            have_cv2 = True
        except Exception:
            have_cv2 = False

        flow_mags: List[float] = []
        lumas: List[float] = []
        prev = _gray(frames[0])
        lumas.append(float(prev.mean()))

        for fr in frames[1:]:
            cur = _gray(fr)
            lumas.append(float(cur.mean()))
            if have_cv2:
                flow = cv2.calcOpticalFlowFarneback(
                    prev.astype(np.uint8), cur.astype(np.uint8),
                    None, 0.5, 3, 15, 3, 5, 1.2, 0,
                )
                mag = float(np.mean(np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)))
            else:
                mag = float(np.mean(np.abs(cur - prev)))
            flow_mags.append(mag)
            prev = cur

        # Temporal instability: high coefficient-of-variation of flow magnitude
        # and abrupt luminance jumps indicate flicker / inconsistency.
        flow_arr = np.asarray(flow_mags) + 1e-6
        flow_cov = float(np.std(flow_arr) / (np.mean(flow_arr) + 1e-6))
        luma_jitter = float(np.std(np.diff(lumas)))

        fake_p = float(np.clip(0.5 * min(flow_cov / 1.5, 1.0) + 0.5 * min(luma_jitter / 8.0, 1.0), 0.0, 1.0))

        return DetectorResult(
            name=NAME,
            fake_probability=fake_p,
            status=DetectorStatus.OK if have_cv2 else DetectorStatus.DEGRADED,
            summary="Optical-flow stability and luminance-flicker analysis.",
            details={
                "flow_coeff_of_variation": round(flow_cov, 4),
                "luminance_jitter": round(luma_jitter, 4),
                "optical_flow": "farneback" if have_cv2 else "brightness_proxy",
                "frames_analyzed": len(frames),
            },
        )
    except Exception as exc:
        return errored(NAME, exc)

"""
Ensemble scoring.

Combines the per-detector ``fake_probability`` values into a single
authenticity confidence (0-100, higher == more authentic) and a categorical
verdict. Detectors that were SKIPPED (not applicable to the media type) or
ERRORed are excluded from the weighted average so they don't bias the result.
"""
from __future__ import annotations

from typing import Dict, List

from . import config
from .models.base import DetectorResult, DetectorStatus


def _verdict_for_score(score: float) -> str:
    for threshold, label in config.VERDICT_THRESHOLDS:
        if score >= threshold:
            return label
    return config.VERDICT_THRESHOLDS[-1][1]


def aggregate(results: List[DetectorResult]) -> Dict:
    """Aggregate detector results into the final scored verdict.

    Returns a dict with the overall score, verdict, and a per-detector
    breakdown suitable for direct JSON serialisation to the frontend.
    """
    weighted_sum = 0.0
    weight_total = 0.0
    breakdown = []

    for r in results:
        applicable = r.status in (DetectorStatus.OK, DetectorStatus.DEGRADED)
        weight = config.DETECTOR_WEIGHTS.get(r.name, 0.0)
        # Degraded detectors are down-weighted since they use fallbacks.
        effective_weight = weight * (0.6 if r.status == DetectorStatus.DEGRADED else 1.0)

        if applicable and effective_weight > 0:
            weighted_sum += r.fake_probability * effective_weight
            weight_total += effective_weight

        breakdown.append({
            **r.to_dict(),
            "weight": round(weight, 3),
            "contributed": applicable and effective_weight > 0,
        })

    if weight_total > 0:
        fake_probability = weighted_sum / weight_total
    else:
        fake_probability = 0.5  # nothing applicable -> undecided

    # Authenticity score: 100 == real, 0 == fake.
    score = round((1.0 - fake_probability) * 100.0, 1)
    verdict = _verdict_for_score(score)

    # Confidence in the verdict: how far from the undecided midpoint.
    confidence = round(abs(score - 50.0) / 50.0 * 100.0, 1)

    return {
        "score": score,
        "fake_probability": round(fake_probability, 4),
        "verdict": verdict,
        "verdict_confidence": confidence,
        "detectors_used": int(round(weight_total / max(weight_total, 1e-9))) if weight_total else 0,
        "num_detectors_contributing": sum(1 for b in breakdown if b["contributed"]),
        "breakdown": breakdown,
    }

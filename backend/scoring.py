"""
Ensemble scoring.

Combines the per-detector ``fake_probability`` values into a single
authenticity confidence (0-100, higher == more authentic) and a categorical
verdict. Detectors that were SKIPPED (not applicable to the media type) or
ERRORed are excluded from the weighted average so they don't bias the result.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from . import config
from .models.base import DetectorResult, DetectorStatus


def _verdict_for_score(score: float) -> str:
    for threshold, label in config.VERDICT_THRESHOLDS:
        if score >= threshold:
            return label
    return config.VERDICT_THRESHOLDS[-1][1]


def _evidence_grade(contributing: int, degraded: int, premium_available: bool) -> str:
    if premium_available and contributing >= 6 and degraded <= 2:
        return "premium"
    if contributing >= 6 and degraded <= 3:
        return "strong"
    if contributing >= 4:
        return "standard"
    if contributing >= 2:
        return "limited"
    return "insufficient"


def _calibrate_probability(
    fake_probability: float,
    detector_probs: List[float],
) -> Tuple[float, List[str]]:
    notes: List[str] = []
    if not detector_probs:
        return 0.5, ["No detector produced usable evidence."]

    strong_fake = sum(1 for p in detector_probs if p >= 0.72)
    strong_real = sum(1 for p in detector_probs if p <= 0.28)
    spread = max(detector_probs) - min(detector_probs)

    if len(detector_probs) < 3:
        notes.append("Limited detector coverage; treat the verdict as provisional.")
        fake_probability = 0.5 + ((fake_probability - 0.5) * 0.6)

    if strong_fake == 1 and strong_real >= 2:
        notes.append("Single-detector fake signal contradicted by stronger authentic evidence.")
        fake_probability = min(fake_probability, 0.62)

    if strong_fake >= 2 and fake_probability < 0.52:
        notes.append("Multiple independent fake indicators raised the risk estimate.")
        fake_probability = max(fake_probability, 0.52)

    if spread >= 0.55 and 0.35 <= fake_probability <= 0.65:
        notes.append("Detector disagreement is high; manual review recommended.")

    return max(0.0, min(1.0, fake_probability)), notes


def aggregate(results: List[DetectorResult]) -> Dict:
    """Aggregate detector results into the final scored verdict.

    Returns a dict with the overall score, verdict, and a per-detector
    breakdown suitable for direct JSON serialisation to the frontend.
    """
    weighted_sum = 0.0
    weight_total = 0.0
    breakdown = []
    contributing_probs: List[float] = []
    degraded_count = 0
    premium_available = False

    for r in results:
        applicable = r.status in (DetectorStatus.OK, DetectorStatus.DEGRADED)
        weight = config.DETECTOR_WEIGHTS.get(r.name, 0.0)
        # Degraded detectors are down-weighted since they use fallbacks.
        effective_weight = weight * (0.6 if r.status == DetectorStatus.DEGRADED else 1.0)

        if applicable and effective_weight > 0:
            weighted_sum += r.fake_probability * effective_weight
            weight_total += effective_weight
            contributing_probs.append(r.fake_probability)
            if r.status == DetectorStatus.DEGRADED:
                degraded_count += 1
            if r.name == "premium_consensus":
                premium_available = True

        breakdown.append({
            **r.to_dict(),
            "weight": round(weight, 3),
            "contributed": applicable and effective_weight > 0,
        })

    if weight_total > 0:
        fake_probability = weighted_sum / weight_total
    else:
        fake_probability = 0.5  # nothing applicable -> undecided
    fake_probability, decision_notes = _calibrate_probability(fake_probability, contributing_probs)

    # Authenticity score: 100 == real, 0 == fake.
    score = round((1.0 - fake_probability) * 100.0, 1)
    verdict = _verdict_for_score(score)

    # Confidence in the verdict: how far from the undecided midpoint.
    evidence_grade = _evidence_grade(len(contributing_probs), degraded_count, premium_available)
    disagreement = (
        float(max(contributing_probs) - min(contributing_probs))
        if contributing_probs else 1.0
    )
    confidence_multiplier = max(0.45, 1.0 - disagreement * 0.35)
    if evidence_grade in {"limited", "insufficient"}:
        confidence_multiplier *= 0.7
    confidence = round(abs(score - 50.0) / 50.0 * 100.0 * confidence_multiplier, 1)
    if 40 <= score < 60 and "Detector disagreement is high; manual review recommended." not in decision_notes:
        decision_notes.append("Borderline score; use the evidence report before making a final decision.")

    return {
        "score": score,
        "fake_probability": round(fake_probability, 4),
        "verdict": verdict,
        "verdict_confidence": confidence,
        "detectors_used": sum(1 for b in breakdown if b["contributed"]),
        "num_detectors_contributing": sum(1 for b in breakdown if b["contributed"]),
        "evidence_grade": evidence_grade,
        "risk_band": "high" if score < 40 else "review" if score < 60 else "low",
        "decision_notes": decision_notes,
        "recommended_action": (
            "Escalate to manual forensic review."
            if score < 40 or evidence_grade in {"limited", "insufficient"}
            else "Use the report as supporting evidence."
        ),
        "premium_signals_available": premium_available,
        "breakdown": breakdown,
    }

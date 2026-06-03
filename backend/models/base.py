"""
Shared types and helpers for all detectors.

The contract every detector follows:

    run(path, *, media_type, frames=None, **kwargs) -> DetectorResult

``fake_probability`` is the canonical number consumed by the ensemble: a float
in [0, 1] where 1 means "almost certainly manipulated / synthetic". Detectors
also attach a human-readable ``score`` (0-100, higher == more authentic) and a
free-form ``details`` dict for the evidence report.
"""
from __future__ import annotations

import dataclasses
import enum
from typing import Any, Dict, List, Optional


class DetectorStatus(str, enum.Enum):
    """Outcome of a single detector run."""

    OK = "ok"  # detector ran with full capability
    DEGRADED = "degraded"  # ran via heuristic fallback (missing weights/deps)
    SKIPPED = "skipped"  # not applicable to this media type
    ERROR = "error"  # unexpected failure (does not abort the pipeline)


@dataclasses.dataclass
class DetectorResult:
    """Normalised output of a detector."""

    name: str
    # Canonical signal for the ensemble: probability the media is fake [0, 1].
    fake_probability: float
    status: DetectorStatus = DetectorStatus.OK
    # 0-100 authenticity score (100 == looks real). Derived from
    # fake_probability by default but detectors may override.
    score: Optional[float] = None
    # Short label shown in UIs, e.g. "No spectral artifacts detected".
    summary: str = ""
    # Arbitrary structured findings for the evidence report.
    details: Dict[str, Any] = dataclasses.field(default_factory=dict)
    # Optional anomaly regions as [x, y, w, h] in pixel coordinates.
    regions: List[List[int]] = dataclasses.field(default_factory=list)

    def __post_init__(self) -> None:
        self.fake_probability = _clamp01(self.fake_probability)
        if self.score is None:
            self.score = round((1.0 - self.fake_probability) * 100.0, 1)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "fake_probability": round(self.fake_probability, 4),
            "score": self.score,
            "status": self.status.value,
            "summary": self.summary,
            "details": self.details,
            "regions": self.regions,
        }


def _clamp01(x: float) -> float:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return 0.5
    if x != x:  # NaN guard
        return 0.5
    return max(0.0, min(1.0, x))


def skipped(name: str, reason: str) -> DetectorResult:
    """Build a SKIPPED result with a neutral probability."""
    return DetectorResult(
        name=name,
        fake_probability=0.5,
        status=DetectorStatus.SKIPPED,
        summary=reason,
        details={"reason": reason},
    )


def errored(name: str, exc: Exception) -> DetectorResult:
    """Build an ERROR result that won't abort the ensemble."""
    return DetectorResult(
        name=name,
        fake_probability=0.5,
        status=DetectorStatus.ERROR,
        summary=f"Detector failed: {exc}",
        details={"error": str(exc)},
    )

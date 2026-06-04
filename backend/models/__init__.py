"""
Detection model package.

Each module exposes a single ``run(...)`` entry point that returns a
:class:`DetectorResult`. Detectors are intentionally decoupled so they can be
added, removed, or re-weighted in the ensemble (see ``backend/scoring.py``)
without touching one another.

Heavy third-party dependencies (torch, mediapipe, dlib, librosa, ...) are
imported lazily inside each detector. When a dependency or its pretrained
weights are unavailable the detector degrades to a documented lightweight
heuristic instead of crashing, so the full pipeline stays demoable. Set the
``ADF_STRICT_MODELS`` env var to force hard failures when real weights are
missing.
"""
from .base import DetectorResult, DetectorStatus

__all__ = ["DetectorResult", "DetectorStatus"]

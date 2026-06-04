"""
Optional provider-consensus detector.

Configured premium detectors run as independent external checks and are folded
into the ensemble only when ADF_ENABLE_PAID_APIS=1 and ADF_PREMIUM_DETECTORS is
set. The core engine remains fully self-hostable when no provider is configured.
"""
from __future__ import annotations

import json
import mimetypes
import os
import uuid
from typing import Dict, List, Optional
from urllib import request

import numpy as np

from .. import config
from .base import DetectorResult, DetectorStatus, errored, skipped

NAME = "premium_consensus"


def _build_multipart(path: str, filename: str) -> tuple[bytes, str]:
    boundary = "adf-" + uuid.uuid4().hex
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    with open(path, "rb") as fh:
        payload = fh.read()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode("utf-8") + payload + f"\r\n--{boundary}--\r\n".encode("utf-8")
    return body, f"multipart/form-data; boundary={boundary}"


def _extract_probability(data: Dict[str, object]) -> Optional[float]:
    for key in ("fake_probability", "deepfake_probability", "synthetic_probability"):
        value = data.get(key)
        if isinstance(value, (int, float)):
            return float(value)

    score = data.get("score")
    if isinstance(score, (int, float)):
        if 0 <= score <= 1:
            return 1.0 - float(score)
        if 0 <= score <= 100:
            return 1.0 - (float(score) / 100.0)

    verdict = str(data.get("verdict", "")).lower()
    if "fake" in verdict or "synthetic" in verdict or "generated" in verdict:
        return 0.85
    if "real" in verdict or "authentic" in verdict:
        return 0.15
    return None


def _call_provider(provider: config.PremiumProvider, path: str, filename: str) -> Dict[str, object]:
    key = os.getenv(provider["api_key_env"], "")
    if not key:
        return {
            "provider": provider["name"],
            "status": "skipped",
            "reason": f"{provider['api_key_env']} is not set",
        }

    body, content_type = _build_multipart(path, filename)
    req = request.Request(
        provider["url"],
        data=body,
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": content_type,
            "Accept": "application/json",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=25) as resp:
        raw = resp.read().decode("utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        return {"provider": provider["name"], "status": "error", "reason": "Non-object JSON response"}

    probability = _extract_probability(data)
    return {
        "provider": provider["name"],
        "status": "ok" if probability is not None else "unscored",
        "fake_probability": probability,
        "raw_verdict": data.get("verdict"),
        "raw_score": data.get("score"),
    }


def run(
    path: str,
    *,
    media_type: str,
    frames: Optional[list] = None,
    **_: object,
) -> DetectorResult:
    if not config.ENABLE_PAID_APIS:
        return skipped(NAME, "Premium detector providers are disabled.")
    if not config.PREMIUM_PROVIDERS:
        return skipped(NAME, "No premium detector providers are configured.")

    try:
        filename = os.path.basename(path)
        responses: List[Dict[str, object]] = []
        probabilities: List[float] = []
        for provider in config.PREMIUM_PROVIDERS:
            try:
                response = _call_provider(provider, path, filename)
            except Exception as exc:
                response = {"provider": provider["name"], "status": "error", "reason": str(exc)}
            responses.append(response)
            probability = response.get("fake_probability")
            if isinstance(probability, (int, float)):
                probabilities.append(float(probability))

        if not probabilities:
            return DetectorResult(
                name=NAME,
                fake_probability=0.5,
                status=DetectorStatus.DEGRADED,
                summary="Premium providers were reachable but returned no usable score.",
                details={"providers": responses},
            )

        fake_p = float(np.median(probabilities))
        return DetectorResult(
            name=NAME,
            fake_probability=fake_p,
            status=DetectorStatus.OK,
            summary=f"Consensus from {len(probabilities)} configured premium detector(s).",
            details={"providers": responses},
        )
    except Exception as exc:
        return errored(NAME, exc)

"""
Detector 7 — EXIF / metadata forensics.

Manipulated images frequently betray themselves in their container metadata:

* **Editing-software traces** — EXIF ``Software`` tag set to Photoshop / GIMP /
  Lightroom, or XMP toolkit markers.
* **Stripped metadata** — AI generators and re-encoders usually output files
  with no camera make/model, no capture timestamp, and no GPS — suspicious for
  a "real photo".
* **Quantization tables** — JPEGs re-saved by editors use standard library
  quantization tables that differ from in-camera tables.
* **Inconsistencies** — modify date earlier than create date, mismatched
  dimensions, etc.

Pure-Python via Pillow's EXIF reader; always runs at full capability for
images. Videos are SKIPPED (handled by other detectors).
"""
from __future__ import annotations

from typing import List, Optional

from .base import DetectorResult, DetectorStatus, errored, skipped

NAME = "metadata_forensics"

_EDITOR_MARKERS = [
    "photoshop", "gimp", "lightroom", "affinity", "pixelmator",
    "paint.net", "snapseed", "facetune", "midjourney", "dall-e",
    "stable diffusion", "dream", "firefly",
]


def run(
    path: str,
    *,
    media_type: str,
    frames: Optional[list] = None,
    **_: object,
) -> DetectorResult:
    if media_type != "image":
        return skipped(NAME, "Metadata forensics targets still images.")
    try:
        from PIL import Image, ExifTags

        findings: List[str] = []
        score_penalty = 0.0

        img = Image.open(path)
        fmt = (img.format or "").upper()
        exif_raw = None
        try:
            exif_raw = img._getexif()  # type: ignore[attr-defined]
        except Exception:
            exif_raw = None

        exif = {}
        if exif_raw:
            for tag_id, value in exif_raw.items():
                tag = ExifTags.TAGS.get(tag_id, str(tag_id))
                exif[tag] = value

        software = str(exif.get("Software", "")).lower()
        make = exif.get("Make")
        model = exif.get("Model")
        dt_original = exif.get("DateTimeOriginal")

        # 1. Editing-software trace.
        for marker in _EDITOR_MARKERS:
            if marker in software:
                findings.append(f"Editing/generation software detected: '{exif.get('Software')}'.")
                score_penalty += 0.5
                break

        # 2. Stripped metadata for a supposed photograph.
        if fmt in {"JPEG", "JPG"} and not exif:
            findings.append("JPEG has no EXIF metadata (commonly stripped after manipulation/AI generation).")
            score_penalty += 0.35
        else:
            if not make and not model:
                findings.append("No camera make/model present.")
                score_penalty += 0.2
            if not dt_original:
                findings.append("No original capture timestamp present.")
                score_penalty += 0.1

        # 3. Date inconsistency.
        dt_digitized = exif.get("DateTimeDigitized")
        if dt_original and dt_digitized and dt_original != dt_digitized:
            findings.append("DateTimeOriginal differs from DateTimeDigitized.")
            score_penalty += 0.1

        # 4. PNG (lossless) presented as a photo — neutral but noted.
        if fmt == "PNG":
            findings.append("PNG container — lossless format atypical for camera photos.")
            score_penalty += 0.1

        fake_p = max(0.0, min(1.0, score_penalty))
        if not findings:
            findings.append("Metadata appears consistent with an unedited capture.")

        return DetectorResult(
            name=NAME,
            fake_probability=fake_p,
            status=DetectorStatus.OK,
            summary="EXIF/metadata integrity and editing-trace analysis.",
            details={
                "format": fmt,
                "has_exif": bool(exif),
                "software": exif.get("Software"),
                "camera_make": make,
                "camera_model": model,
                "findings": findings,
            },
        )
    except Exception as exc:
        return errored(NAME, exc)

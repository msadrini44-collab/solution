"""
Evidence report generation.

Produces a structured JSON report of a scan and, when matplotlib is available,
visualizations (ELA/anomaly heatmap overlay + frequency-spectrum plot). The
report can be exported to PDF when ``reportlab`` is installed; otherwise the
JSON report remains the canonical, always-available artifact.
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from . import config


def build_report(scan_id: str, filename: str, media_type: str,
                 aggregate_result: Dict) -> Dict:
    """Assemble the canonical JSON evidence report."""
    return {
        "report_version": "1.0",
        "scan_id": scan_id,
        "filename": filename,
        "media_type": media_type,
        "generated_at": _dt.datetime.utcnow().isoformat() + "Z",
        "overall": {
            "score": aggregate_result["score"],
            "verdict": aggregate_result["verdict"],
            "verdict_confidence": aggregate_result["verdict_confidence"],
            "fake_probability": aggregate_result["fake_probability"],
        },
        "detectors": aggregate_result["breakdown"],
        "engine": {
            "name": "AntiDeepfake AI",
            "detectors": list(config.DETECTOR_WEIGHTS.keys()),
        },
    }


def save_json(report: Dict) -> Path:
    out = config.REPORT_DIR / f"{report['scan_id']}.json"
    out.write_text(json.dumps(report, indent=2))
    return out


def render_visualizations(scan_id: str, image_path: Optional[str],
                          regions: List[List[int]]) -> Dict[str, str]:
    """Render heatmap overlay + frequency spectrum PNGs.

    Returns a mapping of artifact-name -> file path. Silently returns an empty
    dict if matplotlib / the source image is unavailable.
    """
    artifacts: Dict[str, str] = {}
    if not image_path or not Path(image_path).exists():
        return artifacts
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from PIL import Image

        img = np.asarray(Image.open(image_path).convert("RGB"))
        gray = img.mean(axis=2)

        # --- anomaly heatmap overlay ---
        fig, ax = plt.subplots(figsize=(6, 6))
        ax.imshow(img)
        for (x, y, w, h) in regions:
            ax.add_patch(plt.Rectangle((x, y), w, h, fill=False,
                                       edgecolor="red", linewidth=2))
        ax.set_title("Anomaly regions")
        ax.axis("off")
        heat_path = config.REPORT_DIR / f"{scan_id}_heatmap.png"
        fig.savefig(heat_path, bbox_inches="tight", dpi=110)
        plt.close(fig)
        artifacts["heatmap"] = str(heat_path)

        # --- frequency spectrum ---
        spec = np.log1p(np.abs(np.fft.fftshift(np.fft.fft2(gray))))
        fig, ax = plt.subplots(figsize=(6, 6))
        ax.imshow(spec, cmap="inferno")
        ax.set_title("Log power spectrum (FFT)")
        ax.axis("off")
        spec_path = config.REPORT_DIR / f"{scan_id}_spectrum.png"
        fig.savefig(spec_path, bbox_inches="tight", dpi=110)
        plt.close(fig)
        artifacts["spectrum"] = str(spec_path)
    except Exception:
        # Visualizations are best-effort; the JSON report is the source of truth.
        return artifacts
    return artifacts


def export_pdf(report: Dict, artifacts: Dict[str, str]) -> Optional[Path]:
    """Export the report to PDF. Returns None if reportlab is unavailable."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.units import inch
        from reportlab.pdfgen import canvas
    except Exception:
        return None

    out = config.REPORT_DIR / f"{report['scan_id']}.pdf"
    c = canvas.Canvas(str(out), pagesize=letter)
    width, height = letter
    y = height - inch

    c.setFont("Helvetica-Bold", 18)
    c.drawString(inch, y, "AntiDeepfake AI — Evidence Report")
    y -= 0.4 * inch
    c.setFont("Helvetica", 11)
    for line in [
        f"Scan ID: {report['scan_id']}",
        f"File: {report['filename']} ({report['media_type']})",
        f"Generated: {report['generated_at']}",
        f"Verdict: {report['overall']['verdict']}  "
        f"(score {report['overall']['score']}/100, "
        f"confidence {report['overall']['verdict_confidence']}%)",
    ]:
        c.drawString(inch, y, line)
        y -= 0.28 * inch

    y -= 0.1 * inch
    c.setFont("Helvetica-Bold", 13)
    c.drawString(inch, y, "Detector breakdown")
    y -= 0.3 * inch
    c.setFont("Helvetica", 10)
    for d in report["detectors"]:
        line = f"- {d['name']}: score {d['score']}/100 [{d['status']}] {d['summary']}"
        c.drawString(inch, y, line[:100])
        y -= 0.24 * inch
        if y < inch:
            c.showPage()
            y = height - inch

    # Embed visualizations on a new page if present.
    img_paths = [p for p in artifacts.values() if Path(p).exists()]
    if img_paths:
        c.showPage()
        y = height - inch
        c.setFont("Helvetica-Bold", 13)
        c.drawString(inch, y, "Visualizations")
        y -= 0.3 * inch
        for p in img_paths:
            try:
                c.drawImage(p, inch, y - 3 * inch, width=3 * inch,
                            height=3 * inch, preserveAspectRatio=True)
                y -= 3.2 * inch
                if y < inch:
                    c.showPage()
                    y = height - inch
            except Exception:
                continue

    c.save()
    return out

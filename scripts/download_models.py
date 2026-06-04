#!/usr/bin/env python3
"""
Download / prepare pretrained model weights for the AntiDeepfake AI detectors.

Weights are written to ``backend/weights/`` (override with ``ADF_MODEL_DIR``).
The detectors that use weights are:

* ``face_forgery_ffpp.pth``  — FaceForensics++ face-forgery classifier.
* ``gan_fingerprint.pth``    — GAN/diffusion source classifier.

Because the canonical FaceForensics++ weights are gated behind a research
agreement, this script supports three modes:

1. ``--url-face <URL>`` / ``--url-gan <URL>`` — download from a URL you provide
   (e.g. your own mirror once you have accepted the FF++ license).
2. ``ADF_FACE_WEIGHTS_URL`` / ``ADF_GAN_WEIGHTS_URL`` env vars — same as above.
3. Default (no URL) — generate small, randomly-initialised placeholder
   checkpoints so the full pipeline is runnable end-to-end for demos. These
   placeholders are clearly marked and should be replaced with real weights for
   production accuracy.

The detectors fall back to documented heuristics when no weights are present,
so this script is optional for a demo but recommended for real deployments.

Usage
-----
    python scripts/download_models.py                 # placeholders
    python scripts/download_models.py --url-face URL  # real FF++ weights
    ADF_FACE_WEIGHTS_URL=URL python scripts/download_models.py
"""
from __future__ import annotations

import argparse
import os
import sys
import urllib.request
from pathlib import Path

# Resolve the weights dir the same way backend/config.py does, without
# importing the backend (so this script runs with zero deps for placeholders
# unless torch is needed).
MODEL_DIR = Path(os.getenv("ADF_MODEL_DIR", str(Path(__file__).resolve().parent.parent / "backend" / "weights")))
MODEL_DIR.mkdir(parents=True, exist_ok=True)


def _download(url: str, dest: Path) -> None:
    print(f"Downloading {url} -> {dest}")
    with urllib.request.urlopen(url) as resp, dest.open("wb") as out:
        total = int(resp.headers.get("Content-Length", 0))
        read = 0
        while chunk := resp.read(1 << 20):
            out.write(chunk)
            read += len(chunk)
            if total:
                pct = 100 * read / total
                print(f"\r  {read/1e6:.1f}/{total/1e6:.1f} MB ({pct:.0f}%)", end="")
        print()
    print(f"Saved {dest} ({dest.stat().st_size/1e6:.1f} MB)")


def _placeholder_face(dest: Path) -> None:
    """Create a randomly-initialised EfficientNet-B4 FF++ head checkpoint."""
    try:
        import torch
        import torch.nn as nn
        from torchvision import models as tv_models
    except Exception:
        print("  torch/torchvision not installed; skipping face placeholder.")
        print("  (face_forgery detector will use its heuristic fallback.)")
        return
    net = tv_models.efficientnet_b4(weights=None)
    in_f = net.classifier[1].in_features
    net.classifier = nn.Sequential(nn.Dropout(0.3), nn.Linear(in_f, 2))
    torch.save({"state_dict": net.state_dict(), "placeholder": True}, dest)
    print(f"Wrote PLACEHOLDER {dest} — replace with real FF++ weights for production.")


def _placeholder_gan(dest: Path) -> None:
    """Create a randomly-initialised GAN-fingerprint classifier checkpoint."""
    try:
        import torch
        import torch.nn as nn
    except Exception:
        print("  torch not installed; skipping GAN placeholder.")
        print("  (gan_fingerprint detector will use its heuristic fallback.)")
        return
    net = nn.Sequential(
        nn.Conv2d(1, 16, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
        nn.Conv2d(16, 32, 3, padding=1), nn.ReLU(), nn.AdaptiveAvgPool2d(4),
        nn.Flatten(), nn.Linear(32 * 4 * 4, 64), nn.ReLU(), nn.Linear(64, 6),
    )
    torch.save({"state_dict": net.state_dict(), "placeholder": True}, dest)
    print(f"Wrote PLACEHOLDER {dest} — replace with trained weights for production.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Download AntiDeepfake AI model weights")
    parser.add_argument("--url-face", default=os.getenv("ADF_FACE_WEIGHTS_URL"))
    parser.add_argument("--url-gan", default=os.getenv("ADF_GAN_WEIGHTS_URL"))
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    args = parser.parse_args()

    face_dest = MODEL_DIR / "face_forgery_ffpp.pth"
    gan_dest = MODEL_DIR / "gan_fingerprint.pth"

    # Face forgery weights
    if face_dest.exists() and not args.force:
        print(f"{face_dest} already exists (use --force to overwrite).")
    elif args.url_face:
        _download(args.url_face, face_dest)
    else:
        _placeholder_face(face_dest)

    # GAN fingerprint weights
    if gan_dest.exists() and not args.force:
        print(f"{gan_dest} already exists (use --force to overwrite).")
    elif args.url_gan:
        _download(args.url_gan, gan_dest)
    else:
        _placeholder_gan(gan_dest)

    print("\nDone. Weights directory:", MODEL_DIR)
    print("Tip: accept the FaceForensics++ license and pass --url-face to use")
    print("real pretrained weights: https://github.com/ondyari/FaceForensics")
    return 0


if __name__ == "__main__":
    sys.exit(main())

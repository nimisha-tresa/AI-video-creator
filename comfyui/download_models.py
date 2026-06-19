#!/usr/bin/env python3
"""Download local video/image models (SD 1.5 + AnimateDiff motion adapter)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

MODELS_DIR = Path("/app/models")
if not MODELS_DIR.exists():
    MODELS_DIR = Path(__file__).resolve().parent / "models"

SD15_REPO = "runwayml/stable-diffusion-v1-5"
MOTION_REPO = "guoyww/animatediff-motion-adapter-v1-5-2"

SD15_DIR = MODELS_DIR / "stable-diffusion-v1-5"
MOTION_DIR = MODELS_DIR / "animatediff-motion-adapter-v1-5-2"


def _has_files(path: Path, min_files: int = 3) -> bool:
    if not path.exists():
        return False
    files = [p for p in path.rglob("*") if p.is_file()]
    return len(files) >= min_files


def models_ready() -> bool:
    return _has_files(SD15_DIR) and _has_files(MOTION_DIR, min_files=2)


def download_all(force: bool = False) -> None:
    from huggingface_hub import snapshot_download

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    if force or not _has_files(SD15_DIR):
        print(f"Downloading {SD15_REPO} -> {SD15_DIR}")
        snapshot_download(
            repo_id=SD15_REPO,
            local_dir=str(SD15_DIR),
            local_dir_use_symlinks=False,
        )
        print("SD 1.5 download complete.")

    if force or not _has_files(MOTION_DIR, min_files=2):
        print(f"Downloading {MOTION_REPO} -> {MOTION_DIR}")
        snapshot_download(
            repo_id=MOTION_REPO,
            local_dir=str(MOTION_DIR),
            local_dir_use_symlinks=False,
        )
        print("AnimateDiff motion adapter download complete.")

    if models_ready():
        print("All local models ready.")
    else:
        print("Model download finished but verification failed.", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download local AI video models")
    parser.add_argument("--check-only", action="store_true", help="Exit 0 if models exist, 1 otherwise")
    parser.add_argument("--force", action="store_true", help="Re-download even if present")
    args = parser.parse_args()

    if args.check_only:
        sys.exit(0 if models_ready() else 1)

    download_all(force=args.force)


if __name__ == "__main__":
    main()

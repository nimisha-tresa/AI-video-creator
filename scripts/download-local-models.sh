#!/usr/bin/env bash
# Download local AnimateDiff + SD 1.5 models (~6 GB) for free offline video generation.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== Download local AI video models (AnimateDiff + SD 1.5) ==="
echo "Target: $ROOT/comfyui/models"
echo

docker compose -f "$ROOT/infra/docker-compose.yml" build comfyui
docker compose -f "$ROOT/infra/docker-compose.yml" run --rm comfyui python download_models.py

echo
echo "Done. Restart ComfyUI:"
echo "  docker compose -f infra/docker-compose.yml up -d comfyui worker api"

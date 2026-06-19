# Download local AnimateDiff + SD 1.5 models (~6 GB) for free offline video generation.
# Run after trying Pollinations, or when you want a fully free backup engine.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

Write-Host "=== Download local AI video models (AnimateDiff + SD 1.5) ===" -ForegroundColor Cyan
Write-Host "Target: $Root\comfyui\models"
Write-Host ""

docker compose -f "$Root\infra\docker-compose.yml" build comfyui
docker compose -f "$Root\infra\docker-compose.yml" run --rm comfyui python download_models.py

Write-Host ""
Write-Host "Done. Restart ComfyUI to enable local fallback:" -ForegroundColor Green
Write-Host "  docker compose -f infra/docker-compose.yml up -d comfyui worker api"

#!/bin/bash
set -euo pipefail
cd /app
if [ "${AUTO_DOWNLOAD_MODELS:-false}" = "true" ]; then
  python download_models.py --check-only || python download_models.py || true
fi
exec python server.py

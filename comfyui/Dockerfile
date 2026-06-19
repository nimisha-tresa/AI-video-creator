# Local ComfyUI-compatible server with AnimateDiff (SD 1.5) models
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        git \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip

# CPU PyTorch works everywhere; swap to CUDA index for GPU hosts
ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir \
        torch torchvision \
        --index-url ${TORCH_INDEX}

RUN pip install --no-cache-dir \
        diffusers>=0.30.0 \
        transformers>=4.44.0 \
        accelerate>=0.33.0 \
        safetensors>=0.4.0 \
        huggingface_hub>=0.24.0 \
        aiohttp>=3.9.0 \
        imageio[ffmpeg]>=2.34.0 \
        pillow>=10.0.0

COPY download_models.py local_engine.py server.py prompt_engine.py /app/

RUN mkdir -p /app/models /app/output

EXPOSE 8188

ENV COMFYUI_ENGINE=auto \
    AUTO_DOWNLOAD_MODELS=false \
    PYTHONUNBUFFERED=1

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8188/status')" || exit 1

CMD ["python", "/app/server.py"]

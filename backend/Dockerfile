FROM python:3.11-slim

WORKDIR /app

# System deps
ARG INSTALL_SYSTEM_DEPS=false
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ENV HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    NO_PROXY=${NO_PROXY} \
    http_proxy=${HTTP_PROXY} \
    https_proxy=${HTTPS_PROXY} \
    no_proxy=${NO_PROXY}
RUN if [ "$INSTALL_SYSTEM_DEPS" = "true" ]; then \
        apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl libpq-dev ffmpeg \
        && rm -rf /var/lib/apt/lists/*; \
    else \
        echo "Skipping system dependencies installation"; \
    fi

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ComfyUI Mock - Minimal HTTP server for testing
# Real ComfyUI would be installed here; using mock for development

FROM python:3.11-slim

WORKDIR /app

# Copy mock server script
COPY mock_server.py /app/mock_server.py

# Expose port
EXPOSE 8188

# Health check
HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=2 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8188/status')" || exit 1

# Start mock ComfyUI
CMD ["python3", "/app/mock_server.py"]

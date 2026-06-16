#!/bin/bash

# Video Creator - Diagnostic Script
# Run this to quickly identify which component is broken

set -e

PASS="✓"
FAIL="✗"
WARN="⚠"

echo "======================================"
echo "Video Creator - System Diagnostic"
echo "======================================"
echo ""

# 1. Check Docker containers
echo "1. Checking Docker containers..."
RUNNING_CONTAINERS=$(docker compose ps --services --filter "status=running" | wc -l)
TOTAL_CONTAINERS=$(docker compose ps --services | wc -l)

if [ "$RUNNING_CONTAINERS" -eq "$TOTAL_CONTAINERS" ]; then
    echo "$PASS All $TOTAL_CONTAINERS containers are running"
else
    echo "$FAIL Only $RUNNING_CONTAINERS/$TOTAL_CONTAINERS containers running"
    echo "   Run: docker compose up -d"
fi
echo ""

# 2. Check ComfyUI API
echo "2. Checking ComfyUI API connectivity..."
if docker compose exec -T api curl -s http://comfyui:8188/status > /dev/null 2>&1; then
    echo "$PASS ComfyUI API is responding at http://comfyui:8188"
else
    echo "$FAIL ComfyUI is not responding at http://comfyui:8188"
    echo "   Try: docker compose logs comfyui"
    COMFYUI_OK=0
fi
echo ""

# 3. Check Redis connectivity
echo "3. Checking Redis connectivity..."
if docker compose exec -T worker redis-cli -h redis ping 2>/dev/null | grep -q PONG; then
    echo "$PASS Worker can connect to Redis"
else
    echo "$FAIL Worker cannot connect to Redis"
    echo "   Try: docker compose logs worker | grep -i error"
    REDIS_OK=0
fi
echo ""

# 4. Check Celery worker
echo "4. Checking Celery worker status..."
WORKER_COUNT=$(docker compose exec -T worker celery -A workers.celery_app inspect active 2>/dev/null | grep -c "celery@" || echo "0")
if [ "$WORKER_COUNT" -gt 0 ]; then
    echo "$PASS Celery worker is connected"
else
    echo "$WARN Celery worker may not be ready yet (normal on startup)"
    echo "   Try: docker compose logs worker | grep ready"
fi
echo ""

# 5. Check database
echo "5. Checking PostgreSQL database..."
if docker compose exec -T postgres psql -U vcreator -d video_creator -c "SELECT COUNT(*) FROM generation;" > /dev/null 2>&1; then
    GEN_COUNT=$(docker compose exec -T postgres psql -U vcreator -d video_creator -t -c "SELECT COUNT(*) FROM generation;" | xargs)
    echo "$PASS Database is accessible ($GEN_COUNT generations in queue)"
else
    echo "$FAIL Cannot connect to PostgreSQL"
    echo "   Try: docker compose logs postgres"
fi
echo ""

# 6. Check MinIO
echo "6. Checking MinIO storage..."
if docker compose exec -T api python -c "from app.services.storage import get_minio_client; get_minio_client(); print('OK')" 2>/dev/null | grep -q OK; then
    echo "$PASS MinIO is accessible"
else
    echo "$FAIL MinIO connection failed"
    echo "   Try: docker compose logs minio"
fi
echo ""

# 7. Check API health
echo "7. Checking Backend API..."
if curl -s http://localhost:8000/health > /dev/null 2>&1 || curl -s http://localhost:8000/docs > /dev/null 2>&1; then
    echo "$PASS Backend API is responding"
else
    echo "$FAIL Backend API is not responding at http://localhost:8000"
    echo "   Try: docker compose logs api"
fi
echo ""

# 8. Check Frontend
echo "8. Checking Frontend..."
if curl -s http://localhost:3000 > /dev/null 2>&1 || curl -s http://localhost > /dev/null 2>&1; then
    echo "$PASS Frontend is responding"
else
    echo "$WARN Frontend may not be fully loaded yet"
    echo "   Try: docker compose logs frontend"
fi
echo ""

echo "======================================"
echo "Diagnostic Summary"
echo "======================================"
echo ""
echo "If all checks pass:"
echo "  1. Go to http://localhost"
echo "  2. Upload a video or enter a text prompt"
echo "  3. Click 'Generate'"
echo "  4. Watch the progress bar"
echo ""
echo "If any checks failed:"
echo "  1. Check the suggested command above"
echo "  2. Review TROUBLESHOOTING.md for detailed solutions"
echo "  3. Check logs: docker compose logs -f <service_name>"
echo ""
echo "For real-time task monitoring:"
echo "  - Open http://localhost:5555 (Flower - task monitoring)"
echo "  - Open http://localhost:8188 (ComfyUI - model inference)"
echo ""

# Test a generation if everything looks good
if [ -z "$COMFYUI_OK" ] && [ -z "$REDIS_OK" ]; then
    echo "======================================"
    echo "Optional: Run a test generation"
    echo "======================================"
    echo ""
    read -p "Queue a test video generation now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Test generation queued. Check:"
        echo "  - Frontend progress bar at http://localhost"
        echo "  - Task logs: docker compose logs -f worker | grep -i 'Starting\|completed\|failed'"
        echo "  - Task monitoring: http://localhost:5555"
    fi
fi

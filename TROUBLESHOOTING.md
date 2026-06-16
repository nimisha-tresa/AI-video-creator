# Video Creator - Troubleshooting Guide

## Quick Diagnosis: Video Generation Not Working

If you upload a video generation request but see no progress or output, use this step-by-step diagnostic.

### Step 1: Verify All Services Are Running

```bash
# Check if all containers are running
docker compose ps

# Expected output: all containers should be "Up"
#  - postgres
#  - redis
#  - minio
#  - comfyui (CRITICAL for video/image generation)
#  - api
#  - worker (CRITICAL for processing tasks)
#  - celery-beat
#  - flower (optional, for task monitoring)
#  - frontend
#  - nginx
```

If any container is not running, restart all:
```bash
docker compose down
docker compose up -d
```

### Step 2: Check ComfyUI Connectivity

ComfyUI must be accessible at `http://localhost:8188` from the backend services.

```bash
# Option A: Test from your local machine
curl -v http://localhost:8188/status

# Option B: Test from inside the API container
docker compose exec api curl -v http://comfyui:8188/status

# Expected response: HTTP 200 with JSON containing {"status": "OK"} or similar
```

If ComfyUI is not responding:
- Check if the comfyui container is running: `docker compose ps comfyui`
- Check ComfyUI logs: `docker compose logs comfyui`
- Verify ComfyUI port: `docker compose port comfyui 8188`

### Step 3: Verify Celery Worker Is Running

The Celery worker must be connected to Redis and listening for tasks.

```bash
# Option A: Check Flower UI (task monitoring dashboard)
# Open browser to: http://localhost:5555
# Look for "Active Tasks" or "Workers" section
# Should show at least 1 worker connected

# Option B: Check worker logs
docker compose logs worker

# Expected: Should see messages like:
#   "Connected to redis://redis:6379"
#   "celery@worker ready"
#   "Received task workers.tasks.video_gen.text_to_video[...]"
```

If worker is not connected:
```bash
# Restart worker
docker compose restart worker

# Check for connection errors in logs
docker compose logs worker | grep -i "error\|failed\|connection"
```

### Step 4: Trigger a Test Generation and Monitor Logs

1. **Queue a generation** in the UI:
   - Prompt: "a dog running on a beach"
   - Type: "Text to Video"
   - Click "Generate"

2. **Monitor worker logs in real-time**:
   ```bash
   docker compose logs -f worker | grep -E "Starting video|fetched|Acquiring GPU|Building workflow|Submitting to ComfyUI|Workflow completed|failed"
   ```

3. **Look for these log patterns** (in order):
   ```
   Starting video generation id=<ID> type=text_to_video
   Generation fetched id=<ID> owner_id=<USER_ID>
   Acquiring GPU slot id=<ID>
   GPU slot acquired id=<ID> slot=0
   Building workflow id=<ID> type=text_to_video
   Submitting to ComfyUI id=<ID> url=http://localhost:8188
   Connecting to ComfyUI url=http://comfyui:8188 timeout=300
   Workflow queued successfully prompt_id=<ID>
   Workflow completed id=<ID> has_url=true
   Updating DB with completion id=<ID>
   Video generation completed successfully id=<ID> elapsed=<SECONDS>
   ```

### Step 5: Identify Where Generation Fails

#### If logs show "Starting video generation" but stop after step 1-2:

```
Starting video generation id=xxx type=text_to_video
Failed to fetch generation from DB id=xxx error=...
```

**Solution**: Database connection issue. Check:
- `docker compose logs postgres`
- Verify postgres is up and database exists: `docker compose exec postgres psql -U vcreator -d video_creator -c "SELECT COUNT(*) FROM generation;"`

#### If logs show "Building workflow" but fail at "Submitting to ComfyUI":

```
Submitting to ComfyUI id=xxx url=http://localhost:8188
Failed to connect/queue to ComfyUI url=http://comfyui:8188 error=Connection refused
```

**Solution**: ComfyUI not running or not accessible. Check:
- `docker compose logs comfyui | tail -20`
- Test direct connection: `docker compose exec api curl -v http://comfyui:8188/status`
- Verify network: `docker network inspect <network_name> | grep comfyui`

#### If logs show "Workflow queued successfully" but then timeout:

```
Workflow queued successfully prompt_id=abc123
Workflow execution failed or timed out prompt_id=abc123 error_type=TimeoutError
```

**Solution**: ComfyUI workflow execution is too slow or models aren't loaded. Check:
- ComfyUI logs: `docker compose logs comfyui | tail -50` (look for model loading/errors)
- GPU memory: `docker compose exec comfyui nvidia-smi` (if GPU available)
- Disk space: `docker compose exec comfyui df -h` (needs space for model cache)
- Increase timeout in `.env`: `COMFYUI_TIMEOUT=600` (in seconds)

#### If logs show "Output downloaded" but fail on "Updating DB":

```
Output downloaded successfully size_mb=45.3
Updating DB with completion id=xxx
Failed to update DB with error db_error=...
```

**Solution**: Database or storage issue. Check:
- Database connectivity: `docker compose exec postgres psql -U vcreator -d video_creator -c "SELECT 1;"`
- MinIO connectivity: `docker compose exec api python -c "from app.services.storage import get_presigned_url; print('OK')"`

### Step 6: Check Frontend UI Update

1. **Generation appears in the UI**:
   - If generation appears in the queue with "Processing" status → task is being tracked
   - If no generation appears → API/frontend issue, not worker issue

2. **Progress bar updates**:
   - Check browser DevTools Console for errors
   - Check network tab - frontend should poll `/api/generations` every 2.5s
   - Generation record should have `progress` field updating (0.05 → 1.0)

3. **Output URL appears**:
   - When generation completes, `output_url` field should populate
   - Frontend displays download/preview link

---

## Common Issues & Solutions

### Issue: "ComfyUI connection failed"

**Cause**: Backend cannot reach ComfyUI container.

**Steps**:
1. Verify `comfyui` service is running: `docker compose ps comfyui`
2. Check ComfyUI logs for errors: `docker compose logs comfyui`
3. Test network connectivity:
   ```bash
   docker compose exec api curl http://comfyui:8188/status
   ```

### Issue: "Workflow execution timed out"

**Cause**: ComfyUI taking too long to process (slow GPU, missing models, or system overloaded).

**Steps**:
1. Check available GPU VRAM:
   ```bash
   docker compose exec comfyui nvidia-smi
   ```
2. Check ComfyUI models directory has required models:
   - `v1-5-pruned-emaonly.ckpt` (for video generation)
   - `sd_xl_base_1.0.safetensors` (for image generation)
3. Check system resources:
   ```bash
   docker stats  # Monitor CPU/memory usage
   ```
4. Increase timeout in backend config or `.env`:
   ```
   COMFYUI_TIMEOUT=600  # 10 minutes instead of 5
   ```

### Issue: "No output produced by ComfyUI workflow"

**Cause**: ComfyUI workflow executed but didn't produce images/videos.

**Steps**:
1. Check ComfyUI logs for workflow errors:
   ```bash
   docker compose logs comfyui | grep -i "error\|failed"
   ```
2. Verify workflow nodes exist in ComfyUI (requires AnimateDiff nodes for video):
   ```bash
   curl http://localhost:8188/system
   # Should list: ADE_AnimateDiffLoaderWithContext, ADE_AnimateDiffCombine
   ```
3. Manually test workflow in ComfyUI UI:
   - Open http://localhost:8188 in browser
   - Load a txt2video example workflow
   - Run it to verify ComfyUI works standalone

### Issue: Frontend shows "Processing" forever (no progress updates)

**Cause**: Either worker never started processing, or progress updates aren't being published.

**Steps**:
1. Check Redis connectivity:
   ```bash
   docker compose exec worker redis-cli -h redis ping
   # Should respond with PONG
   ```
2. Check if Celery task was ever created:
   ```bash
   docker compose logs worker | grep "Starting video generation"
   ```
3. Check if progress is being published:
   ```bash
   docker compose exec redis redis-cli SUBSCRIBE "generation:progress:*"
   # Queue a new generation, should see messages
   ```

### Issue: "generation not found" error

**Cause**: Worker queried database before generation record was created.

**Steps**:
1. Check database consistency:
   ```bash
   docker compose exec postgres psql -U vcreator -d video_creator -c "SELECT id, status FROM generation ORDER BY created_at DESC LIMIT 5;"
   ```
2. Check for database connection pooling issues:
   - Restart API: `docker compose restart api`
   - Restart Worker: `docker compose restart worker`

---

## Viewing Detailed Logs

### Real-time Worker Processing

```bash
# Follow all worker logs with generation task markers
docker compose logs -f worker | grep -E "(Starting|fetched|GPU|workflow|ComfyUI|completed|failed|error)"
```

### Real-time ComfyUI Logs

```bash
# Follow ComfyUI logs (useful for model loading, execution errors)
docker compose logs -f comfyui | grep -E "(ERROR|WARNING|loaded|execution)"
```

### Database Query History

```bash
# Check latest generations and their status
docker compose exec postgres psql -U vcreator -d video_creator << EOF
SELECT 
  id, 
  type, 
  status, 
  progress, 
  error_message, 
  created_at 
FROM generation 
ORDER BY created_at DESC 
LIMIT 10;
EOF
```

### Redis Task Queue Status

```bash
# View tasks in queue
docker compose exec redis redis-cli LRANGE celery 0 -1 | head -20

# View pending tasks via Flower (http://localhost:5555)
```

---

## Architecture Diagram: Video Generation Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ Frontend (React)                                                │
│ - User enters prompt, clicks "Generate"                        │
│ - POST /api/generations with type="text_to_video"             │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ Backend API (FastAPI)                                           │
│ - Create Generation record in DB (status=PENDING)              │
│ - Queue Celery task: dispatch_generation.delay(gen_id)         │
│ - Return generation to frontend                                │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ Celery Worker Process                                           │
│ 1. Fetch generation from DB (mark as PROCESSING)               │
│ 2. Route based on type:                                        │
│    - text_to_video → workers.tasks.video_gen.text_to_video    │
│ 3. Acquire GPU slot from gpu_manager                           │
│ 4. Build ComfyUI workflow (AnimateDiff config)                │
│ 5. Connect to ComfyUI, submit workflow                        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ ComfyUI (Stable Diffusion + AnimateDiff)                       │
│ - Receive workflow JSON from worker                            │
│ - Load models (may take 30-60s on first run)                   │
│ - Generate video frames using text prompt                      │
│ - Encode to MP4 video                                          │
│ - Save to output folder                                        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ Backend Worker (continued)                                      │
│ 6. Download MP4 from ComfyUI output folder                    │
│ 7. Upload to MinIO bucket (object storage)                    │
│ 8. Get presigned URL (valid for 24h)                          │
│ 9. Update Generation record:                                   │
│    - status=COMPLETED                                          │
│    - output_url=<presigned_url>                               │
│    - progress=1.0                                              │
│ 10. Publish progress via Redis pub/sub                        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ Frontend Polling Loop                                           │
│ - Every 2.5s: GET /api/generations                            │
│ - Receive updated generation with progress & output_url       │
│ - Display progress bar                                         │
│ - When complete, show download/preview link                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Testing Individual Components

### Test 1: ComfyUI Standalone

```bash
# Check if ComfyUI API is reachable
curl -v http://localhost:8188/status

# List available system info (should include model names)
curl http://localhost:8188/system | jq .

# List queue (should be empty if idle)
curl http://localhost:8188/queue | jq .
```

### Test 2: Redis Connection

```bash
# Check if worker can reach Redis
docker compose exec worker redis-cli -h redis ping

# Monitor pub/sub messages (in one terminal)
docker compose exec redis redis-cli SUBSCRIBE "generation:progress:*"

# In another terminal, queue a generation and watch messages appear
```

### Test 3: Database Connectivity

```bash
# Check if generation record exists
docker compose exec postgres psql -U vcreator -d video_creator -c \
  "SELECT id, type, status, progress, created_at FROM generation ORDER BY created_at DESC LIMIT 1;"

# Check if you can insert a test record
docker compose exec postgres psql -U vcreator -d video_creator -c \
  "INSERT INTO generation (id, owner_id, type, prompt, status, width, height, created_at) VALUES ('test-123', 'user-1', 'text_to_video', 'test', 'pending', 512, 512, NOW()) RETURNING id;"
```

### Test 4: MinIO Connectivity

```bash
# Check if buckets exist
docker compose exec api python -c "from app.services.storage import get_minio_client; c = get_minio_client(); print([b.name for b in c.list_buckets()])"

# List output bucket contents
docker compose exec api python -c "from app.services.storage import get_minio_client; c = get_minio_client(); print([obj.object_name for obj in c.list_objects('outputs')])"
```

---

## Performance Tuning

### Slow Video Generation?

- **Increase GPU allocation**: Edit `docker-compose.yml`, add `deploy.resources.reservations.devices[0].device_ids: ["0"]` for specific GPU
- **Optimize model**: Use smaller model or reduce `num_frames` (e.g., 16 → 8)
- **Increase worker count**: Run multiple worker containers for parallel processing
- **Increase timeout**: Set `COMFYUI_TIMEOUT=600` for longer inference

### High Memory Usage?

- **Model offloading**: Enable in ComfyUI (`--normalvram` or `--lowvram` flags)
- **Smaller models**: Use pruned/quantized model files
- **Reduce batch size**: Lower `num_frames` parameter

### Disk Space Issues?

- **Clean ComfyUI cache**: `docker compose exec comfyui rm -rf /workspace/models/checkpoints/cache`
- **Remove temp files**: `docker compose exec comfyui rm -rf /tmp/*`
- **Monitor disk**: `docker compose exec comfyui df -h`

---

## Getting Help

1. **Check logs first**: `docker compose logs -f`
2. **Test each component individually** (see "Testing Individual Components" above)
3. **Check this troubleshooting guide** for your specific error message
4. **Review recent changes**: Any Docker config changes? Model updates? API changes?
5. **Isolate the problem**: Is it frontend? API? Worker? ComfyUI? Database?


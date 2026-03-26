# API Reference

The REST API is implemented in `api/main.py` using FastAPI. It handles video upload, job status polling, cache management, and annotated video download.

## Endpoints

### POST `/upload`

Submit a video clip for processing.

**Request** (multipart/form-data):
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | File | Yes | Video file (.mp4 or .mov) |
| `test_type` | string | Yes | One of: `explosiveness`, `speed`, `fitness`, `agility`, `balance` |
| `config_override` | string | No | JSON string of config parameter overrides |
| `enable_pose` | boolean | No | Override pose estimation toggle |
| `enable_ocr` | boolean | No | Override OCR toggle |

**Response** (200):
```json
{
    "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "status": "queued"
}
```

**Behaviour**:
1. Saves uploaded video to `UPLOAD_DIR` (default `/tmp/vigour_uploads/`)
2. Enqueues `process_clip` Celery task
3. Returns immediately with job_id for polling

---

### GET `/results/{job_id}`

Poll job status and retrieve results.

**Response** (200):
```json
{
    "job_id": "a1b2c3d4-...",
    "status": "complete",
    "results": [
        {
            "student_bib": 7,
            "track_id": 1,
            "test_type": "explosiveness",
            "metric_value": 34.2,
            "metric_unit": "cm",
            "attempt_number": 1,
            "confidence_score": 0.92,
            "flags": [],
            "raw_data": { ... }
        }
    ]
}
```

**Status Values**:
| Status | Meaning |
|--------|---------|
| `pending` | Queued, not yet started |
| `processing` | Pipeline running (stage info may be available) |
| `complete` | All stages done, results available |
| `failed` | Pipeline error (check worker logs) |

---

### GET `/annotated/{job_id}`

Download the annotated video output.

**Response**:
- `200`: Streams annotated MP4 video
- `404`: Pipeline not complete or video not found

---

### GET `/health`

Liveness check.

**Response** (200):
```json
{
    "status": "ok",
    "version": "0.2.0"
}
```

---

### GET `/cache`

List all cached jobs.

**Response** (200):
```json
{
    "jobs": [
        {
            "job_id": "a1b2c3d4-...",
            "stages_cached": ["ingest", "detect", "track"],
            "size_mb": 12.4
        }
    ],
    "total": 3
}
```

---

### GET `/cache/{job_id}`

Inspect cache for a specific job.

**Response** (200):
```json
{
    "job_id": "a1b2c3d4-...",
    "test_type": "explosiveness",
    "stages_cached": ["ingest", "detect", "track", "pose"],
    "size_mb": 12.4,
    "available_stages": ["ingest", "detect", "track", "pose", "ocr", "calibrate", "results"]
}
```

---

### DELETE `/cache/{job_id}`

Clear entire cache for a job.

**Response** (200):
```json
{
    "job_id": "a1b2c3d4-...",
    "status": "cache_cleared"
}
```

---

### DELETE `/cache/{job_id}/{stage}`

Invalidate from a specific stage onwards (cascading downstream).

**Valid Stages**: `ingest`, `detect`, `track`, `pose`, `ocr`, `calibrate`, `results`

**Response** (200):
```json
{
    "job_id": "a1b2c3d4-...",
    "status": "invalidated",
    "stages_invalidated": ["track", "pose", "ocr", "calibrate", "results"],
    "stages_retained": ["ingest", "detect"]
}
```

---

## Celery Worker Task

The worker (`worker/celery_app.py`) exposes a single Celery task:

```python
@celery.task(bind=True)
def process_clip(
    self,
    job_id: str,
    video_path: str,
    test_type: str,
    config_override: str | None = None,
    enable_pose: bool | None = None,
    enable_ocr: bool | None = None,
) -> list[dict]:
```

**Execution Flow**:
1. Load geometry config from `configs/test_configs/{test_type}.json`
2. Apply `config_override` (JSON merge)
3. Run each stage sequentially:
   - Check cache first (skip if cached, unless `PIPELINE_FORCE_RERUN=1`)
   - Execute stage, save to cache
   - Update Celery task state (for progress polling)
4. Attach resolved bibs to track objects
5. Select and run test-specific extractor
6. Generate annotated video + results JSON
7. Return `list[TestResult]` as JSON-serialisable dicts

**Environment Variables**:

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379/0` | Celery broker + backend |
| `CONFIGS_DIR` | `configs/test_configs` | Test config directory |
| `OUTPUT_DIR` | `data/annotated` | Annotated output directory |
| `CACHE_DIR` | `data/cache` | Pipeline cache root |
| `UPLOAD_DIR` | `/tmp/vigour_uploads` | Temp video storage |
| `PIPELINE_FORCE_RERUN` | `0` | Bypass all caches |
| `ENABLE_POSE` | `1` | Global pose toggle |
| `ENABLE_OCR` | `1` | Global OCR toggle |
| `DEVICE` | `cuda` | `cuda` or `cpu` |
| `DEFAULT_FPS` | `15` | Default ingestion FPS |

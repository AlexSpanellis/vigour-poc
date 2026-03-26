# Infrastructure & Deployment

## Local Development Stack

### Docker Compose (`docker-compose.yml`)

Four services for local development:

```
┌──────────┐     ┌──────────┐
│ PostgreSQL│     │  Redis 7 │
│    15     │     │          │
│ port 5432 │     │ port 6379│
└─────┬─────┘     └────┬─────┘
      │                │
      │    ┌───────────┘
      │    │
┌─────┴────┴──┐     ┌──────────────┐
│  FastAPI     │     │ Celery Worker │
│  (api)       │     │ (worker)      │
│  port 8000   │     │ GPU: 1× nvidia│
└──────────────┘     └──────────────┘
```

**Database**: `postgres:15-alpine` with `vigour` database, initialised from `db/schema.sql`
**Message Broker**: `redis:7-alpine` for Celery task queue and result backend
**API**: `python:3.11-slim` running FastAPI on port 8000
**Worker**: `nvcr.io/nvidia/pytorch:24.01-py3` (CUDA 12.1) running Celery with 1 GPU, concurrency=1

### Local Setup Steps

```bash
# 1. Clone & create virtualenv
git clone ... && cd vigour-poc
python3 -m venv .venv && source .venv/bin/activate

# 2. Install dependencies (ORDER MATTERS)
pip install "setuptools==60.2.0"
pip install torch==2.4.0 torchvision==0.19.0 --index-url https://download.pytorch.org/whl/cu121
pip install openmim
mim install mmcv==2.2.0 mmengine
pip install -r requirements.txt
pip install bytetracker --no-deps  # lap>=0.5.12 must be installed first

# 3. Configure environment
cp .env.example .env  # Edit as needed

# 4. Start infrastructure
docker-compose up -d db redis

# 5. Initialise database
psql postgresql://vigour:vigour@localhost:5432/vigour -f db/schema.sql

# 6. Start worker
celery -A worker.celery_app worker --concurrency=1 --loglevel=info

# 7. Start API
fastapi dev api/main.py
```

### Dependency Installation Order

This is critical — wrong order causes build failures:

1. `setuptools` (build system)
2. `torch` + `torchvision` (CUDA-specific wheels)
3. `openmim` → `mim install mmcv mmengine` (requires torch to select correct wheel)
4. `requirements.txt` (everything else)
5. `bytetracker --no-deps` (after `lap>=0.5.12` from requirements.txt)

---

## Production Deployment (GCP)

### Terraform Configuration (`infra/main.tf`)

Provisions a complete GCP stack:

```
┌─────────────────────────────────────────────┐
│              Google Cloud Platform           │
│                                             │
│  ┌─────────────┐  ┌──────────────────────┐ │
│  │ Cloud Storage│  │ Compute Engine       │ │
│  │ (videos +   │  │ g2-standard-4        │ │
│  │  results)   │  │ 1× NVIDIA L4 GPU     │ │
│  │  EU region  │  │ 100GB disk           │ │
│  │  30-day TTL │  │ PyTorch 2.1 + CUDA   │ │
│  └─────────────┘  └──────────────────────┘ │
│                                             │
│  ┌─────────────┐  ┌──────────────────────┐ │
│  │ Cloud SQL   │  │ Memorystore (Redis)  │ │
│  │ PostgreSQL  │  │ BASIC tier, 1GB      │ │
│  │ 15          │  │                      │ │
│  │ db-f1-micro │  │                      │ │
│  └─────────────┘  └──────────────────────┘ │
└─────────────────────────────────────────────┘
```

### Resources

| Resource | Type | Spec | Notes |
|----------|------|------|-------|
| **Storage** | Cloud Storage | EU region, 30-day lifecycle | Video uploads + results |
| **Database** | Cloud SQL | PostgreSQL 15, db-f1-micro | POC-only: 0.0.0.0/0 access |
| **Redis** | Memorystore | BASIC tier, 1GB | Celery broker + backend |
| **Compute** | Compute Engine | g2-standard-4, 1× L4 GPU | ML inference worker |

### VM Configuration
- **Image**: `ml-images/deeplearning-platform-release/pytorch-latest-gpu`
- **Disk**: 100 GB SSD
- **GPU**: 1× NVIDIA L4 (24GB VRAM)
- **Region**: `europe-west4` (default)
- **Startup**: Installs NVIDIA drivers + Docker

---

## Docker Images

### API (`docker/Dockerfile.api`)
```dockerfile
FROM python:3.11-slim
# System deps for OpenCV
RUN apt-get install -y libglib2.0-0 libsm6 libxrender1 libxext6
# Python deps (API subset only)
COPY requirements.txt .
RUN pip install ... (fastapi, celery, redis)
EXPOSE 8000
CMD ["fastapi", "run", "api/main.py", "--host", "0.0.0.0", "--port", "8000"]
```

### Worker (`docker/Dockerfile.worker`)
```dockerfile
FROM nvcr.io/nvidia/pytorch:24.01-py3  # CUDA 12.1 + PyTorch 2.4
# System deps
RUN apt-get install -y libglib2.0-0 libsm6 libxrender1 libxext6 ffmpeg
# Full ML dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt
RUN pip install openmim && mim install mmcv mmengine
CMD ["celery", "-A", "worker.celery_app", "worker", "--concurrency=1", "--loglevel=info"]
```

**Note**: Worker uses `--concurrency=1` to prevent GPU VRAM conflicts when processing multiple clips.

---

## Environment Variables

### Required

| Variable | Example | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://vigour:vigour@localhost:5432/vigour` | PostgreSQL connection |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis for Celery |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `GCP_PROJECT` | — | GCP project ID (production) |
| `GCS_BUCKET` | — | Cloud Storage bucket (production) |
| `GOOGLE_APPLICATION_CREDENTIALS` | — | Service account key path |
| `UPLOAD_DIR` | `/tmp/vigour_uploads` | Temp video storage |
| `OUTPUT_DIR` | `data/annotated` | Annotated video output |
| `CONFIGS_DIR` | `configs/test_configs` | Test geometry configs |
| `CACHE_DIR` | `data/cache` | Pipeline cache root |
| `DEFAULT_FPS` | `15` | Default ingestion FPS |
| `DEVICE` | `cuda` | `cuda` or `cpu` |
| `ENABLE_POSE` | `1` | Global pose toggle |
| `ENABLE_OCR` | `1` | Global OCR toggle |
| `PIPELINE_FORCE_RERUN` | `0` | Bypass all caches |

---

## Testing

### Unit Tests

```bash
pytest tests/ -v     # 37 tests, no GPU required
pytest tests/ --cov  # With coverage
```

**Test Modules**:
| Module | Tests | Description |
|--------|-------|-------------|
| `test_cache.py` | ~10 | Atomic cache saves/loads, invalidation |
| `test_visualise.py` | ~10 | OpenCV overlay rendering |
| `test_calibrate.py` | ~5 | Homography + single-axis calibration |
| `test_cone_layout.py` | ~5 | Cone pattern geometry generation |
| `test_ocr.py` | ~4 | Bib extraction and validation |
| `test_models.py` | ~3 | Dataclass serialisation |

All tests run CPU-only with synthetic data — no GPU, no model weights, no video files needed.

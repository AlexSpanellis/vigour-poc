# Vigour POC — CV Fitness Test Pipeline

Computer vision pipeline for automated physical fitness test analysis from school hall footage.  
South African school context: primary Grades 5–7, maroon/navy uniforms, numbered bibs (01–30).

## Tests Supported

| Test | Metric | Target Accuracy |
|------|--------|-----------------|
| Explosiveness (Vertical Jump) | Height (cm) | ±2 cm |
| Sprint (5 m Speed) | Time (s) | ±0.05 s |
| Fitness (Shuttle Run) | Distance (m) | ±0.5 m |
| Agility (T-Drill) | Time (s) | ±0.1 s |
| Balance | Duration (s) | ±0.5 s |

## Pipeline Architecture

```
Video → Ingest → Detect (YOLOv8s) → Track (ByteTrack) → Pose (RTMPose-m)
     → OCR (PaddleOCR) → Calibrate (HSV + Homography) → Extract → Output
```

Each stage caches its output to `data/cache/` so re-runs pick up where they left off.  
OCR and pose estimation can be toggled off via environment variables or per-job API parameters.

---

## Prerequisites

- Python 3.10+
- Docker & Docker Compose (for Redis and PostgreSQL)
- CUDA 11.8+ (optional, but strongly recommended for pose estimation)
- `ffmpeg` on system PATH

---

## Local Development Setup

### 1 — Clone and create virtual environment

```bash
git clone https://github.com/vigourtech/vigour-poc
cd vigour-poc
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
```

### 2 — Install Python dependencies

**mim** needs PyTorch installed first to detect your CUDA version and pick the right mmcv wheel. Install in this order:

```bash
pip install "setuptools==60.2.0"
pip install torch==2.4.0 torchvision==0.19.0 --index-url https://download.pytorch.org/whl/cu121
pip install openmim
mim install mmcv==2.2.0 mmengine
pip install -r requirements.txt
pip install bytetracker --no-deps
```

- `torch` must be installed before `mim install mmcv mmengine` (mim uses it to select the correct pre-built wheel).
- With mmcv/mmengine already present, `pip install -r requirements.txt` will not rebuild mmcv.
- The last line installs ByteTrack without pulling `lap==0.4.0` (which does not build on Python 3.11).

For a specific CUDA version, install PyTorch from [pytorch.org](https://pytorch.org) first, then run the rest.

### 3 — Configure environment variables

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Redis (Celery broker + backend)
REDIS_URL=redis://localhost:6379/0

# PostgreSQL (results storage)
DATABASE_URL=postgresql://vigour:vigour@localhost:5432/vigour

# Storage paths
UPLOAD_DIR=/tmp/vigour_uploads
OUTPUT_DIR=data/annotated
CONFIGS_DIR=configs/test_configs
CACHE_ROOT=data/cache

# Stage toggles (1 = enabled, 0 = disabled)
ENABLE_POSE=1
ENABLE_OCR=1

# Set to 1 to bypass all caches and rerun every stage
PIPELINE_FORCE_RERUN=0

# GCP (production only)
GCP_PROJECT=vigour-poc
GCS_BUCKET=vigour-footage
```

### 4 — Start local services

```bash
docker-compose up -d db redis
```

This starts:
- PostgreSQL 15 on port 5432
- Redis 7 on port 6379

### 5 — Initialise the database

```bash
psql postgresql://vigour:vigour@localhost:5432/vigour -f db/schema.sql
```

### 6 — Start the Celery worker

```bash
celery -A worker.celery_app worker --concurrency=1 --loglevel=info
```

> Use `--concurrency=1` on a single-GPU machine to avoid VRAM conflicts.

### 7 — Start the FastAPI server

```bash
fastapi dev api/main.py
# or for production:
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

API docs available at: http://localhost:8000/docs

---

## Running Tests

```bash
# All unit tests
pytest tests/ -v

# Individual test modules
pytest tests/unit/test_cache.py -v
pytest tests/unit/test_visualise.py -v
pytest tests/unit/test_models.py -v
pytest tests/unit/test_ocr.py -v
pytest tests/unit/test_calibrate.py -v
```

Current coverage: 37 unit tests, all passing (no GPU or video file required).

---

## Using the API

### Upload a clip and start processing

```bash
curl -X POST http://localhost:8000/upload \
  -F "file=@/path/to/clip.mp4" \
  -F "test_type=explosiveness"
# → {"job_id": "abc-123", "status": "queued"}
```

Supported `test_type` values: `explosiveness`, `speed`, `fitness`, `agility`, `balance`.

### Override stage toggles per job

```bash
# Disable pose estimation for this job only (fastest, no GPU needed)
curl -X POST http://localhost:8000/upload \
  -F "file=@clip.mp4" \
  -F "test_type=speed" \
  -F 'config_override={"enable_pose": false, "enable_ocr": false}'
```

### Poll for results

```bash
curl http://localhost:8000/results/abc-123
# → {"job_id": "abc-123", "status": "complete", "results": [...]}
```

Status values: `pending` → `processing` → `complete` | `failed`

### Download annotated video

```bash
curl http://localhost:8000/annotated/abc-123 -o review.mp4
```

### Cache management

```bash
# List all cached jobs
curl http://localhost:8000/cache

# Inspect cache for one job
curl http://localhost:8000/cache/abc-123

# Re-run only metric extraction (keeps detect/track/pose cached)
curl -X DELETE http://localhost:8000/cache/abc-123/results

# Re-run from pose estimation onwards
curl -X DELETE http://localhost:8000/cache/abc-123/pose

# Clear everything and start fresh
curl -X DELETE http://localhost:8000/cache/abc-123
```

Valid stage names: `ingest`, `detect`, `track`, `pose`, `ocr`, `calibrate`, `results`

---

## Stage Toggles (Pose & OCR)

Two pipeline stages can be disabled for speed or when hardware is unavailable:

### Environment variable (affects all jobs)

```bash
ENABLE_POSE=0 celery -A worker.celery_app worker ...   # skip pose globally
ENABLE_OCR=0  celery -A worker.celery_app worker ...   # skip OCR globally
```

### Per-job via API

Pass `enable_pose` and `enable_ocr` as booleans in `config_override`:

```bash
curl -X POST http://localhost:8000/upload \
  -F "file=@clip.mp4" \
  -F "test_type=speed" \
  -F 'config_override={"enable_pose": false}'
```

**Effect of disabling stages:**

| Toggle | Effect |
|--------|--------|
| `ENABLE_POSE=0` | Skips RTMPose-m; skeleton overlays hidden; balance extractor disabled (returns empty) |
| `ENABLE_OCR=0` | Skips PaddleOCR; all bib_numbers stay `null`; track_id used as identity |

---

## Evaluation Notebooks

Place a sample clip at `data/raw_footage/sample_clip.mp4` then run:

```bash
cd notebooks
jupyter lab
```

| Notebook | Purpose |
|----------|---------|
| `01_detection_eval.ipynb` | YOLOv8s detection — frame grid, confidence stats, cache save |
| `02_tracking_eval.ipynb` | ByteTrack — track lifetimes, ID continuity, colour-coded boxes |
| `03_pose_eval.ipynb` | RTMPose-m — skeleton overlay grid, keypoint confidence bar chart |
| `04_ocr_eval.ipynb` | PaddleOCR — bib crops, majority-vote resolution, accuracy check |
| `05_calibration_eval.ipynb` | HSV cone tuning, homography / single-axis calibration, px→cm mapping |
| `06_test_extractors.ipynb` | Per-test metric extraction from cached pipeline outputs |
| **`02_tracking_with_pose.ipynb`** | **Detect + Track + Pose end-to-end with annotated video export and toggles** |
| `poc_validation.ipynb` | Full pipeline vs ground truth — MAE, bar chart, annotated video |

Each notebook saves its outputs to `PipelineCache` under a shared `job_id` so downstream notebooks can load earlier stages without recomputing.

### Quick single-stage run (no Jupyter)

```python
from pipeline.ingest import extract_frames
from pipeline.detect import PersonDetector

frames = [f for _, f, _ in extract_frames("clip.mp4", target_fps=15)]
detector = PersonDetector()
for frame in frames[:5]:
    dets = detector.detect(frame)
    print(dets)
```

### Cone detection POC scripts (SAM vs YOLOX)

Use these scripts to compare cone localization approaches on the same clip:

```bash
# 1) YOLOX ONNX cone detections
python scripts/poc_cones_yolox.py \
  --video data/raw_footage/agility_test.mp4 \
  --model /path/to/yolox_cone.onnx \
  --target-fps 10 \
  --max-frames 300 \
  --save-annotated \
  --output-json data/cache/poc_yolox_cones.json

# 2) SAM2/SAM3 cone proposals (Ultralytics SAM integration)
python scripts/poc_cones_sam.py \
  --video data/raw_footage/agility_test.mp4 \
  --model sam3_b.pt \
  --target-fps 10 \
  --max-frames 300 \
  --save-annotated \
  --output-json data/cache/poc_sam_cones.json

# 3) Compare both outputs
python scripts/compare_cone_poc_results.py \
  --a data/cache/poc_yolox_cones.json \
  --b data/cache/poc_sam_cones.json \
  --dist-threshold-px 25
```

Notes:
- `poc_cones_sam.py` uses mask proposals + cone color/shape filtering (not class detection logits).
- `poc_cones_yolox.py` assumes your YOLOX ONNX output is either decoded `[x1,y1,x2,y2,score,class]`
  or standard `[cx,cy,w,h,obj,cls...]`.
- For production, benchmark by calibration success/reprojection error, not only cone count agreement.

---

## Repository Structure

```
vigour-poc/
├── pipeline/                    # Core CV pipeline modules
│   ├── models.py                # Shared dataclasses (Detection, Track, Pose, …)
│   ├── ingest.py                # Frame extraction (OpenCV stride-based)
│   ├── detect.py                # Person detection (YOLOv8s)
│   ├── track.py                 # Multi-person tracking (ByteTrack)
│   ├── pose.py                  # Pose estimation (RTMPose-m, top-down ONNX)
│   ├── ocr.py                   # Bib OCR (PaddleOCR + CLAHE + majority vote)
│   ├── calibrate.py             # Cone detection (HSV) + homography calibration
│   ├── visualise.py             # Layered OpenCV overlays + VisOptions toggles
│   ├── cache.py                 # Atomic stage caching (JSON + NPZ)
│   ├── output.py                # JSON results + annotated video writer
│   └── tests/                   # Per-test metric extractors
│       ├── base.py              # BaseMetricExtractor ABC + shared helpers
│       ├── explosiveness.py     # Vertical jump height (ankle baseline + apex)
│       ├── sprint.py            # 5 m sprint time (hip crossing start/finish lines)
│       ├── shuttle.py           # Shuttle run distance (world X reversals)
│       ├── agility.py           # T-drill time (start zone departure/return)
│       └── balance.py           # Balance duration (lean angle state machine)
├── api/
│   └── main.py                  # FastAPI: upload, results, annotated video, cache CRUD
├── worker/
│   └── celery_app.py            # Celery task: full 8-stage pipeline + toggles
├── db/
│   └── schema.sql               # PostgreSQL schema (sessions, clips, results)
├── infra/
│   └── main.tf                  # Terraform GCP: L4 GPU VM, Cloud SQL, Redis, GCS
├── notebooks/                   # Jupyter evaluation notebooks (see table above)
├── configs/
│   └── test_configs/            # Geometry configs per test type (JSON)
│       ├── explosiveness.json
│       ├── sprint.json
│       ├── shuttle.json
│       ├── agility.json
│       └── balance.json
├── tests/
│   └── unit/                    # Pytest unit tests (37 tests, no GPU required)
├── data/
│   ├── raw_footage/             # Upload clips here for notebook evaluation
│   ├── ground_truth/            # Ground truth JSON for accuracy validation
│   ├── annotated/               # Annotated output videos
│   └── cache/                   # Stage cache files (auto-created)
├── docker/
│   ├── Dockerfile.api
│   └── Dockerfile.worker
├── docker-compose.yml
├── requirements.txt
└── conftest.py                  # Pytest root — adds project root to sys.path
```

---

## Environment Parameters (March 2026 Footage)

- **Floor:** Light-coloured wooden parquet — good contrast with cones
- **Lighting:** Diffuse indoor fluorescent + side windows; re-tune HSV on first frame
- **Students:** Primary school Grades 5–7, ~130–155 cm, maroon/navy uniforms, bibs 01–30
- **Cone HSV defaults:** Yellow H 18–35, Orange H 5–18, Blue H 100–130, Red H 0–5 or 170–180
- **Capture:** 30 fps source → downsampled to 15 fps by pipeline ingest
- **Currency:** South African Rand (ZAR). All infrastructure costs quoted in ZAR.

---

## GPU Verification

```python
import onnxruntime as ort
print(ort.get_available_providers())   # must include 'CUDAExecutionProvider'

import paddle
print(paddle.device.get_device())      # must show 'gpu:0'
```

If only `CPUExecutionProvider` is visible, install the GPU build:

```bash
pip install onnxruntime-gpu --extra-index-url https://aiinfra.pkgs.visualstudio.com/PublicPackages/_packaging/onnxruntime-cuda-11/pypi/simple/
```

---

## Production Deployment (GCP)

```bash
cd infra
terraform init
terraform plan -var="gcp_project=YOUR_PROJECT_ID"
terraform apply
```

Provisions: `g2-standard-4` VM (1× L4 GPU), Cloud SQL Postgres 15 (`db-f1-micro`), Memorystore Redis 1 GB, GCS bucket with 30-day lifecycle.

---

## Architecture Reference

See [POC Architecture & Implementation Plan](https://www.notion.so/Vigour-Tech-Home-3168e3eb75cf8142a5a0d8d697c4d6c5) in the Vigour Tech Notion workspace.

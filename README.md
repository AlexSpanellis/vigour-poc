# Vigour POC — CV Fitness Test Pipeline

Computer vision pipeline for automated physical fitness test analysis from school hall footage.

## Tests Supported
| Test | Metric | Target Accuracy |
|------|--------|-----------------|
| Explosiveness (Vertical Jump) | Height (cm) | ±2 cm |
| Sprint (5m Speed) | Time (s) | ±0.05 s |
| Fitness (Shuttle Run) | Distance (m) | ±0.5 m |
| Agility (T-Drill) | Time (s) | ±0.1 s |
| Balance | Duration (s) | ±0.5 s |

## Pipeline Stages
```
Video → Ingest → Detect (YOLOv8s) → Track (ByteTrack) → Pose (RTMPose-m)
     → OCR (PaddleOCR) → Calibrate (HSV + Homography) → Extract → Output
```

## Quick Start

```bash
# 1. Clone and set up environment
git clone https://github.com/vigourtech/vigour-poc
cd vigour-poc
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
mim install mmcv mmengine

# 2. Configure environment
cp .env.example .env
# Edit .env with your GCP project, DB and Redis details

# 3. Start local services
docker-compose up db redis

# 4. Start worker and API
celery -A worker.celery_app worker --concurrency=1 --loglevel=info
fastapi dev api/main.py
```

## Repository Structure
```
vigour-poc/
├── pipeline/           # Core CV pipeline modules
│   ├── models.py       # Shared dataclass contracts (Detection, Track, Pose, etc.)
│   ├── ingest.py       # Frame extraction (OpenCV)
│   ├── detect.py       # Person detection (YOLOv8s)
│   ├── track.py        # Multi-person tracking (ByteTrack)
│   ├── pose.py         # Pose estimation (RTMPose-m, top-down)
│   ├── ocr.py          # Bib number OCR (PaddleOCR + majority vote)
│   ├── calibrate.py    # Cone detection + homography calibration
│   ├── output.py       # JSON results + annotated video
│   └── tests/          # Test-specific metric extractors
│       ├── base.py
│       ├── explosiveness.py
│       ├── sprint.py
│       ├── shuttle.py
│       ├── agility.py
│       └── balance.py
├── api/main.py         # FastAPI upload + results endpoints
├── worker/celery_app.py # Celery pipeline orchestrator
├── db/schema.sql       # PostgreSQL schema
├── infra/main.tf       # Terraform GCP (L4 GPU VM, Redis, Cloud SQL, GCS)
├── notebooks/          # Evaluation notebooks per module
├── data/               # raw_footage/, ground_truth/, annotated/
├── configs/test_configs/ # JSON geometry configs per test
├── tests/unit/         # Pytest unit tests
└── docker/             # Dockerfiles for API and worker
```

## Evaluation Notebooks
| Notebook | Purpose |
|----------|---------|
| `01_detection_eval.ipynb` | Benchmark YOLOv8s/m, RT-DETR |
| `02_tracking_eval.ipynb` | Benchmark ByteTrack, OC-SORT |
| `03_pose_eval.ipynb` | Benchmark RTMPose-m/s, ViTPose |
| `04_ocr_eval.ipynb` | Benchmark PaddleOCR, EasyOCR |
| `05_calibration_eval.ipynb` | HSV tuning, homography validation |
| `06_test_extractors.ipynb` | Per-test metric extraction validation |
| `poc_validation.ipynb` | End-to-end accuracy vs ground truth |

## Environment Parameters (March 2026 Footage)
- **Floor:** Light-coloured wooden parquet — good contrast with cones
- **Lighting:** Diffuse indoor fluorescent + side windows. Re-tune HSV on first frame.
- **Students:** Primary school Grades 5–7, ~130–155 cm, maroon/navy uniforms, numbered bibs (01–30)
- **Cone HSV defaults:** Yellow H18–35, Orange H5–18, Blue H100–130, Red H0–5 or H170–180

## GPU Verification
```python
import onnxruntime as ort
print(ort.get_available_providers())  # Should include CUDAExecutionProvider

import paddle
print(paddle.device.get_device())     # Should show: gpu:0
```

## Architecture Reference
See [POC Architecture & Implementation Plan](https://www.notion.so/Vigour-Tech-Home-3168e3eb75cf8142a5a0d8d697c4d6c5) in Notion.

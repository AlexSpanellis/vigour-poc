# File Reference

Complete file listing with descriptions and line counts.

## Root

| File | Lines | Description |
|------|-------|-------------|
| `README.md` | 419 | Full project documentation |
| `requirements.txt` | 57 | Python dependencies |
| `conftest.py` | 6 | Pytest root configuration |
| `docker-compose.yml` | 52 | Local development stack |
| `.env.example` | 23 | Environment variable template |
| `.gitattributes` | 10 | Git LFS tracking rules |
| `.gitignore` | 44 | Git exclusions |
| `yolov8s.pt` | LFS | YOLOv8s person detection model |
| `rtmpose-m.onnx` | LFS | RTMPose-m pose estimation model |
| `sam2_t.pt` | LFS | SAM2 tiny cone detection model |

## `api/`

| File | Lines | Description |
|------|-------|-------------|
| `main.py` | 240 | FastAPI endpoints (upload, results, cache, health) |

## `worker/`

| File | Lines | Description |
|------|-------|-------------|
| `celery_app.py` | 310 | Celery task orchestration, 8-stage pipeline runner |

## `pipeline/`

| File | Lines | Description |
|------|-------|-------------|
| `__init__.py` | 4 | Package marker |
| `models.py` | 73 | Core dataclasses (Detection, Track, Pose, CalibrationResult, TestResult) |
| `ingest.py` | 103 | Frame extraction with stride-based downsampling |
| `detect.py` | 165 | YOLOv8s person detection with GPU fallback |
| `track.py` | 135 | ByteTrack multi-person tracking |
| `pose.py` | 206 | RTMPose-m keypoint estimation (17 COCO points) |
| `ocr.py` | 170 | PaddleOCR bib reading + majority voting |
| `calibrate.py` | 827 | HSV/SAM3 cone detection + homography/single-axis calibration |
| `cone_layout.py` | 184 | Cone pattern geometry (linear, grid, clustered) |
| `cache.py` | 466 | Atomic stage caching with JSON+NPZ serialisation |
| `visualise.py` | 864 | OpenCV annotation layers + H.264 video export |
| `output.py` | 96 | Results JSON serialisation |

## `pipeline/tests/`

| File | Lines | Description |
|------|-------|-------------|
| `__init__.py` | — | Package marker |
| `base.py` | ~80 | BaseMetricExtractor ABC + shared keypoint helpers |
| `explosiveness.py` | ~120 | Vertical jump height extractor |
| `sprint.py` | ~110 | 5m sprint time extractor |
| `shuttle.py` | ~130 | Shuttle run distance extractor |
| `agility.py` | ~120 | T-drill time extractor |
| `balance.py` | ~130 | Balance duration extractor |

## `tests/unit/`

| File | Lines | Description |
|------|-------|-------------|
| `test_cache.py` | 282 | PipelineCache atomic saves/loads, invalidation |
| `test_visualise.py` | 240 | OpenCV overlay rendering correctness |
| `test_calibrate.py` | 83 | Homography + single-axis calibration |
| `test_cone_layout.py` | 81 | Cone pattern geometry generation |
| `test_ocr.py` | 39 | Bib extraction and range validation |
| `test_models.py` | 40 | Dataclass serialisation round-trips |

## `configs/test_configs/`

| File | Description |
|------|-------------|
| `explosiveness.json` | Vertical jump: baseline, threshold, reference height |
| `sprint.json` | 5m sprint: distance, camera angle, 60fps |
| `shuttle.json` | Shuttle run: cone layout (linear), set timing |
| `fitness.json` | Fitness test: 6×7 grid, SAM3, iterative fitting |
| `agility.json` | T-drill: 4 cone positions, start zone |
| `balance.json` | Balance: lean angle, ankle lift threshold |

## `notebooks/`

| File | Description |
|------|-------------|
| `01_detection_eval.ipynb` | YOLOv8s person detection analysis |
| `02_tracking_eval.ipynb` | ByteTrack tracking analysis |
| `02_tracking_with_pose.ipynb` | End-to-end detect + track + pose |
| `03_pose_eval.ipynb` | RTMPose-m skeleton visualisation |
| `04_ocr_eval.ipynb` | PaddleOCR bib number recognition |
| `05_calibration_eval.ipynb` | HSV/SAM3 cone detection + homography |
| `06_test_extractors.ipynb` | Per-test metric extraction verification |
| `poc_validation.ipynb` | Full pipeline vs ground truth validation |

## `scripts/`

| File | Description |
|------|-------------|
| `poc_cones_sam.py` | SAM2/SAM3 cone detection POC |
| `poc_cones_yolox.py` | YOLOX cone detection POC |
| `compare_cone_poc_results.py` | Compare SAM vs YOLOX cone outputs |
| `run_grid_calibration.py` | Calibration hyperparameter grid search |

## `docker/`

| File | Description |
|------|-------------|
| `Dockerfile.api` | FastAPI container (python:3.11-slim) |
| `Dockerfile.worker` | Celery worker container (nvidia/pytorch:24.01) |

## `db/`

| File | Description |
|------|-------------|
| `schema.sql` | PostgreSQL 15 schema (sessions, clips, results tables) |

## `infra/`

| File | Description |
|------|-------------|
| `main.tf` | Terraform GCP provisioning (storage, SQL, Redis, GPU VM) |

## `data/` (runtime, not committed)

| Directory | Description |
|-----------|-------------|
| `raw_footage/` | Input video clips |
| `annotated/` | Output annotated videos + results JSON |
| `cache/` | Per-job stage caches (JSON + NPZ) |
| `ground_truth/` | Validation labels (JSON) |

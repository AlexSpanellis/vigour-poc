# Pipeline Architecture

## Overview

The Vigour pipeline processes video through 8 sequential stages. Each stage produces intermediate outputs that are cached to disk, allowing selective re-runs and iterative tuning without reprocessing the entire pipeline.

```
Video File
    │
    ▼
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ 1.Ingest │───►│ 2.Detect │───►│ 3.Track  │───►│ 4.Pose   │
│          │    │ (YOLOv8s)│    │(ByteTrack│    │(RTMPose) │
│ Frames   │    │ BBoxes   │    │ IDs      │    │ Skeleton │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
                                                      │
    ┌─────────────────────────────────────────────────┘
    ▼
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ 5.OCR    │───►│ 6.Calib  │───►│ 7.Extract│───►│ 8.Output │
│(PaddleOCR│    │(HSV/SAM3)│    │(Metrics) │    │(JSON+Vid)│
│ Bibs     │    │ px→cm    │    │ Results  │    │          │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
```

## Stage Details

### Stage 1: Ingest (`pipeline/ingest.py`, 103 lines)

**Purpose**: Extract frames from video at a target FPS.

**Algorithm**:
- Opens video via OpenCV `VideoCapture`
- Reads original FPS from metadata (defaults to 30 if unavailable)
- Calculates stride: `stride = round(original_fps / target_fps)`
- Yields every Nth frame as BGR numpy array
- Timestamps computed as `frame_idx / original_fps`

**Input**: Video file path (`.mp4`, `.mov`), target FPS (default 15)
**Output**: Generator of `(frame_idx, BGR_frame, timestamp_seconds)`

**Notes**:
- Video stabilisation is stubbed out (placeholder logs warning)
- Sprint tests use 60 fps; all others use 15 fps

---

### Stage 2: Detect (`pipeline/detect.py`, 165 lines)

**Purpose**: Find all people in each frame.

**Class**: `PersonDetector`

**Model**: YOLOv8s (small variant, person class only)

**Algorithm**:
- Lazy-loads YOLOv8s model on first inference
- Runs YOLO `.predict()` on each frame (or batch)
- Filters to class 0 (person) with configurable confidence threshold (default 0.5)
- Applies NMS with threshold 0.4
- CUDA fallback: detects sm_120 GPUs (RTX 5080/5090) and falls back to CPU

**Input**: BGR frame(s)
**Output**: `list[Detection]` per frame — each has `(bbox, confidence, class_id, frame_idx)`

**Performance Target**: Recall ≥95%, Precision ≥90%, ≤6ms/frame on L4 GPU @ 1080p

---

### Stage 3: Track (`pipeline/track.py`, 135 lines)

**Purpose**: Assign persistent IDs to detected people across frames.

**Class**: `PersonTracker` wrapping ByteTrack

**Algorithm**:
- Feeds detections frame-by-frame to ByteTrack
- ByteTrack uses Hungarian assignment + momentum-based prediction
- Returns stable `track_id` per person across frames
- Tracks marked as `confirmed` or `tentative`

**ByteTrack Configuration**:
| Parameter | Default | Meaning |
|-----------|---------|---------|
| `track_thresh` | 0.5 | Confidence to start new track |
| `track_buffer` | 30 | Frames to keep lost track alive (2s @ 15fps) |
| `match_thresh` | 0.8 | IOU threshold for matching |
| `min_box_area` | 10 | Filter tiny false positives |
| `frame_rate` | 15 | Must match ingestion FPS |

**Input**: `list[Detection]` + `frame_idx`
**Output**: `list[Track]` — each has `(track_id, bbox, frame_idx, is_confirmed, bib_number=None)`

**Performance Target**: ID switch rate <5%, track continuity ≥90% per student

---

### Stage 4: Pose (`pipeline/pose.py`, 206 lines) — OPTIONAL

**Purpose**: Estimate body keypoints for each tracked person.

**Class**: `PoseEstimator` using MMPose RTMPose-m

**Algorithm**:
- Top-down approach: crops each person's bounding box (expanded by 25%)
- Runs RTMPose-m inference to produce 17 COCO keypoints
- Each keypoint: `(x, y, confidence)` in pixel coordinates
- CUDA compatibility check with CPU fallback

**COCO 17 Keypoints**:
```
 0: nose           5: left_shoulder    11: left_hip
 1: left_eye       6: right_shoulder   12: right_hip
 2: right_eye      7: left_elbow       13: left_knee
 3: left_ear       8: right_elbow      14: right_knee
 4: right_ear      9: left_wrist       15: left_ankle
                  10: right_wrist      16: right_ankle
```

**Critical Keypoints per Test**:
- **Jump**: Ankles (15, 16) — vertical displacement
- **Sprint/Agility**: Hips (11, 12) — body centroid position
- **Shuttle**: Hips (11, 12) — direction reversal detection
- **Balance**: Ankles (15, 16) + Hips (11, 12) + Nose (0) — lean angle

**Toggle**: `ENABLE_POSE=0` (env) or `enable_pose=False` (per-job)

**Input**: BGR frame + `list[Track]`
**Output**: `list[Pose]` — each has `(track_id, frame_idx, keypoints[17,3], pose_confidence)`

---

### Stage 5: OCR (`pipeline/ocr.py`, 170 lines) — OPTIONAL

**Purpose**: Read bib numbers from student clothing to identify who is who.

**Class**: `BibOCR` using PaddleOCR PP-OCRv4

**Algorithm**:
1. Crop top 40% of each track's bounding box (torso region where bib is)
2. Apply CLAHE contrast enhancement on grayscale crop
3. Run PaddleOCR text detection + recognition
4. Parse result as integer, validate against range [1, 30]
5. Sample every 5th frame (clearer stills vs motion blur)
6. **Majority voting** (`resolve_bibs()`): aggregate per-frame reads across all frames per track

**Input**: BGR frame + `list[Track]`
**Output**: `dict[track_id → (bib_number, confidence)]`

**Toggle**: `ENABLE_OCR=0` (env) or `enable_ocr=False` (per-job)
- When disabled, `bib_number` remains `None` and `track_id` is used as fallback identity

**Performance Target**: Auto-resolve ≥80% of tracks, zero false positives

---

### Stage 6: Calibrate (`pipeline/calibrate.py`, 827 lines)

**Purpose**: Map pixel coordinates to real-world measurements (cm) using training cones as reference points.

**Class**: `Calibrator`

**Two-Phase Process**:

#### Phase 1: Cone Detection
Two backends available:

**A) HSV Segmentation (default)**:
- Convert frame to HSV colour space
- Apply per-colour masks (yellow, orange, blue, red)
- Morphological cleanup (open + dilate)
- Extract contour centroids
- Filter by minimum area (100 px)

**B) SAM3 Text Prompt**:
- Use SAM3 semantic segmentation with text prompt "training cone"
- Better generalisation to varied lighting
- Requires GPU (with sm_120 fallback to CPU)

#### Phase 2: Calibration
Three methods:

**A) Homography** (`calibrate_homography`):
- Requires ≥4 cone pixel↔world coordinate pairs
- Computes 3×3 perspective transform via `cv2.findHomography` (RANSAC)
- Tries normal + reversed cone ordering
- Valid if reprojection error < 3 px

**B) Layout-Based** (`calibrate_from_layout`):
- Generates expected world coordinates from config pattern (linear, grid, clustered)
- Iterative grid fitting: initial H from seed points, then assign/refit until convergence
- Handles partial cone detections (e.g., 39 of 42 detected)

**C) Single-Axis** (`calibrate_single_axis`):
- For vertical measurements only (jump, balance)
- `pixels_per_cm = cone_spread_px / known_height_cm`
- No perspective correction

**Input**: BGR frame (usually first frame) + cone world coordinates or layout config
**Output**: `CalibrationResult` — `(method, homography_matrix, pixels_per_cm, cone_positions, reprojection_error, is_valid)`

---

### Stage 7: Extract (`pipeline/tests/`, 5 extractors)

**Purpose**: Compute test-specific metrics from tracked poses and calibration.

All extractors inherit from `BaseMetricExtractor` (ABC) and implement:
- `extract(tracks, poses, frames) → list[TestResult]`
- `validate_inputs(tracks, poses, frames) → bool`

**Shared helpers**: `hip_midpoint()`, `ankle_positions()`, `build_track_pose_map()`

See [03-test-extractors.md](./03-test-extractors.md) for detailed algorithm descriptions.

**Input**: All tracks, all poses, all frames, calibration result, test config
**Output**: `list[TestResult]` — one per student per attempt

---

### Stage 8: Output (`pipeline/output.py` + `pipeline/visualise.py`)

**Purpose**: Produce final results JSON and annotated video.

**JSON Output** (`output.py`, 96 lines):
- Serialises `list[TestResult]` via `dataclasses.asdict()`
- Writes to `data/annotated/{job_id}/results.json`

**Annotated Video** (`visualise.py`, 864 lines):
- H.264 encoding via ffmpeg subprocess
- Configurable overlay layers via `VisOptions`:
  1. Bounding boxes (green=confirmed, orange=tentative) with track ID + bib label
  2. Pose skeleton (COCO 17-point connections, colour per track)
  3. Calibration grid overlay (world-coordinate lines in cm)
  4. Test-specific annotations (jump apex, sprint lines, motion trails, lean angle)
  5. Flag badges (bib_unresolved, low_pose_confidence, invalid_calibration)
  6. HUD scoreboard (best attempt per bib, top-right)
  7. Frame counter + timestamp
  8. Top-down world-view inset (bird's-eye cone + person positions)

---

## Caching System (`pipeline/cache.py`, 466 lines)

Each stage's output is cached to `data/cache/{job_id}/`:

```
data/cache/{job_id}/
├── manifest.json          # Stage list, timestamps, metadata
├── stage_ingest.json      # Frame indices + timestamps
├── stage_detect.npz       # Per-frame detections (compressed numpy)
├── stage_track.npz        # Per-frame tracks + bibs
├── stage_pose.npz         # Per-frame keypoints
├── stage_ocr.json         # Bib readings + resolved map
├── stage_calibrate.npz    # Calibration matrix + cone data
└── stage_results.json     # Final TestResult list
```

**Key Features**:
- **Atomic writes**: temp file → rename (prevents corruption on crash)
- **Stage invalidation**: Deleting a stage removes all downstream stages too
- **Force rerun**: `PIPELINE_FORCE_RERUN=1` bypasses all caches
- **API management**: REST endpoints for listing, inspecting, and clearing caches

---

## Stage Toggles

| Toggle | Environment Variable | Per-Job Parameter | Effect When Disabled |
|--------|---------------------|-------------------|---------------------|
| **Pose** | `ENABLE_POSE=0` | `enable_pose=False` | All poses empty; balance extractor disabled; skeleton overlays hidden |
| **OCR** | `ENABLE_OCR=0` | `enable_ocr=False` | All bib_numbers remain `None`; track_id used as identity |

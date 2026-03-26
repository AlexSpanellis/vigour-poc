# Evaluation Notebooks

Eight Jupyter notebooks in `notebooks/` provide stage-by-stage and end-to-end validation workflows. They share a common caching layer (`PipelineCache`) so downstream notebooks reuse upstream results without recomputation.

## Notebook Dependency Graph

```
01_detection_eval ─── cache detections
        │
        ▼
02_tracking_eval ──── cache tracks
        │
        ├──► 02_tracking_with_pose (integrated pipeline, optional pose)
        │
        ▼
03_pose_eval ──────── cache poses
        │
        ▼
04_ocr_eval ───────── cache bib resolutions
        │
        ▼
05_calibration_eval ─ cache calibration
        │
        ▼
06_test_extractors ── cache test results
        │
        ▼
poc_validation ────── end-to-end accuracy check
```

---

## 01_detection_eval.ipynb — Person Detection

**Purpose**: Evaluate YOLOv8s person detection quality on sample footage.

**What It Does**:
1. Extracts frames from video at 15 fps
2. Runs `PersonDetector` (YOLOv8s) on all frames
3. Visualises 3×3 grid of sample frames with bounding boxes
4. Charts: detection count over time + confidence distribution histogram
5. Saves detections to cache

**Key Outputs**:
- Per-frame detection counts (typically ~5 persons/frame)
- Confidence score distribution
- Cached detections for downstream notebooks

---

## 02_tracking_eval.ipynb — Multi-Person Tracking

**Purpose**: Evaluate ByteTrack ID assignment stability.

**What It Does**:
1. Loads cached detections (or recomputes)
2. Runs `PersonTracker` (ByteTrack) frame-by-frame
3. Visualises tracks with distinct colours, confirmed vs tentative
4. Track lifetime chart: horizontal lines showing frame span per ID
5. Saves tracks to cache

**Key Outputs**:
- Unique track count and ID switch analysis
- Track continuity per student (% of frames with consistent ID)
- Confirmed vs tentative track ratio

---

## 02_tracking_with_pose.ipynb — Integrated Pipeline

**Purpose**: End-to-end detection + tracking + pose with toggleable stages.

**What It Does**:
1. Runs full detect → track → pose → OCR pipeline
2. Configurable toggles: `ENABLE_POSE`, `ENABLE_OCR`
3. Exports annotated video with `PipelineVisualiser`
4. Configurable `VisOptions` for overlay layers

**Key Outputs**:
- Annotated video with skeleton overlays
- Integration validation (stages work together correctly)

---

## 03_pose_eval.ipynb — Pose Estimation

**Purpose**: Evaluate RTMPose-m keypoint accuracy.

**What It Does**:
1. Loads cached tracks (or computes inline)
2. Runs `PoseEstimator` (RTMPose-m) on each tracked person
3. Visualises COCO-17 skeletons with colour-coded connections
4. Bar chart: mean confidence per keypoint joint
5. Saves poses to cache

**Key Outputs**:
- Skeleton visualisation quality assessment
- Per-joint confidence scores (identifies which keypoints are reliable)
- Cached poses for extractors

---

## 04_ocr_eval.ipynb — Bib OCR

**Purpose**: Evaluate PaddleOCR bib number recognition accuracy.

**What It Does**:
1. Loads cached tracks
2. Runs `BibOCR` on every 5th frame (upper-torso crops)
3. Applies `resolve_bibs()` majority voting
4. Visualises OCR crops with predicted bib numbers
5. Optionally compares against ground truth

**Key Outputs**:
- Per-track bib resolution with confidence
- Crop visualisation (verify OCR is reading correct region)
- Resolution rate (% of tracks with confident bib assignment)

---

## 05_calibration_eval.ipynb — Calibration

**Purpose**: Evaluate cone detection and pixel→world calibration.

**What It Does**:
1. Displays HSV distribution of first frame (for manual range tuning)
2. Runs SAM3 or HSV cone detection
3. Visualises detected cone centroids on frame
4. Computes homography or single-axis calibration
5. Tests pixel→world coordinate mapping
6. Renders top-down world-coordinate view (cm units)

**Key Outputs**:
- Cone detection accuracy (found vs expected)
- Reprojection error (pixels)
- Top-down world view showing cone + person positions
- Calibration result for downstream extractors

**Calibration Methods Tested**:
- Explicit world coords → homography
- Cone layout pattern → iterative grid fitting
- Fallback → single-axis (pixels per cm)

---

## 06_test_extractors.ipynb — Metric Extraction

**Purpose**: Run per-test metric extractors and validate results.

**What It Does**:
1. Loads all cached stages (frames, tracks, poses, calibration)
2. Selects test-specific extractor via `TEST_TYPE` config
3. Runs extraction: `extractor.extract(all_tracks, all_poses, frames)`
4. Bar charts: metric values + confidence scores per student
5. Optionally compares against ground truth (MAE)

**Key Outputs**:
- Per-student metric values with confidence
- Flag analysis (which results have warnings)
- Accuracy vs ground truth (if available)

---

## poc_validation.ipynb — Full Pipeline Validation

**Purpose**: End-to-end accuracy check before field deployment.

**What It Does**:
1. Loads one or more video clips from `data/raw_footage/`
2. Runs complete 8-stage pipeline (ingest → output)
3. Compares predicted metrics against ground truth (from `data/ground_truth/`)
4. Exports annotated video with all overlays + top-down inset

**Ground Truth Format**:
```json
{
    "test_type": "explosiveness",
    "clips": {
        "sample_clip.mp4": {
            "students": [
                {"bib": 7, "metric_value": 34.2, "metric_unit": "cm"},
                {"bib": 14, "metric_value": 28.8, "metric_unit": "cm"}
            ]
        }
    }
}
```

**Key Outputs**:
- Per-bib error: `|predicted - ground_truth|`
- Mean Absolute Error (MAE) across all students
- Predicted vs GT comparison chart
- Full annotated video with skeleton, calibration grid, and top-down view
- Confidence analysis with 0.6 threshold flagging

---

## Shared Patterns

### Cache Usage
All notebooks use `PipelineCache(job_id=...)` to load/save intermediate results:
```python
cache = PipelineCache(job_id="notebook-eval-detection")
if cache.has("detect"):
    all_detections = cache.load_detections()
else:
    # Run detection, then save
    cache.save_detections(all_detections)
```

### Video Path Configuration
All notebooks expect video in `data/raw_footage/`:
```python
VIDEO_PATH = "data/raw_footage/agility_test.mp4"
```

### Visualisation
Common visualisation setup:
```python
vis_options = VisOptions(
    show_boxes=True,
    show_skeleton=ENABLE_POSE,
    show_calibration_grid=calibration.is_valid,
    show_top_down_view=True,
    show_hud=False,
    show_test_overlay=False,
    show_flags=True,
    show_frame_counter=True,
)
```

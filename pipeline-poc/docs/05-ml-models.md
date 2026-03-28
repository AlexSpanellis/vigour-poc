# ML Models & Computer Vision

## Model Inventory

| Model | Framework | File | Stage | Purpose |
|-------|-----------|------|-------|---------|
| **YOLOv8s** | Ultralytics | `yolov8s.pt` | 2. Detect | Person bounding box detection |
| **RTMPose-m** | MMPose | `rtmpose-m.onnx` | 4. Pose | 17-keypoint skeleton estimation |
| **SAM2/SAM3** | Ultralytics | `sam2_t.pt` | 6. Calibrate | Cone detection (semantic segmentation) |
| **PP-OCRv4** | PaddleOCR | (downloaded) | 5. OCR | Bib number text recognition |
| **ByteTrack** | ByteTracker | (algorithmic) | 3. Track | Multi-person tracking (no weights) |

---

## YOLOv8s — Person Detection

**Stage**: 2 (Detect)
**Class**: `PersonDetector` in `pipeline/detect.py`

### How It Works
- YOLO (You Only Look Once) v8 small variant
- Single-shot object detection: processes entire frame in one pass
- Filtered to class 0 (person) only — all other COCO classes discarded
- Non-maximum suppression removes overlapping detections

### Configuration
| Parameter | Default | Description |
|-----------|---------|-------------|
| `conf_threshold` | 0.5 | Min confidence to keep detection |
| `nms_threshold` | 0.4 | IOU threshold for NMS |
| `device` | "cuda" | "cuda" or "cpu" |

### Performance
- Target: Recall ≥95%, Precision ≥90%
- Speed: ≤6ms per frame on L4 GPU @ 1080p
- Handles partial occlusion (students overlapping)
- Alternatives evaluated: YOLOv8m/n, RT-DETR, YOLOv9, Detectron2

### Loading Pattern
```python
# Lazy load — model not in GPU memory until first call
def __init__(self, model_path="yolov8s.pt", device="cuda"):
    self._model = None

def _load_model(self):
    from ultralytics import YOLO
    self._model = YOLO(self.model_path)
```

### GPU Fallback
Detects sm_120 architecture (RTX 5080/5090, unsupported by PyTorch 2.4) and automatically falls back to CPU inference.

---

## RTMPose-m — Pose Estimation

**Stage**: 4 (Pose)
**Class**: `PoseEstimator` in `pipeline/pose.py`

### How It Works
- **Top-down** approach: first detect person bbox, then estimate keypoints within it
- RTMPose-m (Real-Time Multi-person Pose estimation, medium size)
- Produces 17 COCO-format keypoints with per-keypoint confidence
- Bounding box expanded by 25% padding to capture limbs at edges

### Model Details
- Config: `body_2d_keypoint/rtmpose/coco/rtmpose-m_8xb256-420e_aic-coco-256x192.py`
- Checkpoint: Downloaded from OpenMMLab
- Input resolution: 256×192 (cropped person region)
- Output: 17 × (x, y, confidence)

### Critical Keypoints for Vigour

**Ankles (15, 16)** — Used by:
- Jump height: baseline vs apex vertical displacement
- Balance: detect single-leg stance, floor contact

**Hips (11, 12)** — Used by:
- Sprint: crossing start/finish lines (hip midpoint X)
- Shuttle: direction reversal detection (world X)
- Agility: cone proximity and start zone detection

**Nose (0)** — Used by:
- Balance: lean angle calculation (nose-to-hip vertical offset)

---

## SAM2/SAM3 — Cone Detection

**Stage**: 6 (Calibrate)
**Usage**: Alternative cone detection backend in `pipeline/calibrate.py`

### How It Works
- **SAM3 Semantic Mode**: Text-prompted segmentation ("training cone")
- Generates per-mask detections with centroid and HSV colour labelling
- Better generalisation to varied lighting than HSV segmentation
- Falls back to CPU for unsupported GPU architectures

### Comparison with HSV Backend

| Aspect | HSV Segmentation | SAM3 Prompt |
|--------|-----------------|-------------|
| Speed | Fast (pure OpenCV) | Slow (neural inference) |
| Robustness | Sensitive to lighting | More robust |
| Configuration | Requires HSV range tuning | Just text prompt |
| GPU | Not needed | Strongly recommended |
| Accuracy | Good with tuned ranges | Good out-of-box |

### HSV Ranges (Default)
```
Yellow:       H 18-35,  S 80-255,  V 80-255
Orange/Red:   H 5-18,   S 100-255, V 100-255
Blue:         H 100-130, S 80-255,  V 50-255
Red (wrap):   H 0-5 or 170-180, S 100-255, V 100-255
```

---

## PaddleOCR PP-OCRv4 — Bib Reading

**Stage**: 5 (OCR)
**Class**: `BibOCR` in `pipeline/ocr.py`

### How It Works
1. **Crop**: Extract top 40% of person bounding box (torso/bib region)
2. **Enhance**: CLAHE (Contrast Limited Adaptive Histogram Equalization) on grayscale
3. **Detect + Recognise**: PaddleOCR finds text regions and reads characters
4. **Validate**: Parse as integer, check range [1, 30]
5. **Aggregate**: Majority vote across sampled frames per track

### Key Parameters
| Parameter | Value | Description |
|-----------|-------|-------------|
| `TORSO_CROP_FRACTION` | 0.40 | Top 40% of bbox for bib region |
| `min_bib` | 1 | Minimum valid bib number |
| `max_bib` | 30 | Maximum valid bib number |
| `min_confidence` | 0.6 | Majority vote threshold |
| `sample_rate` | every 5th frame | Skip blurry motion frames |

### Majority Voting
```
Frame 10: track_1 → "7"
Frame 15: track_1 → "7"
Frame 20: track_1 → "1"   ← noise
Frame 25: track_1 → "7"
Frame 30: track_1 → "7"

Vote: track_1 → bib 7, confidence 0.80 (4/5 frames agree)
```

---

## ByteTrack — Multi-Person Tracking

**Stage**: 3 (Track)
**Class**: `PersonTracker` in `pipeline/track.py`

### How It Works
- **Not a neural network** — purely algorithmic tracker
- Uses Hungarian algorithm for optimal assignment of detections to tracks
- Momentum-based prediction for occluded persons
- Handles track birth (new person enters), death (person leaves), and recovery (person reappears)

### Key Parameters
| Parameter | Default | Description |
|-----------|---------|-------------|
| `track_thresh` | 0.5 | Confidence to create new track |
| `track_buffer` | 30 | Frames to keep lost track (2s @ 15fps) |
| `match_thresh` | 0.8 | IOU threshold for matching |
| `min_box_area` | 10 | Filter tiny false detections |

---

## GPU Compatibility

### CUDA Fallback Pattern
Both YOLOv8 and RTMPose implement automatic CPU fallback:

```python
try:
    result = model.predict(frame, device="cuda")
except RuntimeError as e:
    if "no kernel image" in str(e) or "not compatible" in str(e).lower():
        logger.warning("GPU unsupported, falling back to CPU")
        result = model.predict(frame, device="cpu")
```

This handles:
- RTX 5080/5090 (sm_120) with PyTorch 2.4 (max sm_90)
- Missing CUDA drivers
- Insufficient GPU memory

### SAM3 Compatibility Check
```python
def _cuda_compatible_for_sam(self) -> bool:
    cap = torch.cuda.get_device_capability()  # (major, minor)
    return cap[0] <= 9  # sm_90 max supported
```

---

## Model File Management

### Git LFS
All model weights are tracked via Git LFS (`.gitattributes`):
```
*.pt *.onnx *.pth *.ckpt *.pkl *.bin *.h5 *.joblib → filter=lfs
```

The files in the repo are 133-134 byte LFS pointers. Actual weights are stored in LFS storage.

### Lazy Loading
All models use deferred loading — not initialised until first inference call. This:
- Saves GPU memory when stages are disabled (e.g., `ENABLE_POSE=0`)
- Allows import without GPU available
- Enables CPU-only testing (37 unit tests, no GPU required)

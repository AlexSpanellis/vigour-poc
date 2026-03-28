# Visualisation System

The visualisation module (`pipeline/visualise.py`, 864 lines) renders annotated video frames with configurable overlay layers. It supports both video export (via ffmpeg H.264) and single-frame annotation (for notebooks).

## VisOptions Configuration

```python
@dataclass
class VisOptions:
    show_boxes: bool = True              # Bounding boxes + track ID labels
    show_skeleton: bool = True           # COCO 17-point skeleton
    show_calibration_grid: bool = True   # World-coordinate grid overlay
    show_top_down_view: bool = True      # Bird's-eye inset
    top_down_view_size: tuple = (280, 280)  # Inset dimensions
    show_hud: bool = False               # Test progress display
    show_test_overlay: bool = False      # Test-specific annotations
    show_flags: bool = True              # Warning badges
    show_frame_counter: bool = True      # Frame number + timestamp
```

## Overlay Layers

### 1. Bounding Boxes

- **Confirmed tracks**: Green border, solid
- **Tentative tracks**: Orange border, thinner
- Label: `Track {id}` or `Bib {number}` (if OCR resolved)
- Track ID colour from 9-colour palette (cycling)

### 2. Pose Skeleton

17 COCO keypoints + 13 connectivity lines per person:

```
Face:  nose↔eyes, eyes↔ears
Torso: shoulders↔shoulders, shoulders↔hips, hips↔hips
Arms:  shoulder→elbow→wrist (both sides)
Legs:  hip→knee→ankle (both sides)
```

- Keypoint circles drawn only if confidence > 0.3
- Colour matched to track ID palette
- Line thickness: 2px

### 3. Calibration Grid

- Detected cones: filled circles at pixel positions
- World-coordinate axis arrows from origin
- Reprojection error badge (top-left)
- Grid lines at regular cm intervals (if homography valid)

### 4. Test-Specific Overlays

| Test | Overlay |
|------|---------|
| **Explosiveness** | Horizontal baseline floor line, apex marker (star), height annotation in cm |
| **Sprint** | Vertical start/finish crossing lines with labels |
| **Shuttle** | Motion trail (hip path trace) with fading tail |
| **Agility** | Path trace + cone proximity circles (radius = touch threshold) |
| **Balance** | Lean angle indicator line from hip to nose, balance duration timer |

### 5. Flag Badges

Warning badges rendered near affected track:
- `bib_unresolved` — red badge
- `low_pose_confidence` — yellow badge
- `invalid_calibration` — red badge (global, not per-track)

### 6. HUD Scoreboard

Top-right display showing best attempt per bib:
```
┌─────────────────┐
│  Bib 7:  34.2 cm│
│  Bib 14: 28.8 cm│
│  Bib 22: 31.5 cm│
└─────────────────┘
```

### 7. Frame Counter

Bottom-left timestamp display:
```
Frame: 42/300  |  t=2.80s
```

### 8. Top-Down World View (Inset)

Small bird's-eye view in bottom-right corner showing:
- Cone positions: filled circles (detected) + open circles (expected grid)
- Person positions: coloured circles with track ID labels
- World-coordinate grid lines
- Axis labels (X cm, Y cm)
- Auto-scaled with 15% padding

## Colour Palette

9-colour cycling palette for track identification:

| Index | Colour | RGB |
|-------|--------|-----|
| 0 | Red | (255, 80, 80) |
| 1 | Green | (80, 255, 80) |
| 2 | Blue | (80, 80, 255) |
| 3 | Yellow | (255, 255, 80) |
| 4 | Magenta | (255, 80, 255) |
| 5 | Cyan | (80, 255, 255) |
| 6 | Orange | (255, 160, 80) |
| 7 | Purple | (160, 80, 255) |
| 8 | Light Blue | (80, 160, 255) |

## Video Export

### Encoding
- Codec: H.264 (Baseline profile, yuv420p)
- Method: ffmpeg subprocess pipe (streaming write)
- Output format: MP4
- Handles arbitrary frame sizes

### Per-Track State
The visualiser maintains state across frames for certain overlays:
- `_path_history`: Hip position trajectory (last N frames) for motion trails
- `_ankle_baselines`: Median ankle Y for standing detection
- `_balance_start`, `_balance_elapsed`: Balance timer state

### API

```python
# For video export
visualiser = PipelineVisualiser(output_path, fps, vis_options)
visualiser.open()
for frame, tracks, poses, calibration, results, timestamp in data:
    annotated = visualiser.write_frame(frame, tracks, poses, calibration, results, timestamp)
visualiser.close()

# For notebook single-frame use (static method)
annotated = PipelineVisualiser.annotate_frame(
    frame, tracks, poses, calibration, results, timestamp, vis_options
)
```

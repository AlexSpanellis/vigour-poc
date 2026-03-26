# Test-Specific Metric Extractors

All extractors live in `pipeline/tests/` and inherit from `BaseMetricExtractor` (ABC) defined in `pipeline/tests/base.py`.

## Base Class

```python
class BaseMetricExtractor(ABC):
    def __init__(self, config: dict, calibration: CalibrationResult): ...

    @abstractmethod
    def extract(self, tracks, poses, frames) -> list[TestResult]: ...

    @abstractmethod
    def validate_inputs(self, tracks, poses, frames) -> bool: ...

    # Shared helpers:
    def hip_midpoint(self, pose: Pose) -> tuple[float, float] | None
    def ankle_positions(self, pose: Pose) -> tuple[tuple, tuple] | None
    def build_track_pose_map(self, frame_tracks, frame_poses) -> dict[int, Pose]
```

---

## 1. Explosiveness (Vertical Jump)

**File**: `pipeline/tests/explosiveness.py`
**Test Type**: `"explosiveness"`
**Metric**: Jump height in centimetres

### Algorithm

```
Phase 1: Establish Baseline
  - For each student (track_id), collect ankle Y positions across first 30 frames
  - Compute median ankle Y = standing floor position
  - Both ankles used; take average of left (15) and right (16) ankle Y

Phase 2: Jump Detection (State Machine)
  State: NOT_JUMPING
    → If ankle Y drops below (baseline_y - jump_threshold_px): transition to JUMPING
  State: JUMPING
    → Track minimum ankle Y (highest physical point = lowest pixel Y)
    → If ankle Y returns to baseline ±5 px: transition to NOT_JUMPING, record jump

Phase 3: Height Calculation
  - jump_height_px = baseline_y - apex_y
  - jump_height_cm = jump_height_px / pixels_per_cm  (from single-axis calibration)
  - Filter: discard jumps below jump_min_height_cm (5 cm default)

Phase 4: Result Selection
  - Return best N attempts (default 3) per student
```

### Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `jump_threshold_px` | 15 | Min pixel drop to detect jump start |
| `baseline_frames` | 30 | Frames for standing baseline |
| `jump_min_height_cm` | 5.0 | Filter micro-jumps |
| `num_attempts` | 3 | Report best N |
| `reference_height_cm` | 23.0 | Calibration reference (cone height) |

### Calibration Method Used
**Single-axis** — only vertical measurement matters.

---

## 2. Sprint (5m Speed)

**File**: `pipeline/tests/sprint.py`
**Test Type**: `"speed"`
**Metric**: Time in seconds

### Algorithm

```
Phase 1: Define Crossing Lines
  - start_line_x_px = 400 (or from calibration cone positions)
  - finish_line_x_px = 1500 (or from calibration)

Phase 2: Per-Student Tracking
  For each frame:
    - Compute hip midpoint X position (average of left hip [11] and right hip [12])
    - If hip_x crosses start_line_x_px: record start_frame
    - If hip_x crosses finish_line_x_px (after start): record finish_frame

Phase 3: Sub-Frame Interpolation
  - Between frame N (before line) and frame N+1 (after line):
    fraction = (line_x - position_N) / (position_N+1 - position_N)
    precise_time = (frame_N + fraction) / fps

Phase 4: Sprint Time
  - sprint_time_s = finish_time - start_time
  - If student returns before finish: reset (false start handling)
  - Multiple attempts recorded and reported
```

### Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `sprint_distance_m` | 5.0 | Physical distance |
| `start_line_x_px` | 400 | Pixel X for start |
| `finish_line_x_px` | 1500 | Pixel X for finish |
| `camera_angle_deg` | 45 | Camera angle |
| `capture_fps` | 60 | Higher FPS for precision |
| `num_attempts` | 3 | Attempts per student |

### Calibration Method Used
**Homography** — maps start/finish cone pixel positions to 5m world distance.

---

## 3. Shuttle Run (Fitness)

**File**: `pipeline/tests/shuttle.py`
**Test Type**: `"fitness"`
**Metric**: Total distance in metres

### Algorithm

```
Phase 1: World-Space Tracking
  - For each frame, transform hip midpoint from pixels to world X (cm) via homography
  - Build per-student time series of world X positions

Phase 2: Direction Reversal Detection
  Standard shuttle layout: cones at X = 0, 200, 400, 600, 800, 1000 cm
  For each frame:
    - Check if student is near a cone (within reversal_proximity_cm = 30 cm)
    - Check if velocity sign changed (moving left↔right)
    - If both: count as reversal

Phase 3: Distance Calculation
  - Per 15-second set: sum of |ΔX| across all frames
  - Total distance = sum of 3 sets
  - Convert cm → metres for output

Phase 4: Set Timing
  - 3 sets × 15 seconds each
  - 30 seconds rest between sets
  - Detect set boundaries from activity patterns
```

### Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `set_duration_s` | 15 | Duration of each set |
| `num_sets` | 3 | Number of sets |
| `rest_between_sets_s` | 30 | Rest period |
| `reversal_proximity_cm` | 30 | Closeness to cone for reversal |
| `cone_count` | 6 | Number of cones in line |
| `cone_spacing_m` | 4.0 | Distance between cones |

### Calibration Method Used
**Homography** — full perspective transform for world X tracking.

---

## 4. Agility (T-Drill)

**File**: `pipeline/tests/agility.py`
**Test Type**: `"agility"`
**Metric**: Time in seconds

### Algorithm

```
Phase 1: Cone Mapping
  - T-drill cone positions in world space:
    Start: (0, 0)
    Centre: (5m, 0)
    Left:   (5m, -3m)
    Right:  (5m, +3m)
  - Transform to pixel space via homography inverse

Phase 2: State Machine
  State: WAITING
    - Student hip within start_zone_cm (50 cm) of start cone
    → If hip distance > start_zone_cm: transition to DRILLING, start timer

  State: DRILLING
    - Student running T-drill pattern
    - Optionally validate cone proximity (within cone_touch_threshold_cm = 80 cm)
    → If hip distance < start_zone_cm: transition to WAITING, stop timer
    - Filter: discard drills < 1 second (spurious events)

Phase 3: Time Calculation
  - agility_time_s = (end_frame - start_frame) / fps
  - Multiple attempts tracked and reported
```

### T-Drill Pattern

```
            Left (-3m)
              │
              │
Start ────── Centre ────── Right (+3m)
(0,0)        (5m,0)
```

Standard pattern: Start → Centre → Left → Centre → Right → Centre → Start

### Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `drill_pattern` | "t_drill" | Drill type |
| `cone_positions_m` | [[0,0],[5,0],[5,-3],[5,3]] | Cone layout |
| `start_zone_cm` | 50 | Radius around start cone |
| `cone_touch_threshold_cm` | 80 | Max distance for valid cone touch |
| `num_attempts` | 3 | Attempts per student |

### Calibration Method Used
**Homography** — for world-space distance calculations.

---

## 5. Balance

**File**: `pipeline/tests/balance.py`
**Test Type**: `"balance"`
**Metric**: Duration in seconds

### Algorithm

```
Phase 1: Establish Baseline
  - Median ankle Y across first 30 frames = standing position
  - Both ankles at floor level

Phase 2: State Machine
  State: BILATERAL (both feet on floor)
    → If one ankle Y < (baseline_y - ankle_lift_threshold_px):
      transition to BALANCING, start timer

  State: BALANCING
    - Monitor lean angle: atan2(|nose_x - hip_x|, hip_y - nose_y) in degrees
    → If lean_angle > lean_threshold_deg (15°): transition to FAILED
    → If both ankles return to floor: transition to FAILED

  State: FAILED
    - Record balance duration
    → Reset to BILATERAL

Phase 3: Result
  - Return longest balance duration per student
```

### Lean Angle Calculation

```
        nose (0)
         │
         │ ← lean angle measured from vertical
         │
    hip midpoint (avg of 11, 12)
```

`angle = atan2(|nose_x - hip_x|, hip_y - nose_y)` — 0° = perfectly upright

### Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `lean_threshold_deg` | 15 | Max lean angle before fail |
| `ankle_lift_threshold_px` | 20 | Min pixel movement to detect lift |
| `baseline_frames` | 30 | Frames for baseline |
| `max_duration_s` | 60 | Max test time |

### Calibration Method Used
**Single-axis** — only vertical measurement needed.

---

## Extractor Selection

The worker selects the appropriate extractor based on `test_type`:

```python
EXTRACTORS = {
    "explosiveness": ExplosivenessExtractor,
    "speed": SprintExtractor,
    "fitness": ShuttleExtractor,
    "agility": AgilityExtractor,
    "balance": BalanceExtractor,
}
```

Each extractor receives the full config dict (from `configs/test_configs/{test_type}.json`) and the `CalibrationResult` from Stage 6.

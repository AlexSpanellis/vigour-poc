# Data Models

All core data structures are defined in `pipeline/models.py` as Python dataclasses. These form the contract between pipeline stages.

## Detection

Output of Stage 2 (Person Detection).

```python
@dataclass
class Detection:
    bbox: tuple[float, float, float, float]  # (x1, y1, x2, y2) pixel coordinates
    confidence: float                         # 0.0–1.0 detection score
    class_id: int                             # Always 0 (person)
    frame_idx: int                            # Frame number in video
```

**Notes**:
- Bounding box is in pixel coordinates, top-left origin
- `class_id` is always 0 because YOLOv8s is filtered to person class only
- Typical confidence range for valid detections: 0.5–0.95

---

## Track

Output of Stage 3 (Multi-Person Tracking). Extends Detection with identity.

```python
@dataclass
class Track:
    track_id: int            # Unique person identifier across frames
    bbox: tuple[float, float, float, float]  # (x1, y1, x2, y2) pixels
    frame_idx: int           # Current frame
    is_confirmed: bool       # True = stable track, False = tentative
    bib_number: int | None   # Student bib (resolved by OCR stage), initially None
    bib_confidence: float    # OCR confidence, 0.0 if unresolved
```

**Notes**:
- `track_id` is assigned by ByteTrack and persists across frames for the same person
- `bib_number` starts as `None` and is populated after Stage 5 (OCR)
- `is_confirmed` indicates ByteTrack's confidence in the track's stability

---

## Pose

Output of Stage 4 (Pose Estimation).

```python
@dataclass
class Pose:
    track_id: int            # Links back to Track
    frame_idx: int           # Current frame
    keypoints: np.ndarray    # Shape (17, 3) — [x, y, confidence] per keypoint
    pose_confidence: float   # Mean of all 17 keypoint confidences
```

**COCO 17-Point Skeleton Index**:

```
Index  Keypoint         Used By
─────  ────────         ───────
  0    nose             balance (lean angle)
  1    left_eye         —
  2    right_eye        —
  3    left_ear         —
  4    right_ear        —
  5    left_shoulder    —
  6    right_shoulder   —
  7    left_elbow       —
  8    right_elbow      —
  9    left_wrist       —
 10    right_wrist      —
 11    left_hip         sprint, shuttle, agility, balance
 12    right_hip        sprint, shuttle, agility, balance
 13    left_knee        —
 14    right_knee       —
 15    left_ankle       jump, balance
 16    right_ankle      jump, balance
```

**Skeleton Connections** (for visualisation):
```
Face:  (0,1) (0,2) (1,3) (2,4)
Torso: (5,6) (5,11) (6,12) (11,12)
Arms:  (5,7) (7,9) (6,8) (8,10)
Legs:  (11,13) (13,15) (12,14) (14,16)
```

---

## CalibrationResult

Output of Stage 6 (Cone Detection + Calibration).

```python
@dataclass
class CalibrationResult:
    method: str                    # "homography" or "single_axis"
    homography_matrix: np.ndarray | None  # 3×3 perspective transform (or None)
    pixels_per_cm: float | None    # Linear scale factor (or None)
    cone_positions_px: list[tuple] # Detected cone pixel centres
    cone_positions_world: list[tuple]  # Corresponding world coordinates (cm)
    reprojection_error_px: float   # Calibration quality metric
    is_valid: bool                 # Quality gate
```

**Validity Criteria**:
- Homography: `reprojection_error_px < 3.0`
- Single-axis: `pixels_per_cm > 0`

**Coordinate Systems**:
- **Pixel**: (0,0) at top-left of frame, x→right, y→down
- **World**: (0,0) at first cone, x→right, y→forward, units in centimetres

---

## TestResult

Final output of Stage 7 (Metric Extraction).

```python
@dataclass
class TestResult:
    student_bib: int         # OCR-resolved bib number (-1 if unresolved)
    track_id: int            # Raw tracking ID (fallback identity)
    test_type: str           # "explosiveness", "speed", "fitness", "agility", "balance"
    metric_value: float      # The measurement (e.g., 34.2)
    metric_unit: str         # Unit: "cm", "s", "m"
    attempt_number: int      # Which attempt (1–3 for multi-attempt tests)
    confidence_score: float  # Pipeline confidence: 0.0–1.0
    flags: list[str]         # Warning flags
    raw_data: dict           # Test-specific intermediate values for debugging
```

**Confidence Score Calculation**:
- Base: 0.8 if bib resolved, 0.4 if unresolved
- Multiplied by test-specific quality factors (e.g., calibration accuracy)

**Common Flags**:
- `"bib_unresolved"` — OCR could not confidently identify the student
- `"low_pose_confidence"` — Keypoint detection below 0.3 threshold
- `"invalid_calibration"` — Calibration failed quality gate

**Raw Data Examples by Test**:
- Explosiveness: `{apex_frame, baseline_y, jump_height_px, pixels_per_cm}`
- Sprint: `{start_frame, finish_frame, interpolated_start, interpolated_finish}`
- Agility: `{start_frame, end_frame, cone_touches: [...]}`

---

## Database Schema

PostgreSQL 15 schema (`db/schema.sql`):

```sql
-- Test sessions (one per school visit)
CREATE TABLE sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    school_name TEXT NOT NULL,
    session_date DATE NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Video clips submitted for processing
CREATE TABLE clips (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id   UUID REFERENCES sessions(id),
    job_id       TEXT UNIQUE,          -- Celery task ID
    test_type    TEXT NOT NULL,         -- "explosiveness", "speed", etc.
    video_path   TEXT NOT NULL,
    status       TEXT DEFAULT 'pending', -- pending → processing → complete | failed
    created_at   TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ
);

-- Individual test results per student
CREATE TABLE results (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clip_id          UUID REFERENCES clips(id),
    student_bib      INT NOT NULL,
    track_id         INT NOT NULL,
    test_type        TEXT NOT NULL,
    metric_value     FLOAT NOT NULL,
    metric_unit      TEXT NOT NULL,
    attempt_number   INT DEFAULT 1,
    confidence_score FLOAT,
    flags            TEXT[],           -- Array of warning strings
    raw_data         JSONB             -- Test-specific debug info
);

-- Indices for common queries
CREATE INDEX idx_results_bib ON results(student_bib);
CREATE INDEX idx_results_type ON results(test_type);
CREATE INDEX idx_clips_job ON clips(job_id);
```

---

## Data Flow Between Stages

```
Stage 1 (Ingest)
  → frame_indices: list[int]
  → timestamps: list[float]
  → raw frames: list[np.ndarray]  (BGR, not cached — re-extracted on replay)

Stage 2 (Detect)
  → all_detections: list[list[Detection]]  (per-frame list of detections)

Stage 3 (Track)
  → all_tracks: list[list[Track]]  (per-frame list of tracks)

Stage 4 (Pose)
  → all_poses: list[list[Pose]]  (per-frame list of poses)

Stage 5 (OCR)
  → frame_readings: list[dict[int, int|None]]  (per-frame: track_id → bib)
  → resolved_bibs: dict[int, tuple[int, float]]  (track_id → (bib, confidence))
  → Bibs attached to Track objects: track.bib_number, track.bib_confidence

Stage 6 (Calibrate)
  → calibration: CalibrationResult

Stage 7 (Extract)
  → results: list[TestResult]

Stage 8 (Output)
  → results.json file
  → annotated.mp4 video
```

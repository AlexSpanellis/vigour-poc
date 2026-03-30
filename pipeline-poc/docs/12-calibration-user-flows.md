# Calibration User Flows — Per Test Type

**Purpose**: Define the teacher-facing calibration workflow for each of the 7 Vigour tests. Each flow must be completable by a non-technical PE teacher in under 2 minutes, with on-screen guidance and real-time feedback.

**Key constraint from functional requirements**: "A teacher with no prior training must be able to set up and run their first test within 10 minutes." Calibration is one step within setup — it must feel invisible, not like a separate technical task.

---

## Design Decision: Three Calibration Tiers

After analysing the 7 tests against camera geometry, measurement requirements, and teacher effort, three distinct calibration approaches emerge. **Not every test needs cones.**

| Tier | Approach | Tests | Teacher effort |
|------|----------|-------|---------------|
| **Tier 0** | No calibration | Balance | Zero — just point camera |
| **Tier 1** | Reference-object calibration | Explosiveness, Mobility | Minimal — hold a known object in frame once |
| **Tier 2** | Two-point bounding box + cone layout | Sprint, Fitness, Agility, Coordination | Place 2 reference cones → FOV check → place test cones |

---

## Tier 0: No Calibration

### Test 5 — Balance (Single-Leg, Eyes Closed)

**Why no calibration**: Balance is purely temporal — how many seconds can they hold the pose? The pipeline detects ankle lift via pose keypoints relative to a baseline, with no spatial measurement needed.

**Camera**: Front-facing, body height.

**User flow**:
```
1. Teacher selects "Balance" test type
2. App shows camera guide overlay:
   "Point camera at students from the front, at waist height"
   [diagram showing camera position]
3. App performs live detection check:
   ✅ "1 person detected" — ready to record
   ⚠️ "No person detected — move closer or adjust angle"
4. Teacher taps Record
```

**Calibration pipeline**: None. `requires_valid_calibration = False`. Extractor uses pixel-space ankle Y only.

**Assessment**: This is the simplest flow. No changes needed from current implementation. Works today.

---

## Tier 1: Reference-Object Calibration

### Test 1 — Explosiveness (Vertical Jump)

**What we need to measure**: Height of feet off floor in centimetres. This is a single-axis (vertical) measurement.

**Current approach**: `calibrate_single_axis()` — computes `pixels_per_cm` from a reference object of known height (default: 23cm cone).

**Proposed user flow**:
```
1. Teacher selects "Explosiveness" test type
2. App shows setup guide:
   "Place students in a row. Camera faces them from the front."
   [diagram]
3. App shows calibration step:
   "Hold a cone upright at the students' feet position for 2 seconds"
   [live camera feed with target zone overlay]
4. App auto-detects the cone and calculates px/cm scale
   ✅ "Calibrated — 1cm = 4.2 pixels" (shown as simple green checkmark)
   ⚠️ "Can't see the cone — try again"
5. Teacher removes cone, students step into position
6. Teacher taps Record
```

**Alternative considered**: Skip calibration entirely and use the students' known standing height from their profile as the reference. This would eliminate the calibration step but requires accurate height data in the system.

**Assessment**: Current `calibrate_single_axis()` works. The UX just needs the on-screen guide. The cone-holding step adds ~10 seconds. **Recommend keeping it** — it's robust and doesn't depend on student profile data being accurate.

**Edge case**: Multiple students jumping simultaneously. The vertical scale is consistent across the row if the camera is square-on and far enough back. A single calibration suffices — no per-student calibration needed.

---

### Test 6 — Mobility (Standing Toe-Touch)

**What we need to measure**: Trunk flexion angle (degrees) AND fingertip-to-floor distance (cm, can be negative). Two measurements — angle is pose-only, distance needs spatial calibration.

**Camera**: Side-on, body height, perpendicular to student.

**Proposed approach**: **Tier 1 — single-axis calibration** (same as Explosiveness but horizontal/vertical).

**Why not Tier 2**: The camera is perpendicular and at body height. There is minimal perspective distortion. A single-axis scale factor is sufficient for the fingertip-to-floor measurement. The angle is computed purely from pose keypoints (shoulder→hip→vertical) with no spatial calibration needed.

**Proposed user flow**:
```
1. Teacher selects "Mobility" test type
2. App shows setup guide:
   "Position camera side-on, at waist height, 2-3m away"
   "Students stand perpendicular to camera"
   [diagram showing camera and student positions]
3. Calibration step:
   "Place a cone on the floor at the student's standing position"
   [live camera with target zone overlay]
4. App detects cone and computes vertical px/cm scale
   ✅ "Scale calibrated"
5. Student stands at the mark
6. Teacher taps Record → student performs 3 toe-touch attempts
```

**Key insight**: For fingertip-to-floor distance, we only need vertical scale at the plane of the student. Since the camera is perpendicular and at the same distance as the student, a single-axis calibration is geometrically sufficient.

**Angle measurement**: Computed from pose keypoints — no calibration dependency:
- Trunk flexion angle = angle between (shoulder→hip vector) and vertical
- This is pure image-space geometry, invariant to scale

**Assessment**: Single-axis works. This test type doesn't exist in the current POC code yet — needs a new `MobilityExtractor`. The calibration code (`calibrate_single_axis`) already supports this.

---

## Tier 2: Cone-Layout Calibration (Bounding-Box Approach)

These tests require mapping pixel coordinates to real-world positions because the pipeline must track movement across known distances (sprint gates, shuttle cones, agility waypoints, coordination taps).

### The Shared Workflow: Bottom-Left / Top-Right Bounding-Box Check

All Tier 2 tests share a common first phase before diverging into test-specific cone placement.

```
PHASE 1 — FOV VALIDATION (shared across all Tier 2 tests)
═══════════════════════════════════════════════════════════

Step 1: Teacher places TWO reference cones
  - Bottom-left corner of test area (nearest to camera, left side)
  - Top-right corner of test area (farthest from camera, right side)

  These define the bounding box of the entire test zone.

  The app shows: "Place a cone at the near-left corner and
  another at the far-right corner of your test area"
  [diagram specific to each test showing where BL and TR go]

Step 2: Camera FOV check
  The app detects both cones and validates:
  a) Both cones are visible in the frame
  b) Both cones are >5% inset from frame edges (not clipped)
  c) The bounding box covers enough of the frame (>40% of frame area)
  d) The aspect ratio of the bounding box is reasonable for this test layout

  Feedback:
  ✅ "Test area is fully visible" → proceed
  ⚠️ "Left cone too close to edge — move camera back or left"
  ⚠️ "Right cone not visible — widen camera angle"
  ❌ "Test area too small in frame — move camera closer"

Step 3: World-coordinate anchor
  The BL and TR cones are assigned known world coordinates:
  - BL = (0, 0) cm — origin
  - TR = (test_width_cm, test_depth_cm) — from test config

  This gives us 2 known pixel↔world pairs immediately.
```

**Why this works**: Two diagonal corners give the maximum information about the spatial extent of the test area. They span both axes. Combined with the test-specific cone layout (which provides additional points), they anchor the homography robustly.

**Why BL/TR specifically**: The bottom-left is closest to the camera (largest in frame, easiest to detect). The top-right is farthest (tests depth detection). Together they stress-test the full range of the camera's perspective distortion.

---

### Regular Y-Pattern Calibration Grid

For tests where the teacher has flexibility in cone placement (fitness, coordination), we use a **regular Y-axis pattern** — cones placed at known intervals along the depth axis (Y in world coordinates, which maps to the camera's depth).

**Why Y-axis regularity matters**:
- Perspective distortion is greatest along depth (Y). Objects far from camera appear much smaller than near objects.
- A regular Y-spacing pattern (e.g., every 200cm) provides strong geometric conditioning for the homography precisely where distortion is worst.
- X-axis spacing is less critical because lateral distortion is lower at typical camera positions.

**Implementation**: The cone layout configs already encode this as `spacing_cm_y` for grids and `direction: "y"` for linear patterns.

---

### Test 2 — Speed (5m Sprint)

**What we need to measure**: Time in seconds from start cone to finish cone.

**Camera**: 45-degree angle to capture the full 5m run.

**Cone layout**: 2 cones — start and finish, 5m (500cm) apart.

**Proposed user flow**:
```
PHASE 1 — FOV Validation
  BL cone = start cone (near camera)
  TR cone = finish cone (far from camera)
  World coords: BL = (0, 0), TR = (0, 500)
  → These ARE the test cones — no separate reference cones needed

PHASE 2 — Calibration (automatic)
  With only 2 points, we cannot compute a full homography.

  Options:
  A) Linear interpolation along the run axis (sufficient for timing)
  B) Add 1 more point (midpoint cone at 250cm) → 3 points → homography

  RECOMMENDED: Option A — linear interpolation

  Rationale: Sprint timing only needs to detect when the student
  crosses the start line and finish line. We don't need arbitrary
  pixel→world mapping. The two cones define two gates. Movement
  between gates is projected onto the line between them.

  The app shows:
  ✅ "Start and finish cones detected — ready to record"

PHASE 3 — Record
  Students run one at a time. Camera stays fixed.
```

**Assessment**: Sprint is the simplest Tier 2 test. Two cones double as both FOV validation AND spatial reference. A full homography is overkill — projecting the hip centroid onto the start→finish line gives sub-frame timing accuracy. **This matches the current implementation** where sprint already calibrates successfully.

**Why not 3+ cones**: Adding a midpoint cone forces the teacher to measure 2.5m precisely — more work for negligible accuracy gain on a timing-only measurement. Two cones = two gates = time between gates.

---

### Test 3 — Fitness (Repeated Shuttle Sprints)

**What we need to measure**: Distance travelled in each 15-second set. 6 cones, 2m apart in a line.

**Camera**: Elevated and angled to see all 6 cones.

**Cone layout**: 6 cones linear, 200cm spacing → total 1000cm span.

**Proposed user flow**:
```
PHASE 1 — FOV Validation
  BL cone = cone 1 (near-left, 0cm)
  TR cone = cone 6 (far-right, 1000cm)

  App shows: "Place your first cone (near corner) and last cone
  (far corner). Leave 6 cones in total in a line, 2 metres apart."
  [diagram showing the linear layout from camera's perspective]

  ✅ "Both end cones visible"

PHASE 2 — Full Cone Placement
  Teacher places remaining 4 cones between endpoints at 200cm intervals.

  App detects all 6 cones and validates:
  a) 6 cones detected (within tolerance: 5-8 accepted, best 6 selected)
  b) Cones are approximately collinear
  c) Spacing is approximately regular (within ±30% of 200cm)

  Feedback:
  ✅ "6 cones detected in a line — calibration valid"
  ⚠️ "Only 4 cones detected — check middle cones are visible"
  ⚠️ "Cones not in a straight line — cone 3 is offset"

PHASE 3 — Calibration (automatic)
  Correspondence: linear layout → 2 candidates (forward/reversed)
  World coords: [(0,0), (200,0), (400,0), (600,0), (800,0), (1000,0)]
  Solve via solve_correspondence() → homography

  Reprojection error check: threshold 5cm
  ✅ Valid → proceed to recording
  ❌ Invalid → "Calibration failed — please reposition cones and try again"

PHASE 4 — Record
  Students sprint up and down. Camera stays fixed.
```

**Assessment**: The current pipeline supports this via `calibrate_from_layout()` with `pattern: "linear"`. The main challenge is **over-detection** (40 cones detected vs 6 expected) when other test setups share the gym. The spatial ROI filter partially addresses this but needs the BL/TR bounding box to define the ROI precisely.

**Key improvement**: The BL/TR Phase 1 defines the spatial ROI for cone detection in Phase 2. Instead of trying to filter post-hoc (current approach), we know *a priori* where to look. This is a significant accuracy improvement.

---

### Test 4 — Agility (Cone Drill)

**What we need to measure**: Completion time through a cone pattern. Need to detect when the student is near each waypoint cone.

**Camera**: Above and behind, capturing full drill area.

**Cone layout**: 4+ cones in a test-specific pattern (e.g., T-drill, L-drill). Colour-coded: start, turns, finish.

**Proposed user flow**:
```
PHASE 1 — FOV Validation
  The agility drill has a specific geometric pattern.

  App shows the drill diagram and instructs:
  "Place a cone at the near-left corner of your drill area
  and another at the far-right corner"
  [overlay shows the drill pattern with BL/TR positions marked]

  BL = (0, 0), TR = (width, depth) of the drill bounding box

  ✅ "Drill area fully visible"

PHASE 2 — Pattern Cone Placement
  Teacher places the test cones in the prescribed pattern.

  App shows: "Place your 4 drill cones as shown in the diagram"
  [interactive overlay with numbered cone positions]

  Detection: colour-coded cones help distinguish roles:
  - Yellow = turn points
  - Red = start
  - Blue = finish (or similar)

  Validation:
  a) Expected number of cones detected within the BL/TR bounding box
  b) Pattern roughly matches expected layout (distances within tolerance)

  ✅ "4 cones detected — pattern matches T-drill"
  ⚠️ "3 cones detected — check cone 2 is visible"

PHASE 3 — Calibration
  World coords come from the test config (cone_positions_m).
  Correspondence: irregular layout → permutation search (N=4 → 24 candidates)

  Additional constraint: the BL/TR reference cones from Phase 1 can
  optionally be left in place as extra calibration points. This gives
  6 points instead of 4, dramatically improving the homography.

  RECOMMENDATION: Leave BL/TR cones in place during recording. They
  serve double duty — FOV validation AND calibration improvement.

PHASE 4 — Record
  Students complete the drill one at a time.
```

**Assessment**: Agility is currently the hardest test to calibrate (28 cones detected vs 4 expected). The BL/TR bounding box approach is **transformative** here because:

1. It defines the spatial ROI *before* detecting drill cones → eliminates cones from other setups
2. The two BL/TR points + 4 drill cones = 6 total calibration points → much more robust homography
3. Colour-coded cones reduce ambiguity within the ROI

**Open question**: Should BL/TR reference cones be a *different* colour from drill cones? Using distinct colours (e.g., blue reference cones, yellow drill cones) would make detection unambiguous. This requires teachers to carry two colours of cones — check if this is acceptable.

---

### Test 7 — Coordination (4-Cone Lateral Tap Sequence)

**What we need to measure**: Total time + sequence error detection. Student taps 4 cones in a 2m × 2m square in a prescribed clockwise order.

**Camera**: Elevated behind, 2.0–2.5m height, covering the full 2m × 2m area.

**Cone layout**: 4 cones in a square — this IS a regular pattern.

**Proposed user flow**:
```
PHASE 1 — FOV Validation
  The square pattern has natural BL/TR corners:
  BL = bottom-left cone of the square (0, 0)
  TR = top-right cone of the square (200, 200)

  These ARE test cones — no separate reference cones needed.

  App shows: "Place your 4 cones in a 2m × 2m square as shown"
  [diagram with numbered positions: 1=BL, 2=BR, 3=TR, 4=TL]

  Teacher places all 4 cones at once (the square is small enough
  that all cones are usually visible once the camera is positioned).

  ✅ "4 cones detected — square pattern confirmed"

PHASE 2 — Calibration (automatic)
  World coords: [(0,0), (200,0), (200,200), (0,200)] — 2m square
  Correspondence: grid_2x2 → 8 D4 candidates

  Regular Y-pattern: the square has 2 cones at Y=0 and 2 at Y=200cm.
  This gives exactly the regular Y-spacing pattern we want for depth
  calibration.

  Additional validation: the 4 corners of the square must form
  approximately right angles (angular check within ±15°).

  ✅ "Calibration valid — reprojection error: 1.2cm"

PHASE 3 — Record
  Students do 3 full sequences, 2 attempts each.
  Pipeline tracks foot position relative to each cone to detect taps
  and validate sequence order.
```

**Assessment**: Coordination is a **natural fit** for the cone-based calibration approach. The 4-cone square IS the test layout AND the calibration grid. The 2×2 grid provides the D4 symmetry group (8 candidates), and with 4 well-separated points the homography is well-conditioned.

**Sequence error detection** is the unique challenge here — the pipeline needs to track *which* cone the foot is near and in *what order*. This requires:
1. Accurate pixel→world mapping (homography) to determine proximity to each cone
2. Temporal tracking of the foot across frames
3. State machine: expected sequence [1→2→3→4→1→2→3→4→1→2→3→4] vs actual

**This test type doesn't exist in the POC yet** — needs a new `CoordinationExtractor`.

---

## Summary: Approach Assessment

### What works well with the BL/TR + Regular Y-Pattern approach:

| Test | Verdict | Rationale |
|------|---------|-----------|
| **Coordination** | **Best fit** | 4-cone square IS the BL/TR + grid. Zero extra cones needed. |
| **Agility** | **Strong fit** | BL/TR solves the over-detection problem by defining ROI. Extra 2 calibration points improve H. |
| **Fitness** | **Good fit** | BL/TR = endpoint cones. Linear Y-pattern with 6 cones. |
| **Sprint** | **Adequate but overkill** | Only 2 cones needed (start/finish). They serve as BL/TR naturally. Linear projection suffices — no full homography needed. |
| **Explosiveness** | **Not applicable** | Single-axis calibration. No cones on the floor. |
| **Mobility** | **Not applicable** | Single-axis calibration. Side-on camera. |
| **Balance** | **Not applicable** | No calibration needed. |

### Where the approach doesn't make sense:

1. **Sprint**: Two cones are sufficient. Making the teacher think about "bottom-left / top-right" for a straight line adds cognitive overhead for no benefit. Better UX: "Place start cone and finish cone. That's it."

2. **Balance / Explosiveness / Mobility**: These don't use floor cones. Forcing a BL/TR step would be confusing and unnecessary.

### Recommended simplification:

Don't present calibration as "calibration" to teachers. Present it as **test setup**:

- "Place your cones as shown in the diagram" (they're placing test cones, not calibrating)
- "Make sure all cones are visible" (natural FOV check)
- The green checkmark appears when detection + validation succeeds

The word "calibration" should never appear in the teacher-facing UI.

---

## Implementation Requirements (Pipeline Changes)

### New: `validate_fov(frame, bl_cone_px, tr_cone_px, test_config) → FOVResult`

```python
@dataclass
class FOVResult:
    bl_visible: bool
    tr_visible: bool
    bl_inset_ok: bool       # >5% from frame edges
    tr_inset_ok: bool
    area_coverage: float    # fraction of frame covered by test area
    is_valid: bool
    feedback_message: str   # human-readable guidance
```

### New: Spatial ROI from BL/TR

Once BL and TR are detected, their pixel positions define the spatial ROI for all subsequent cone detection. This replaces the static `spatial_roi` config with a dynamic, per-session ROI:

```python
roi = {
    "x_min_frac": (bl_cone.cx / frame_width) - margin,
    "x_max_frac": (tr_cone.cx / frame_width) + margin,
    "y_min_frac": (tr_cone.cy / frame_height) - margin,  # TR is farther = higher in frame
    "y_max_frac": (bl_cone.cy / frame_height) + margin,  # BL is nearer = lower in frame
}
```

### Modified: `calibrate_from_layout()` changes

Add optional `bl_tr_px` parameter:
- If provided, BL/TR pixel positions are prepended to the cone list with known world coords
- Spatial ROI is derived from BL/TR instead of static config
- This gives every homography 2 extra known points

### New test extractors needed:

1. **`MobilityExtractor`** — trunk flexion angle + fingertip-to-floor distance
2. **`CoordinationExtractor`** — completion time + sequence error detection

---

## UX Flow Comparison: Current POC vs Proposed

| Step | Current (POC) | Proposed (MVP) |
|------|--------------|----------------|
| Test selection | Not in app (manual) | App menu: select test type |
| Cone placement | Manual, no guidance | Step-by-step with diagrams |
| Camera positioning | Trial and error | On-screen overlay guide |
| FOV validation | None | BL/TR auto-check with feedback |
| Cone detection | Post-hoc (during pipeline) | Real-time during setup |
| Calibration feedback | None (pipeline logs) | Green/red indicator with message |
| Spatial ROI | Static config | Dynamic from BL/TR |
| Error recovery | Re-run pipeline | "Move cone and try again" |

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Teacher can't find BL/TR positions | Blocks testing | Clear diagrams + "place here" overlay on camera feed |
| Over-detection in shared gym | Wrong cones matched | BL/TR ROI eliminates ~80% of false cones |
| HSV detection fails in poor lighting | Calibration blocked | Fall back to SAM3; future: ArUco markers on cones |
| Phone camera FOV too narrow | Can't see all cones | Minimum distance guidance per test ("stand at least 4m away") |
| Teacher removes BL/TR cones before recording | Loses calibration anchors | Lock calibration to session; re-check on record start |
| Multiple simultaneous tests in same gym | Cross-contamination | Per-session ROI from BL/TR isolates each test zone |

---

## Phase Recommendation

| Phase | Calibration capability |
|-------|----------------------|
| **MVP** | Implement BL/TR flow for Agility + Coordination + Fitness. Sprint uses 2-cone linear. Explosiveness uses single-axis. Balance = none. Mobility = single-axis (new extractor). |
| **Phase 2** | ArUco markers on cone tops for unambiguous detection. Auto-camera-tilt estimation. Multi-phone calibration sync (same session, different tests). |

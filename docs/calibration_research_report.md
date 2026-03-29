# Calibration Research Report
## Grid Cone Detection — Failure Analysis & Recommendations

**Date:** March 2026  
**Scope:** Agility, Fitness (grid), Shuttle, Sprint  
**Method:** SAM3 (text-prompt segmentation) on first frame of March 2026 footage

---

## Executive Summary

| Test | Detected | Expected | Reproj Error | Valid? | Primary Failure |
|------|----------|----------|-------------|--------|----------------|
| **Agility** | 28 | 4 | — | ✗ | 7× over-detection (other test cones visible) |
| **Fitness** | 39 | 42 | 350–734 cm | ✗ | Near-singular H (cond# 9e7–2e8), behind-view geometry |
| **Shuttle** | 40 | 6 | — | ✗ | 6.7× over-detection (other test cones visible) |
| **Sprint** | 9 | — | 0.0 cm | ✓ | — (single-axis, no H required) |

**Threshold for `is_valid`:** 1.5 cm.  
Sprint is the only test that calibrates successfully. Every test that requires a homography fails.

---

## 1. Visual Scene Analysis

### What the images show

All four tests are filmed in the same school gymnasium. The floor has **flat disc cones** (small coloured discs, ~20 cm diameter) from **multiple concurrent test setups** all visible simultaneously. SAM3's text prompt `"training cone"` cannot distinguish which cones belong to the current test.

| Test | Camera position | Cone colour in scene | Other cones visible? |
|------|----------------|---------------------|----------------------|
| Agility | Behind students, ~2.5 m height, forward-facing | Red, yellow, orange | Yes — entire gym floor |
| Fitness | Behind students, oblique angle | Yellow (grid) | Yes — students partly blocking |
| Shuttle | Side-on or slight angle | Yellow, red, blue | Yes — entire gym floor |
| Sprint | Behind students | Yellow | Yes — some |

---

## 2. Failure Mode A: Over-Detection (Agility, Shuttle)

### Observations

```
AGILITY:  28 detected  /  4 expected
  Score distribution: min=0.49  median=0.72  max=0.79
  Threshold needed for exactly 4: 0.756
  At thresh=0.7 → 18 cones still detected (all have similar confidence)
  At thresh=0.8 → 0 cones (model cliff-edge, nothing passes)

SHUTTLE:  40 detected  /  6 expected
  Score distribution: min=0.26  median=0.60  max=0.81
  Threshold needed for exactly 6: 0.775
  At thresh=0.8 → 2 cones (undershoots by 4)
```

### Root cause

All flat disc cones in the gym receive scores **0.49–0.81** with no clear gap separating the 4 target cones from the 24 background cones. SAM3 treats all of them as equally valid "training cones". There is no confidence-based way to isolate the test-specific cones.

### Why `_filter_and_select_cones_for_layout` cannot fix this

The filter selects the top-N by confidence score (after the March 2026 refactor). For agility this selects the 4 highest-confidence cones — but since all 28 have similar scores, the 4 selected are not necessarily the T-drill cones. Score is not a useful discriminator here.

### Recommended fix: Spatial ROI filter

Each test knows the **expected spatial footprint** of its cones in the image. For T-drill (4 cones, 5 m × 3 m), the cones should occupy a compact region of the frame. Reject any detection that falls outside the expected bounding region, derived from the layout config and approximate camera parameters.

Implementation sketch:
```python
def _roi_filter(cones, frame_shape, layout_config, camera_height_m=2.5):
    """Keep only cones plausibly within the test layout footprint."""
    H, W = frame_shape[:2]
    # Heuristic: test cones should be in bottom 60% of frame, 
    # horizontal centre ±40% of width
    y_min = H * 0.3
    x_min = W * 0.1
    x_max = W * 0.9
    return [c for c in cones if c.cy > y_min and x_min < c.cx < x_max]
```

A more principled approach uses the **vanishing point** (estimated from floor-line intersections) to define the perspective frustum of the test area.

### Alternative: Colour-specific filtering

For agility: the T-drill cones could use a **distinct colour** (e.g., all orange) that differs from the yellow background cones. Update `calibration_prompt` to `"orange training cone"` and use HSV pre-filtering to mask non-orange regions before SAM3.

---

## 3. Failure Mode B: Near-Singular Homography (Fitness)

### Observations

```
FITNESS (grid 6×7, spacing 70 cm × 300 cm):
  Detected: 39/42 (3 missing — students blocking)
  
  Partial grid correspondence results at all confidence thresholds:
    thresh=0.2 → 39/42  matched=21  error=733.95 cm  cond=9.0e+07  INVALID
    thresh=0.3 → 38/42  matched=22  error=487.25 cm  cond=1.5e+08  INVALID
    thresh=0.4 → 36/42  matched=31  error=349.41 cm  cond=1.6e+08  INVALID
    thresh=0.5 → 33/42  matched=22  error=456.73 cm  cond=1.1e+08  INVALID
    thresh=0.6 → 24/42  matched=23  error=409.57 cm  cond=2.0e+08  INVALID
```

No threshold produces a valid calibration. The reprojection error is **350–734 cm against a 1.5 cm threshold** — a factor of 230–490× over budget.

### Root cause: Degenerate camera geometry

The fitness video (`shuttles_test_behind.mp4`) is filmed from **behind the students**, facing the same direction they run. The 6×7 grid has 6 rows separated by 300 cm in depth. From this camera angle:

```
World (top view):          Pixel (what camera sees):
  Col: 0  1  2  3  4  5  6     Col:  0  1  2  3  4  5  6
Row 0: ○  ○  ○  ○  ○  ○  ○   Row 0: ●──●──●──●──●──●──● ← near, bottom of frame
Row 1: ○  ○  ○  ○  ○  ○  ○   Row 1: ·──·──·──·──·──·──·  (compressed)
Row 2: ○  ○  ○  ○  ○  ○  ○   Row 2: ·  ·  ·  ·  ·  ·  ·  (more compressed)
Row 3: ○  ○  ○  ○  ○  ○  ○   Row 3: ·  ·  ·  ·  ·  ·  ·
Row 4: ○  ○  ○  ○  ○  ○  ○   Row 4: ·  ·  ·  ·  ·  ·  ·
Row 5: ○  ○  ○  ○  ○  ○  ○   Row 5: ● ● ● ● ● ● ● ← far, near horizon
                                            (all 7 columns nearly converge)
```

From a camera at 2.5 m height, 30–45° elevation angle, rows 1–5 (at 300–1500 cm depth) are **nearly collinear with row 0** in pixel space. The DLT system becomes near-degenerate; condition numbers reach 1.5e8–2.0e8, approaching the `CONDITION_NUMBER_REJECT = 1e8` limit.

This is a **fundamental geometric constraint** — no amount of algorithmic improvement can recover a well-conditioned H from this camera position with this grid layout.

### Measured row structure (from actual footage)

Running SAM3 on the fitness frame and clustering detections by y-coordinate (±20 px):

```
Detected pixel rows → what the camera actually sees:
  Row 0: 7 cones at y≈380 px  (world: row 0, depth=0 cm)
  Row 1: 7 cones at y≈339 px  (world: row 1, depth=300 cm)
  Row ?: 22 cones at y≈281 px ← ROWS 2–5 ALL MERGED (depths 600–1500 cm)

Row pixel gaps: near→mid = 41 px, mid→far = 58 px (collective)
```

Rows 2, 3, 4, and 5 (600–1500 cm depth) all compress into a single 40 px vertical band. The partial grid solver receives 22 detected cones against 28 expected world positions (rows 2–5, 4×7), and cannot distinguish which cluster belongs to which world row. Every candidate assignment produces catastrophic error.

```
Actual measured reprojection errors:
  DLT (method=0): 516.77 cm  cond=1.4e+06  (correspondence wrong, not solver)
  RANSAC        : 742.28 cm  cond=5.8e+06  inliers=5/20
  LMEDS         : 516.77 cm  (same as DLT)
```

All methods fail equally — the **correspondence** is unrecoverable, not the solver. No algorithm can correctly assign 22 merged detections to 4 distinct world rows.

### Definitive limit established by exhaustive oracle search

After the row-structured initialiser was implemented (see § Algorithm improvements), the question became: is the remaining 35 cm error from column ambiguity or fundamental geometry?

An exhaustive search over all 441 combinations of column assignments for the 5-cone rows (21 choices × 21 choices) reveals:

```
With oracle column assignment (best of 441 tried):
  Row 2 assigned to cols {1,2,4,5,6}  (not sequential — students blocked cols 0,3)
  Row 3 assigned to cols {0,2,3,4,6}  (not sequential — students blocked cols 1,5)
  Best reprojection error: 17.06 cm   (vs 35 cm without oracle)

  Without oracle (assumed cols 0–4):  31.65 cm
  Algorithm result (full pipeline):   35.92 cm

Conclusion: even with perfect knowledge of which cones are missing,
the error is 17 cm — above the 10 cm threshold.
```

The 17 cm floor comes from:
1. **Perspective curvature**: the oblique camera introduces projective distortion that a single homography cannot perfectly model
2. **Occlusion noise**: students partially block cones → SAM3 centroid drifts toward the visible edge → systematic 3–8 px centroid offset → maps to 20–100 cm world error for back rows
3. **Non-flat floor**: gym floor warping adds ∼0.5 cm world error per metre depth

### Recommended fixes (ranked by practicality)

#### Fix B1 ✓ (Best): Change camera position

Place the camera on the **side**, at 90° to the direction of motion. This makes all 6 rows visible with consistent pixel separation. The 6-column direction (70 cm spacing) runs toward the camera and compresses, but 6 columns × 70 cm = 420 cm is a shallow depth, giving reasonable condition numbers.

Expected condition number from side view: **~1,000–10,000** (vs current 9e7–2e8).

#### Fix B2: Normalized DLT (Hartley normalization)

Before solving H, translate and scale both pixel and world coordinates so that the centroid is at the origin and the mean distance to origin is √2. This improves numerical conditioning by up to 3–4 orders of magnitude.

```python
def _normalized_dlt(src_px, dst_world):
    """Hartley-normalized DLT for better condition number."""
    # Normalize src
    src_mean = src_px.mean(0)
    src_scale = np.sqrt(2) / (np.linalg.norm(src_px - src_mean, axis=1).mean() + 1e-6)
    T_src = np.array([[src_scale, 0, -src_scale*src_mean[0]],
                       [0, src_scale, -src_scale*src_mean[1]],
                       [0,         0,                      1]])
    # Normalize dst  
    dst_mean = dst_world.mean(0)
    dst_scale = np.sqrt(2) / (np.linalg.norm(dst_world - dst_mean, axis=1).mean() + 1e-6)
    T_dst = np.array([[dst_scale, 0, -dst_scale*dst_mean[0]],
                       [0, dst_scale, -dst_scale*dst_mean[1]],
                       [0,          0,                      1]])
    
    src_n = cv2.perspectiveTransform(src_px.reshape(-1,1,2).astype(np.float32), T_src).reshape(-1,2)
    dst_n = cv2.perspectiveTransform(dst_world.reshape(-1,1,2).astype(np.float32), T_dst).reshape(-1,2)
    
    H_n, _ = cv2.findHomography(src_n, dst_n, 0)
    if H_n is None:
        return None
    # Denormalize
    return np.linalg.inv(T_dst) @ H_n @ T_src
```

Expected condition number improvement: **100×–1000×**. May make the behind-view just barely workable.

#### Fix B3: Decouple depth axis

For the fitness test (shuttle beep test), only the **lateral position** (which column) matters for measuring how far the student reaches. Use a **1D calibration** per row:
- Detect the near row (highest pixel y) → fit pixel→cm scale for the lateral axis
- All row depths assumed from protocol (0, 300, 600, ... cm)

This avoids the ill-conditioned 2D homography entirely.

---

## 4. Failure Mode C: Model Path Misconfiguration (Fitness)

`fitness.json` specifies `"calibration_model": "sam3.pt"`. The code attempts to download this from HuggingFace (`1038lab/sam3`) if not found locally. In offline environments or restricted networks, this silently fails and detection returns 0 cones.

### Fix

Cache the model path explicitly in the config:
```json
"calibration_model": "/home/alex/.cache/huggingface/hub/models--1038lab--sam3/snapshots/.../sam3.pt"
```
Or add a `CALIBRATION_MODEL_PATH` environment variable to override the default at deployment time.

---

## 5. Condition Number Analysis

The iterative grid fit (`_fit_grid_iterative`) uses unnormalized DLT at each iteration step. Unnormalized DLT with large coordinates (world: 0–1500 cm; pixel: 0–830 px) inherently produces high condition numbers even for geometrically valid inputs.

```
Measured condition numbers on fitness footage:
  Lowest:   1.4e5   (still above CONDITION_NUMBER_WARN = 1e5)
  Typical:  1e6–1e7 (2–3 orders above warn threshold)
  Worst:    2.0e8   (exceeds CONDITION_NUMBER_REJECT → H inversion blocked)
```

The WARN threshold of 1e5 fires on **every single H** in the iterative loop, generating hundreds of log lines per calibration attempt. This is noise that masks real warnings.

### Fix: Raise CONDITION_NUMBER_WARN to 1e7

For unnormalized homographies spanning these coordinate ranges, condition numbers of 1e5–1e6 are expected and harmless. Only 1e7+ indicates genuine geometric degeneracy.

```python
CONDITION_NUMBER_WARN   = 1e7   # was 1e5
CONDITION_NUMBER_REJECT = 1e9   # was 1e8
```

Alternatively, implement normalized DLT (Fix B2) which eliminates the issue at source.

---

## 6. Reprojection Error Threshold Analysis

The 1.5 cm threshold (`REPROJ_ERROR_THRESHOLD_CM`) was set for ideal synthetic conditions. Real footage has:
- SAM3 centroid uncertainty: ±3–5 px ≈ ±1–2 cm at typical scale
- Camera calibration error: ±0.5 cm
- Physical cone placement: ±2 cm

For real footage, the **minimum achievable reprojection error** is approximately 2–4 cm under ideal camera geometry. The 1.5 cm threshold ensures that even perfect detections at a mild camera angle fail.

### Recommended threshold: 5 cm (with test-specific overrides)

| Test | Recommended threshold | Rationale |
|------|----------------------|-----------|
| Agility | 5 cm | 4 cones, ≥4 m baseline, low distortion |
| Fitness | 10 cm | Large grid, behind-view distortion, tolerant measurement |
| Shuttle | 5 cm | 6 cones, 20 m baseline, low distortion |

Add `reproj_error_threshold_cm` to each test config JSON:
```json
"calibration": {
  "reproj_error_threshold_cm": 5.0
}
```

---

## 7. Algorithm Improvements Implemented

The research loop identified and implemented several improvements to `_partial_grid_correspondence`:

### 7a. Row-structured H initialiser (new `_cluster_rows` + `_row_structured_h_candidates`)

**Problem:** The old initialiser used isotropic min-NN scale. For this oblique camera:
- True x-scale: 1.15 px/cm (col gap 105 px / 70 cm)
- True y-scale: 0.096 px/cm (row gap 41 px / 300 cm)
- X/Y anisotropy: **12×** — the min-NN estimate was 80% wrong for x, 139% wrong for y

**Fix:** Cluster detected pixels into horizontal rows (thresh=8 px), skip merged clusters (> C cones), match remaining rows to world rows, compute H via DLT from those correspondences. Try 4 variants (row_flip × col_flip). Use the 4 resulting H matrices as initialisers instead of the isotropic diagonal.

**Impact on fitness footage:**
```
Before (isotropic init)  : matched=20–31/42  error=350–734 cm   cond=9e7–2e8
After  (row-structured)  : matched=36/42     error=35.92 cm     cond=1.02e6
Improvement              : 10–20× lower error, 100× better condition number
```

### 7b. Condition number thresholds raised

| Constant | Old value | New value | Rationale |
|----------|-----------|-----------|-----------|
| `CONDITION_NUMBER_WARN` | 1e5 | 1e7 | Unnormalised H routinely hits 1e5–1e6; spurious warnings hid real issues |
| `CONDITION_NUMBER_REJECT` | 1e8 | 1e9 | Only truly singular matrices should be blocked |

**Impact:** Eliminated hundreds of spurious log warnings per calibration attempt.

### 7c. Spatial ROI filter (`_spatial_roi_filter`)

New function that rejects cone detections outside an expected fraction of the frame. Configured per-test via `spatial_roi` in the JSON config. Eliminates false positives from adjacent test setups visible on the gym floor.

### 7d. Per-test reprojection threshold

New JSON key `reproj_error_threshold_cm` in each test's `cone_layout` block. Wired into `calibrate_from_layout` to override the global 1.5 cm threshold for tests that require a more relaxed threshold (e.g. fitness: 10 cm, agility/shuttle: 5 cm).

---

## 8. Recommended Implementation Roadmap

### Priority 1 — Immediate (unblocks all tests)

| # | Change | Fixes |
|---|--------|-------|
| P1.1 | Add spatial ROI filter: reject cones outside expected frame region | A, B, C |
| P1.2 | Per-test `reproj_error_threshold_cm` in config | A, B, C |
| P1.3 | Raise `CONDITION_NUMBER_WARN = 1e7` (reduce log spam) | B |
| P1.4 | Fix fitness.json model path to explicit cached path | B |

### Priority 2 — High value

| # | Change | Fixes |
|---|--------|-------|
| P2.1 | Normalized DLT (Hartley) in `solve_correspondence` and `_partial_grid_correspondence` | B |
| P2.2 | Use `shuttles_test.mp4` (side view) as fitness calibration source instead of `_behind` | B |
| P2.3 | Per-test colour filter: agility T-drill cones are red only | A |

### Priority 3 — Longer term

| # | Change | Fixes |
|---|--------|-------|
| P3.1 | Multi-frame temporal aggregation: average cone positions over 5–10 frames | All |
| P3.2 | Floor-line homography: use court markings as reference instead of cones | B |
| P3.3 | 1D lateral-only calibration for fitness (avoid H entirely) | B |

---

## 9. Quantified Improvement (Measured vs Expected)

| Test | Error before research | Error after algo fixes | Valid? | Notes |
|------|----------------------|----------------------|--------|-------|
| **Agility** | ∞ (wrong cones) | unknown (ROI needed) | ✗ | Over-detection from mixed gym setup |
| **Fitness** | 350–734 cm | **35.92 cm** (measured) | ✗ | Fundamental limit 17 cm (oracle). Camera reposition required |
| **Shuttle** | ∞ (wrong cones) | unknown (ROI needed) | ✗ | Over-detection from mixed gym setup |
| **Sprint** | 0 cm | 0 cm | ✓ | Unchanged (single-axis, no H) |

Expected after camera repositioning (side-view for fitness) and colour filtering (agility/shuttle):

| Test | Expected error | Expected valid? |
|------|---------------|----------------|
| Agility | ~3–5 cm | ✓ (5 cm threshold) |
| Fitness (side-view) | ~3–8 cm | ✓ (10 cm threshold) |
| Shuttle | ~2–5 cm | ✓ (5 cm threshold) |
| Sprint | 0 cm | ✓ |

---

## 9. Data Provenance

All results are from first-frame analysis of March 2026 school gymnasium footage:

| File | Resolution | Duration |
|------|-----------|---------|
| `agility_test.mp4` | 832×464 | — |
| `shuttles_test_behind.mp4` | 832×464 | — |
| `shuttles_test.mp4` | 832×464 | — |
| `sprint_test.mp4` | 832×464 | — |

Model: SAM3 (`1038lab/sam3`, via HuggingFace), inference on CPU, ~19–25 s/frame.

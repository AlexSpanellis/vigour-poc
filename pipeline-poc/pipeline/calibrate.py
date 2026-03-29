"""
Module 6 — Cone Detection & Camera Calibration
Interface: Calibrator.calibrate_homography / calibrate_single_axis → CalibrationResult

Recommended approach: HSV segmentation → contour centroids → cv2.findHomography.
Alternatives: Fine-tuned YOLO for cones, ArUco markers, floor court lines.
See: notebooks/05_calibration_eval.ipynb

HSV Ranges (March 2026 school hall footage — re-tune on first frame of each clip):
    Yellow:     H 18–35,   S 80–255,  V 80–255   (primary lane markers)
    Orange/Red: H 5–18,    S 100–255, V 100–255  (mid-lane agility markers)
    Blue:       H 100–130, S 80–255,  V 50–255   (far-end depth reference)
    Red:        H 0–5 or 170–180, S 100–255, V 100–255 (grid markers)

Decision log:
    Date | Approach | Reprojection Error | Detection Rate | Verdict
    ——   | ——       | ——                 | ——             | ——
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import cv2
import numpy as np

from pipeline.cone_layout import (
    generate_cone_world_coords,
    generate_cone_world_coords_from_pixels,
)
from pipeline.models import CalibrationResult

logger = logging.getLogger(__name__)

# Reprojection error threshold (cm) for is_valid.  Calibrations above this are
# rejected and will not be written to metric_value.
REPROJ_ERROR_THRESHOLD_CM = 1.5

# Homography condition number limits.
# Important: raw H matrices have large condition numbers when point coordinates
# span wide ranges (e.g. pixel domain [0,1920] vs world [0,500 cm]).  These
# thresholds apply to the RAW (unnormalised) H returned by cv2.findHomography.
#
# WARN   – log a diagnostic warning; geometry may be marginal.
# REJECT – H is so numerically degenerate (rows nearly identical) that even
#           SVD inversion is unreliable.  In practice this only occurs when
#           cones are nearly coincident in image space or the camera is nearly
#           parallel to the floor.
CONDITION_NUMBER_WARN = 1e7    # raised from 1e5 — unnormalised H on real footage routinely hits 1e5–1e6
CONDITION_NUMBER_REJECT = 1e9  # raised from 1e8 — only flag truly degenerate matrices


class CalibrationError(Exception):
    """Raised when calibration cannot produce a geometrically valid result.

    Callers at the session boundary must catch this and record a
    ``calibration_failed`` event rather than letting a bad ``metric_value``
    reach the database.
    """


# ---------------------------------------------------------------------------
# Geometric correspondence solver (Fix 1)
# ---------------------------------------------------------------------------

def _enumerate_valid_assignments(world_pts: np.ndarray, layout: str) -> list[list[int]]:
    """Return the set of candidate world-point permutations for *layout*.

    Each element ``a`` is a list of length N where ``a[i]`` is the index into
    ``world_pts`` that ``pixel_pts[i]`` should be matched to.

    Layout strings
    --------------
    ``'linear'``      → 2 candidates (forward / reversed)
    ``'grid_RxC'``    → 8 candidates (dihedral group D₄: 4 rotations × 2 reflections)
    ``'irregular'``   → all N! permutations for N ≤ 6; 2·|hull| candidates for N > 6
    """
    N = len(world_pts)

    if layout == "linear":
        return [list(range(N)), list(range(N - 1, -1, -1))]

    if layout.startswith("grid_"):
        parts = layout[5:].split("x")
        R, C = int(parts[0]), int(parts[1])
        if R * C != N:
            raise CalibrationError(
                f"Grid layout '{layout}' expects {R * C} cones but got {N}."
            )
        grid = np.arange(N).reshape(R, C)
        candidates: list[list[int]] = []
        seen: set[tuple] = set()
        g = grid.copy()
        for _ in range(4):
            for variant in (g, np.fliplr(g)):
                flat = tuple(variant.flatten().tolist())
                if flat not in seen:
                    candidates.append(list(flat))
                    seen.add(flat)
            g = np.rot90(g)
        return candidates  # at most 8 (fewer for square grids with extra symmetry)

    # Irregular / unknown layout
    if N <= 6:
        from itertools import permutations
        return [list(p) for p in permutations(range(N))]

    return _hull_ordered_candidates(world_pts, N)


def _hull_ordered_candidates(world_pts: np.ndarray, N: int) -> list[list[int]]:
    """Generate 2·|hull| candidates from convex-hull cyclic orderings."""
    hull = cv2.convexHull(world_pts.astype(np.float32), returnPoints=False)
    if hull is None or len(hull) < 3:
        # Degenerate hull — fall back to brute force if small enough
        if N <= 6:
            from itertools import permutations
            return [list(p) for p in permutations(range(N))]
        return [list(range(N))]  # last-resort single candidate

    hull_idx = hull.flatten().tolist()
    interior = [i for i in range(N) if i not in hull_idx]
    candidates: list[list[int]] = []
    for start in range(len(hull_idx)):
        rotated = hull_idx[start:] + hull_idx[:start]
        for flip in (False, True):
            seq = rotated[::-1] if flip else rotated
            candidates.append(seq + interior)
    return candidates


def _spatial_roi_filter(
    cone_objects: list,
    frame_shape: tuple[int, int],
    roi_config: dict | None,
) -> list:
    """Drop detections that fall outside the expected spatial region of the frame.

    Eliminates cones from other test setups visible on the gym floor.
    ``roi_config`` keys (all optional, normalised 0–1):
        ``y_min_frac``: minimum y fraction (default 0.25 — ignore ceiling/wall cones)
        ``y_max_frac``: maximum y fraction (default 0.97)
        ``x_min_frac``: minimum x fraction (default 0.05)
        ``x_max_frac``: maximum x fraction (default 0.95)
    """
    if not roi_config and roi_config != {}:
        return cone_objects
    H, W = frame_shape[:2]
    cfg = roi_config or {}
    y_min = H * cfg.get("y_min_frac", 0.25)
    y_max = H * cfg.get("y_max_frac", 0.97)
    x_min = W * cfg.get("x_min_frac", 0.05)
    x_max = W * cfg.get("x_max_frac", 0.95)
    before = len(cone_objects)
    filtered = [
        c for c in cone_objects
        if y_min <= c.cy <= y_max and x_min <= c.cx <= x_max
    ]
    if len(filtered) < before:
        logger.debug(
            "Spatial ROI filter: kept %d/%d detections (y=[%.0f,%.0f] x=[%.0f,%.0f]).",
            len(filtered), before, y_min, y_max, x_min, x_max,
        )
    return filtered


def h_from_camera_extrinsics(
    height_cm: float,
    tilt_deg: float,
    image_width: int,
    image_height: int,
    focal_length_px: float | None = None,
    fov_horizontal_deg: float | None = None,
    camera_x_world_cm: float = 0.0,
    camera_y_world_cm: float = 0.0,
    pan_deg: float = 0.0,
) -> np.ndarray:
    """Compute an approximate homography (world XY → pixel) from camera extrinsics.

    The resulting H can initialise ``_partial_grid_correspondence`` far more
    accurately than either the isotropic min-NN scale or the row-structured DLT,
    because it encodes the exact perspective geometry for the oblique camera angle.
    Even rough estimates (height ± 10 %, tilt ± 5°) give initial reprojection
    errors of 5–20 cm, close enough for the iterative NN to converge correctly.

    Coordinate conventions
    ----------------------
    - World origin: first cone of the grid.
    - World X: lateral (rightward when facing the grid).
    - World Y: depth (away from camera, toward far rows).
    - World Z: up (positive).
    - Camera is at world position (camera_x_world_cm, camera_y_world_cm, height_cm).
    - ``tilt_deg``: camera looks *downward* this many degrees from horizontal
      (0 = level, 90 = straight down).
    - ``pan_deg``: camera rotates around the vertical axis (0 = facing +Y direction).

    Parameters
    ----------
    height_cm        : camera height above the floor (e.g. 250 cm).
    tilt_deg         : downward tilt angle in degrees from horizontal (e.g. 30).
    image_width      : frame width in pixels (e.g. 832).
    image_height     : frame height in pixels (e.g. 464).
    focal_length_px  : focal length in pixels.  Either this or ``fov_horizontal_deg``
                       must be provided.
    fov_horizontal_deg: horizontal field-of-view in degrees.  Used to derive
                       focal length when ``focal_length_px`` is None.
    camera_x_world_cm: lateral camera position in world coords (default 0 = grid centre).
    camera_y_world_cm: depth camera position in world coords (default 0 = near row).
                       Set to a negative value if camera is *behind* row 0.
    pan_deg          : yaw around vertical axis; 0 = camera faces exactly +Y direction.

    Returns
    -------
    H : (3, 3) float64 array mapping world (X, Y) to pixel (u, v).
    """
    if focal_length_px is None:
        if fov_horizontal_deg is None:
            raise ValueError("Provide either focal_length_px or fov_horizontal_deg.")
        focal_length_px = (image_width / 2.0) / np.tan(np.radians(fov_horizontal_deg / 2.0))

    cx = image_width / 2.0
    cy = image_height / 2.0
    K = np.array([
        [focal_length_px, 0.0, cx],
        [0.0, focal_length_px, cy],
        [0.0, 0.0, 1.0],
    ], dtype=np.float64)

    # Camera position in world coordinates.
    C_world = np.array([camera_x_world_cm, camera_y_world_cm, height_cm], dtype=np.float64)

    # Build rotation matrix.
    # Base: camera faces +Y (into the scene), tilted down by tilt_deg.
    tilt = np.radians(tilt_deg)
    pan  = np.radians(pan_deg)

    # Optical axis in world (camera looks in +Y, tilted down):
    look = np.array([np.sin(pan), np.cos(pan), 0.0])  # horizontal part
    look = np.array([
        np.cos(tilt) * np.sin(pan),
        np.cos(tilt) * np.cos(pan),
        -np.sin(tilt),  # negative = downward
    ])

    # World up = +Z; project out look component to get camera up.
    world_up = np.array([0.0, 0.0, 1.0])
    right = np.cross(look, world_up)
    right /= np.linalg.norm(right) + 1e-12
    cam_up = np.cross(right, look)
    cam_up /= np.linalg.norm(cam_up) + 1e-12

    # Camera axes as rows of rotation matrix (world→camera).
    # Camera x (rightward in image) = right
    # Camera y (downward in image)  = -cam_up
    # Camera z (optical axis)       = look
    R = np.stack([right, -cam_up, look], axis=0)  # (3, 3)

    # Translation: t = -R @ C_world
    t = -(R @ C_world)  # (3,)

    # For a world point on the ground plane (Z=0), the projection is:
    #   pixel = K * (R[:,0]*X + R[:,1]*Y + t)
    # This is H = K * [r0 | r1 | t] where r0, r1 are columns 0,1 of R.
    M = K @ np.column_stack([R[:, 0], R[:, 1], t])  # (3, 3)
    H = M / (M[2, 2] + 1e-12)
    return H.astype(np.float64)


def auto_fit_camera_extrinsics(
    pixel_pts: np.ndarray,
    world_pts: np.ndarray,
    camera_orientation: str,
    height_cm: float,
    image_width: int,
    image_height: int,
) -> np.ndarray | None:
    """Automatically fit camera extrinsics from a small number of physical priors.

    The user only needs to supply:
      - ``camera_orientation``: ``"behind"`` (camera films along the depth axis,
        rows appear as horizontal bands) or ``"side"`` (camera films perpendicular
        to depth, rows appear as vertical columns).
      - ``height_cm``: approximate camera height above the floor.

    Everything else (tilt angle, focal length, camera horizontal position) is
    solved automatically by fitting to the detected cone pixel positions.  This
    works because knowing the orientation constrains which axis is the "depth"
    axis in the image, and height constrains the relationship between tilt and
    distance.

    The result is a **world→pixel** homography matrix (same convention as
    :func:`h_from_camera_extrinsics`) that can be passed as
    ``camera_extrinsics_H`` to :func:`_partial_grid_correspondence` — which
    automatically inverts it to pixel→world for its internal NN loop.

    Parameters
    ----------
    pixel_pts          : (N, 2) detected cone pixel positions.
    world_pts          : (M, 2) world coordinates of all grid cones.
    camera_orientation : ``"behind"`` or ``"side"``.
    height_cm          : camera height above the floor in cm.
    image_width        : frame width in pixels.
    image_height       : frame height in pixels.

    Returns
    -------
    H (3, 3) world→pixel homography, or ``None`` if fitting fails.
    """
    try:
        from scipy.optimize import minimize
    except ImportError:
        logger.warning("scipy not available — cannot auto-fit camera extrinsics.")
        return None

    if len(pixel_pts) < 6:
        return None

    cx_img = image_width / 2.0
    cy_img = image_height / 2.0

    orientation = camera_orientation.lower().strip()

    if orientation == "behind":
        # Camera faces in the +Y world direction (depth axis).
        # Detected rows cluster into horizontal pixel bands; Y-world increases
        # with decreasing pixel-y (rows get higher in the image as they're farther away).
        # Cluster into pixel rows and use their mean-y as fitting targets.
        from pipeline.calibrate import _cluster_rows as _cr
        px_rows = _cr(pixel_pts, thresh_px=10.0, min_row_size=3)
        if len(px_rows) < 2:
            return None

        # Assign pixel rows (nearest first = largest pixel-y) to world rows
        # (smallest world-Y first).
        world_grid = world_pts.reshape(-1, int(round(len(world_pts) ** 0.5 + 0.5)))
        # Get unique world Y values (sorted ascending = near to far)
        world_Ys = sorted(set(float(p[1]) for p in world_pts))
        world_Xs = sorted(set(float(p[0]) for p in world_pts))
        n_fit = min(len(px_rows), len(world_Ys))

        obs_row_y   = [float(np.mean(pixel_pts[r, 1])) for r in px_rows[:n_fit]]
        # Also use leftmost/rightmost of the nearest row (row 0) for x-calibration.
        r0_sorted = sorted(px_rows[0].tolist(), key=lambda i: pixel_pts[i, 0])
        obs_x_left  = float(pixel_pts[r0_sorted[0], 0])
        obs_x_right = float(pixel_pts[r0_sorted[-1], 0])
        left_X  = world_Xs[0]
        right_X = world_Xs[-1]
        w_Ys    = world_Ys[:n_fit]

        def predict_vy(theta, d, f, Y_world):
            sin_t, cos_t = np.sin(theta), np.cos(theta)
            cam_y = -sin_t * (Y_world + d) + cos_t * height_cm
            cam_z =  cos_t * (Y_world + d) + sin_t * height_cm
            if cam_z <= 0:
                return 1e6
            return cy_img + f * cam_y / cam_z

        def predict_vx(theta, d, f, cx_world, X_world):
            sin_t, cos_t = np.sin(theta), np.cos(theta)
            cam_z = cos_t * d + sin_t * height_cm  # Y_world=0 (near row)
            if cam_z <= 0:
                return 1e6
            return cx_img + f * (X_world - cx_world) / cam_z

        def loss(params):
            theta, d, f, cx_world = params
            if d < 10 or f < 50 or theta < 1e-4 or theta > 1.5:
                return 1e10
            total = sum(
                (predict_vy(theta, d, f, Y) - v_obs) ** 2
                for Y, v_obs in zip(w_Ys, obs_row_y)
            )
            total += (predict_vx(theta, d, f, cx_world, left_X)  - obs_x_left) ** 2
            total += (predict_vx(theta, d, f, cx_world, right_X) - obs_x_right) ** 2
            return total

        best_result, best_loss = None, np.inf
        grid_cx = float(np.mean([p[0] for p in world_pts]))
        for theta0 in np.radians([5, 10, 15, 20, 25]):
            for d0 in [100, 500, 1000, 2000]:
                for f0 in [300, 600, 1200]:
                    r = minimize(loss, [theta0, d0, f0, grid_cx],
                                 bounds=[(1e-3, 1.4), (10, 5000), (50, 3000), (0, 2 * max(world_Xs))],
                                 method="L-BFGS-B", options={"maxiter": 400})
                    if r.fun < best_loss:
                        best_loss = r.fun
                        best_result = r.x

        if best_result is None or best_loss > 1e6:
            return None

        theta, d, f, cx_world = best_result
        rms_px = float(np.sqrt(best_loss / (n_fit + 2)))
        logger.info(
            "Auto-fit camera extrinsics (behind): tilt=%.1f° dist=%.0fcm "
            "focal=%.0fpx cx_world=%.0fcm  RMS=%.1fpx",
            np.degrees(theta), d, f, cx_world, rms_px,
        )
        return h_from_camera_extrinsics(
            height_cm=height_cm,
            tilt_deg=float(np.degrees(theta)),
            image_width=image_width,
            image_height=image_height,
            focal_length_px=float(f),
            camera_x_world_cm=float(cx_world),
            camera_y_world_cm=float(-d),
        )

    elif orientation == "side":
        # Camera faces along the +X world direction (lateral axis becomes depth).
        # Detected columns cluster into vertical pixel bands at different world-X.
        # Cluster into pixel *columns* (sort by pixel-x) and use mean-x as targets.
        px_cols_raw = sorted(pixel_pts[:, 0].tolist())
        # Simple 1-D clustering of x-coords
        breaks = [0] + [i + 1 for i in range(len(px_cols_raw) - 1)
                        if px_cols_raw[i + 1] - px_cols_raw[i] > 15] + [len(px_cols_raw)]
        px_col_groups = [px_cols_raw[breaks[i]:breaks[i + 1]]
                         for i in range(len(breaks) - 1) if breaks[i + 1] - breaks[i] >= 3]
        if len(px_col_groups) < 2:
            return None

        world_Xs = sorted(set(float(p[0]) for p in world_pts))
        world_Ys = sorted(set(float(p[1]) for p in world_pts))
        n_fit = min(len(px_col_groups), len(world_Xs))

        obs_col_x = [float(np.mean(grp)) for grp in px_col_groups[:n_fit]]
        # Near column (smallest world-X) should appear at largest pixel-x (if camera on left)
        # or smallest pixel-x (if camera on right).  Try both.
        w_Xs = world_Xs[:n_fit]

        # Grab top/bottom of the nearest column for y-calibration.
        near_col_pts = sorted(
            [(px[1], ) for px in pixel_pts if abs(px[0] - obs_col_x[0]) < 25]
        )
        if len(near_col_pts) < 2:
            obs_y_top = cy_img - 50
            obs_y_bot = cy_img + 50
        else:
            obs_y_top = float(near_col_pts[0][0])
            obs_y_bot = float(near_col_pts[-1][0])
        top_Y  = world_Ys[0]
        bot_Y  = world_Ys[-1]

        def predict_side_vx(theta, d, f, X_world, flip=1.0):
            sin_t, cos_t = np.sin(theta), np.cos(theta)
            cam_x = flip * (X_world + d)
            cam_z = cos_t * (X_world + d) + sin_t * height_cm
            if cam_z <= 0:
                return 1e6
            return cx_img + f * cam_x / cam_z

        def predict_side_vy(f, cy_world, Y_world, d, theta):
            sin_t, cos_t = np.sin(theta), np.cos(theta)
            cam_y = -(Y_world - cy_world)
            cam_z = cos_t * d + sin_t * height_cm
            if cam_z <= 0:
                return 1e6
            return cy_img + f * (-sin_t * 0 + cos_t * height_cm - sin_t * 0) / cam_z

        best_result, best_loss = None, np.inf
        grid_cy_world = float(np.mean([p[1] for p in world_pts]))
        for flip in [1.0, -1.0]:
            for theta0 in np.radians([5, 10, 15, 20]):
                for d0 in [100, 300, 800]:
                    for f0 in [300, 600, 1200]:
                        def loss_side(params, fl=flip):
                            theta, d, f = params
                            if d < 10 or f < 50 or theta < 1e-4 or theta > 1.5:
                                return 1e10
                            return sum(
                                (predict_side_vx(theta, d, f, X, fl) - x_obs) ** 2
                                for X, x_obs in zip(w_Xs, obs_col_x)
                            )

                        r = minimize(loss_side, [theta0, d0, f0],
                                     bounds=[(1e-3, 1.4), (10, 3000), (50, 3000)],
                                     method="L-BFGS-B", options={"maxiter": 300})
                        if r.fun < best_loss:
                            best_loss = r.fun
                            best_result = (*r.x, flip)

        if best_result is None or best_loss > 1e6:
            return None

        theta, d, f, flip = best_result
        pan = 0.0 if flip > 0 else 180.0
        logger.info(
            "Auto-fit camera extrinsics (side): tilt=%.1f° dist=%.0fcm "
            "focal=%.0fpx pan=%.0f°  RMS=%.1fpx",
            np.degrees(theta), d, f, pan,
            float(np.sqrt(best_loss / n_fit)),
        )
        return h_from_camera_extrinsics(
            height_cm=height_cm,
            tilt_deg=float(np.degrees(theta)),
            image_width=image_width,
            image_height=image_height,
            focal_length_px=float(f),
            camera_x_world_cm=float(-d if flip > 0 else (max(world_Xs) + d)),
            camera_y_world_cm=float(grid_cy_world),
            pan_deg=pan,
        )

    else:
        logger.warning("Unknown camera_orientation %r — expected 'behind' or 'side'.", orientation)
        return None


def _cluster_rows(
    pixel_pts: np.ndarray,
    thresh_px: float = 8.0,
    min_row_size: int = 3,
) -> list[np.ndarray]:
    """Cluster detected pixel centres into approximate horizontal rows.

    Returns a list of index arrays (into ``pixel_pts``), sorted bottom-to-top
    (largest-y first = nearest-to-camera first for a forward-facing camera).
    Only rows with at least ``min_row_size`` detections are returned.
    """
    if len(pixel_pts) < 2:
        return []
    order = np.argsort(pixel_pts[:, 1])[::-1]  # largest y first
    rows: list[list[int]] = []
    cur: list[int] = [int(order[0])]
    for k in order[1:]:
        if abs(pixel_pts[k, 1] - pixel_pts[cur[-1], 1]) < thresh_px:
            cur.append(int(k))
        else:
            if len(cur) >= min_row_size:
                rows.append(np.array(cur))
            cur = [int(k)]
    if len(cur) >= min_row_size:
        rows.append(np.array(cur))
    return rows


def _row_structured_h_candidates(
    pixel_pts: np.ndarray,
    world_pts: np.ndarray,
    R: int,
    C: int,
) -> list[np.ndarray]:
    """Generate H initialisation candidates from pixel-row ↔ world-row matching.

    For oblique cameras the x/y pixel scales can differ by 10× or more, making
    the isotropic min-NN scale estimate badly wrong.  Clustering detections
    into horizontal rows and matching them to world rows produces a proper
    anisotropic affine/perspective initialisation that works regardless of
    camera angle.

    Strategy:
    -   Cluster detections into horizontal pixel rows (thresh=8 px, min 3 per row).
    -   Keep only rows with ≤ C cones ("clean rows"); rows with > C cones are
        merged clusters from perspective compression and have ambiguous column
        assignment.
    -   Prefer clean rows that are full (exactly C cones) for the initial H;
        fall back to partial rows (< C cones) if needed.
    -   Tries 4 orientation variants (row_flip × col_flip).

    Returns DLT H matrices for all variants with ≥ 4 correspondences.
    """
    all_px_rows = _cluster_rows(pixel_pts, thresh_px=8.0, min_row_size=3)
    # Exclude merged clusters: keep only rows with ≤ C cones
    clean_rows = [r for r in all_px_rows if len(r) <= C]
    if len(clean_rows) < 2:
        return []

    # Prefer full rows (exactly C cones) over partial rows for robustness.
    # Sort: full rows first, then partial, within each category keep bottom-to-top order.
    full_rows = [r for r in clean_rows if len(r) == C]
    partial_rows = [r for r in clean_rows if len(r) < C]
    # Build two row sets to try:
    # 1. full rows only (if ≥2 available)
    # 2. all clean rows (full + partial)
    row_sets: list[list[np.ndarray]] = [clean_rows]  # always include
    if len(full_rows) >= 2:
        row_sets.insert(0, full_rows)

    world_grid = world_pts.reshape(R, C, 2)  # (R, C, 2) canonical order
    candidates: list[np.ndarray] = []

    for px_row_set in row_sets:
        for row_flip in (False, True):
            ordered_px_rows = list(reversed(px_row_set)) if row_flip else px_row_set
            for col_flip in (False, True):
                src_pts: list[list[float]] = []
                dst_pts: list[list[float]] = []
                n_rows = min(len(ordered_px_rows), R)
                for ri in range(n_rows):
                    px_row_idx = ordered_px_rows[ri]  # indices into pixel_pts
                    sorted_idx = px_row_idx[np.argsort(pixel_pts[px_row_idx, 0])]
                    if col_flip:
                        sorted_idx = sorted_idx[::-1]
                    w_row = world_grid[ri]  # (C, 2) world columns
                    n_use = min(len(sorted_idx), C)
                    for ci in range(n_use):
                        src_pts.append(pixel_pts[sorted_idx[ci]].tolist())
                        dst_pts.append(w_row[ci].tolist())

                if len(src_pts) < 4:
                    continue
                H_init, _ = cv2.findHomography(
                    np.array(src_pts, dtype=np.float32),
                    np.array(dst_pts, dtype=np.float32),
                    0,  # DLT
                )
                if H_init is not None:
                    candidates.append(H_init)

    return candidates


def _partial_grid_correspondence(
    pixel_pts: np.ndarray,
    scores: np.ndarray,
    world_pts: np.ndarray,
    R: int,
    C: int,
    match_radius_px: float = 60.0,
    max_iters: int = 25,
    camera_extrinsics_H: np.ndarray | None = None,
    extrinsics_max_iters: int = 1,
) -> dict | None:
    """D4-aware correspondence for partial grids (N_det ≠ N_world).

    Uses two complementary initialisation strategies and runs iterative
    nearest-neighbour (NN) refinement from each:

    1.  **Row-structured init** — clusters detected pixels into horizontal
        rows, matches them to world rows, and computes H via DLT.  This
        correctly captures anisotropic perspective (x-scale ≠ y-scale) which
        occurs for any non-overhead camera angle.  Tries 4 variants
        (row_flip × col_flip).
    2.  **Isotropic scale init** — centroid + min-NN scale init for each of
        the 8 D4 orientations of the world grid.  Acts as a robust fallback
        when there are too few clean rows (e.g. ≤ 1 detected row).

    For each initialisation candidate:
    a.  Project world → pixel via H⁻¹.
    b.  Greedily assign each detected pixel to its nearest projected world
        point.  Confidence-score priority (not pixel position) breaks ties.
    c.  Refit H via DLT from all matched pairs.  Repeat until stable.

    Score candidates by (most matches, then lowest reprojection error).

    Parameters
    ----------
    pixel_pts      : (N_det, 2) detected cone centroids, arbitrary order.
    scores         : (N_det,)   confidence scores aligned with pixel_pts.
    world_pts      : (N_world, 2) expected world positions, canonical order.
    R, C           : grid dimensions (rows × cols); R*C must equal N_world.
    match_radius_px: maximum pixel distance for a detection-to-world assignment.
    max_iters      : refinement iterations per initialisation candidate.

    Returns
    -------
    dict with keys ``H``, ``error_cm``, ``cond``, ``n_matched``,
    ``cone_positions_px``, ``cone_positions_world`` — or ``None`` if every
    candidate yields fewer than 4 inliers.
    """
    N_det = len(pixel_pts)
    N_world = len(world_pts)

    # Process detections in confidence-descending order so high-scoring cones
    # win when two pixels are equidistant from the same projected world point.
    score_order = np.argsort(scores)[::-1].tolist()

    # ── Initialisation strategy 0: camera extrinsics H (highest priority) ─
    # h_from_camera_extrinsics returns world→pixel (the natural camera
    # projection), but _partial_grid_correspondence stores H as pixel→world
    # (matching cv2.findHomography(src_px, dst_world) convention).
    # Invert once here so the iterative loop works correctly.
    #
    # The extrinsics H already projects all rows within the match radius on
    # the FIRST NN pass (verified empirically).  Subsequent DLT refits can
    # drift the far-row projections outside the radius, causing a near-row-only
    # local minimum.  We therefore use only `extrinsics_max_iters` (default=1)
    # iterations for this candidate, locking in the wide-coverage first match.
    h_inits: list[np.ndarray] = []
    h_inits_max_iters: list[int] = []   # per-candidate iteration limits
    if camera_extrinsics_H is not None:
        try:
            H_ext_px2world = np.linalg.inv(camera_extrinsics_H.astype(np.float64))
            h_inits.append(H_ext_px2world)
            h_inits_max_iters.append(extrinsics_max_iters)
            logger.debug("Partial grid: prepending camera-extrinsics H (inverted to px→world) as first candidate.")
        except np.linalg.LinAlgError:
            logger.warning("camera_extrinsics_H is singular — skipping.")

    # ── Initialisation strategy 1: row-structured H candidates ────────────
    # For oblique cameras (x/y scale can differ by 10×+), isotropic min-NN
    # scale is badly wrong.  Row clustering gives a proper anisotropic init.
    row_cands = _row_structured_h_candidates(pixel_pts, world_pts, R, C)
    h_inits.extend(row_cands)
    h_inits_max_iters.extend([max_iters] * len(row_cands))
    logger.debug(
        "Partial grid: %d row-structured H candidates from %d detected pixel rows.",
        len(h_inits), len(_cluster_rows(pixel_pts)),
    )

    # ── Initialisation strategy 2: isotropic min-NN scale + D4 variants ───
    # Fallback / complement for when row clustering yields few rows.
    def _min_nn_dist(pts: np.ndarray) -> float:
        best_d = np.inf
        for i in range(len(pts)):
            dists = np.linalg.norm(pts - pts[i], axis=1)
            dists[i] = np.inf
            best_d = min(best_d, float(dists.min()))
        return best_d

    min_px_dist = _min_nn_dist(pixel_pts)
    min_w_dist = _min_nn_dist(world_pts[:min(30, N_world)])
    if min_px_dist > 1.0 and min_w_dist < np.inf:
        scale_nn = min_w_dist / min_px_dist
    else:
        scale_nn = (float(np.std(world_pts)) + 1e-6) / (float(np.std(pixel_pts)) + 1e-6)

    # Generate all distinct D4 orientations of the world grid indices.
    grid = np.arange(N_world).reshape(R, C)
    d4_variants: list[list[int]] = []
    seen: set[tuple] = set()
    g = grid.copy()
    for _ in range(4):
        for variant in (g, np.fliplr(g)):
            flat = tuple(variant.flatten().tolist())
            if flat not in seen:
                d4_variants.append(list(flat))
                seen.add(flat)
        g = np.rot90(g)

    for d4_perm in d4_variants:
        world_ordered = world_pts[np.array(d4_perm)]
        px_center = pixel_pts.mean(axis=0)
        w_center = world_ordered.mean(axis=0)
        H_iso: np.ndarray = np.array(
            [
                [scale_nn, 0.0, w_center[0] - scale_nn * px_center[0]],
                [0.0, scale_nn, w_center[1] - scale_nn * px_center[1]],
                [0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )
        h_inits.append(H_iso)
        h_inits_max_iters.append(max_iters)

    best: dict | None = None

    # ── Iterative NN refinement from every candidate ───────────────────────
    # We iterate through all H initialisations (structured + isotropic D4).
    # Each initialisation uses the canonical world ordering (world_pts) so
    # the perspective transform projects to the same pixel space for all.
    for H_init, cand_max_iters in zip(h_inits, h_inits_max_iters):
        H: np.ndarray = H_init.copy()
        world_ordered = world_pts  # always use canonical order with structured inits

        matched_px: np.ndarray | None = None
        matched_world: np.ndarray | None = None
        prev_n = -1

        for _ in range(cand_max_iters):
            H_inv = _safe_invert_H(H)
            if H_inv is None:
                break

            # Project every world point into pixel space.
            proj = cv2.perspectiveTransform(
                world_ordered.reshape(-1, 1, 2).astype(np.float32), H_inv
            ).reshape(-1, 2)

            # Greedy nearest-neighbour assignment (confidence priority, not position).
            used_world: set[int] = set()
            pairs: list[tuple[int, int]] = []
            for i in score_order:
                if len(used_world) == N_world:
                    break
                dists = np.linalg.norm(proj - pixel_pts[i], axis=1)
                # Mask already-claimed world points.
                avail = [j for j in range(N_world) if j not in used_world]
                best_j = avail[int(np.argmin(dists[avail]))]
                if dists[best_j] <= match_radius_px:
                    pairs.append((i, best_j))
                    used_world.add(best_j)

            if len(pairs) < 4:
                break

            src = pixel_pts[[p[0] for p in pairs]].astype(np.float32)
            dst = world_ordered[[p[1] for p in pairs]].astype(np.float32)

            # Refit via DLT — all matched pairs are inliers within this candidate.
            H_new, _ = cv2.findHomography(src, dst, 0)
            if H_new is None:
                break
            H = H_new
            matched_px = src
            matched_world = dst

            if len(pairs) == prev_n:
                break
            prev_n = len(pairs)

            logger.debug(
                "Partial grid iter: matched=%d/%d",
                len(pairs), N_det,
            )

        if matched_px is None or len(matched_px) < 4:
            continue

        proj_world = cv2.perspectiveTransform(
            matched_px.reshape(-1, 1, 2), H
        ).reshape(-1, 2)
        error_cm = float(np.mean(np.linalg.norm(proj_world - matched_world, axis=1)))
        cond = float(np.linalg.cond(H))
        n_matched = int(len(matched_px))

        # Quality score: prefer more matches AND lower error.  Pure n_matched
        # ranking can select extra wrong correspondences at 4× the error; the
        # score n / (err + 1) penalises high error while still rewarding coverage.
        quality = n_matched / (error_cm + 1.0)

        # Perspective direction check: for a ground-level camera the nearest
        # world row (lowest world Y) should project to the LARGEST pixel-y
        # (bottom of the frame), so world_Y and pixel_y should be negatively
        # correlated.  A positive correlation means the row assignment is
        # physically reversed (rows are back-to-front); apply a heavy penalty
        # so the correct-direction candidate always wins.
        w_y_vals = matched_world[:, 1]
        p_y_vals = matched_px[:, 1]
        if np.std(w_y_vals) > 1e-3 and np.std(p_y_vals) > 1e-3:
            corr = float(np.corrcoef(w_y_vals, p_y_vals)[0, 1])
            if corr > 0.3:  # clearly reversed perspective
                quality *= 0.2  # heavy penalty; won't beat a correct-direction H
                logger.debug(
                    "Candidate has reversed perspective direction (corr=%.2f) — penalised.",
                    corr,
                )

        is_better = best is None or quality > best.get("quality", -1)
        if is_better:
            best = {
                "H": H,
                "error_cm": error_cm,
                "cond": cond,
                "n_matched": n_matched,
                "quality": quality,
                "cone_positions_px": [tuple(float(v) for v in p) for p in matched_px],
                "cone_positions_world": [tuple(float(v) for v in p) for p in matched_world],
            }

    return best


def solve_correspondence(
    pixel_pts: np.ndarray,
    world_pts: np.ndarray,
    layout: str = "irregular",
    reproj_threshold_cm: float = REPROJ_ERROR_THRESHOLD_CM,
) -> dict:
    """Find the best bijection between detected pixel centroids and world points.

    Replaces sort-based correspondence.  Tries every geometrically valid
    assignment for the given layout, solves H for each, and returns the one
    with the lowest mean reprojection error in world (cm) units.

    Parameters
    ----------
    pixel_pts:
        (N, 2) detected cone centroids in pixel coordinates (arbitrary order).
    world_pts:
        (N, 2) expected cone positions in world cm.
    layout:
        ``'linear'``, ``'grid_RxC'`` (e.g. ``'grid_6x7'``), or
        ``'irregular'``.
    reproj_threshold_cm:
        Reject the best candidate if its reprojection error exceeds this.

    Returns
    -------
    dict with keys ``H`` (3×3 ndarray), ``assignment`` (list[int]),
    ``error_cm`` (float), ``cond`` (float).

    Raises
    ------
    CalibrationError
        If no valid homography is found, or the best error exceeds the
        threshold.
    """
    N = len(pixel_pts)
    if N < 4:
        raise CalibrationError(
            f"solve_correspondence needs ≥ 4 points; got {N}."
        )

    candidates = _enumerate_valid_assignments(world_pts, layout)
    best: dict | None = None

    for assignment in candidates:
        src = pixel_pts.astype(np.float32)
        dst = world_pts[np.array(assignment)].astype(np.float32)

        # Use DLT (method=0) — not RANSAC — because we're scoring full-set
        # candidates against each other.  Within a single candidate there are no
        # outliers to reject; RANSAC's random sampling is unreliable for small N
        # when many 4-point subsets are co-linear (e.g. a 2×3 grid).
        H, _ = cv2.findHomography(src, dst, 0)
        if H is None:
            continue

        projected = cv2.perspectiveTransform(
            src.reshape(-1, 1, 2), H
        ).reshape(-1, 2)
        error_cm = float(np.mean(np.linalg.norm(projected - dst, axis=1)))
        cond = float(np.linalg.cond(H))

        if best is None or error_cm < best["error_cm"]:
            best = {
                "H": H,
                "assignment": list(assignment),
                "error_cm": error_cm,
                "cond": cond,
            }

    if best is None:
        raise CalibrationError(
            "No valid homography found for any correspondence candidate "
            f"(layout='{layout}', N={N})."
        )

    if best["error_cm"] > reproj_threshold_cm:
        raise CalibrationError(
            f"Best reprojection error {best['error_cm']:.2f} cm exceeds "
            f"threshold {reproj_threshold_cm:.2f} cm (layout='{layout}', N={N})."
        )

    if best["cond"] > CONDITION_NUMBER_WARN:
        logger.warning(
            "Homography condition number %.1f > %.1f — geometry may be "
            "near-degenerate (cones nearly collinear or camera angle < 20°).",
            best["cond"], CONDITION_NUMBER_WARN,
        )

    return best


# ---------------------------------------------------------------------------
# Safe H inversion (Fix 4)
# ---------------------------------------------------------------------------

def _safe_invert_H(H: np.ndarray) -> np.ndarray | None:
    """Invert *H* using SVD decomposition with a condition-number pre-check.

    Returns ``None`` when the matrix is too ill-conditioned to invert reliably,
    instead of silently returning numerical garbage as ``np.linalg.inv`` would.
    """
    cond = float(np.linalg.cond(H))
    if cond > CONDITION_NUMBER_REJECT:
        logger.warning(
            "Cannot safely invert H: condition number %.1f exceeds %.1f. "
            "Geometry is near-degenerate — check camera angle and cone spacing.",
            cond, CONDITION_NUMBER_REJECT,
        )
        return None
    if cond > CONDITION_NUMBER_WARN:
        logger.warning(
            "H condition number %.1f > %.1f — inversion may lose precision.",
            cond, CONDITION_NUMBER_WARN,
        )
    retval, H_inv = cv2.invert(H, flags=cv2.DECOMP_SVD)
    if retval == 0:
        logger.warning("cv2.invert returned 0 (singular matrix).")
        return None
    return H_inv


# Default HSV ranges — re-tune per lighting condition
HSV_RANGES = {
    "yellow": ((18, 80, 80), (35, 255, 255)),
    "orange": ((5, 100, 100), (18, 255, 255)),
    "blue":   ((100, 80, 50), (130, 255, 255)),
    "red_lo": ((0, 100, 100), (5, 255, 255)),
    "red_hi": ((170, 100, 100), (180, 255, 255)),
}

# Minimum contour area to treat as a cone (filters noise)
MIN_CONE_AREA = 100


@dataclass
class ConeDetection:
    """Internal cone representation with colour label metadata."""
    cx: float
    cy: float
    colour_label: str
    score: float
    bbox: tuple[float, float, float, float] | None = None


class Calibrator:
    """
    Detects cones via HSV segmentation and computes pixel↔world mapping.

    Evaluation criteria:
        - All cones detected in ≥ 95% of frames from March 2026 footage
        - Homography reprojection error < 3 px
        - Known 5m cone separation reproduced within ±5 cm
        - Robust across all 6 clips from March 2026 footage
    """

    def __init__(
        self,
        hsv_ranges: dict | None = None,
        min_cone_area: int = MIN_CONE_AREA,
        detector_backend: Literal["hsv", "sam3_prompt"] = "hsv",
        sam_model_path: str = "sam3.pt",
        sam_prompt: str = "training cone",
        min_confidence: float = 0.5,
    ):
        self.hsv_ranges = hsv_ranges or HSV_RANGES
        self.min_cone_area = min_cone_area
        self.detector_backend = detector_backend
        self.sam_model_path = sam_model_path
        self.sam_prompt = sam_prompt
        self.min_confidence = min_confidence
        self._sam_predictor = None
        self._sam_force_cpu = False  # Set when CUDA fails at runtime
        self.last_detected_cones: list[ConeDetection] = []

    # ------------------------------------------------------------------
    # Cone detection
    # ------------------------------------------------------------------

    def detect_cones(
        self,
        frame: np.ndarray,
        colour: str = "yellow",
    ) -> list[tuple[float, float]]:
        """
        Detect cone centres via HSV mask + contour centroids.

        Args:
            frame:  BGR frame.
            colour: One of 'yellow', 'orange', 'blue', 'red_lo', 'red_hi'.

        Returns:
            List of (cx, cy) pixel centres for detected cones (score >= min_confidence).
        """
        cone_objects = self._detect_cone_objects(frame, colour=colour)
        cone_objects = [c for c in cone_objects if c.score >= self.min_confidence]
        self.last_detected_cones = cone_objects
        centres = [(c.cx, c.cy) for c in cone_objects]
        logger.debug("Detected %d cone(s) via %s backend (min_confidence=%.2f).", len(centres), self.detector_backend, self.min_confidence)
        return centres

    def _detect_cone_objects(self, frame: np.ndarray, colour: str = "yellow") -> list[ConeDetection]:
        if self.detector_backend == "sam3_prompt":
            return self._detect_cones_sam3_prompt(frame)
        return self._detect_cones_hsv(frame, colour)

    def _detect_cones_hsv(self, frame: np.ndarray, colour: str = "yellow") -> list[ConeDetection]:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        if colour not in self.hsv_ranges:
            raise ValueError(f"Unknown cone colour '{colour}'. Add to HSV_RANGES.")

        lo, hi = self.hsv_ranges[colour]
        mask = cv2.inRange(hsv, np.array(lo), np.array(hi))

        # Morphological cleanup
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_DILATE, kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        detections: list[ConeDetection] = []
        for c in contours:
            area = float(cv2.contourArea(c))
            if area < self.min_cone_area:
                continue
            M = cv2.moments(c)
            if M["m00"] <= 0:
                continue
            cx = float(M["m10"] / M["m00"])
            cy = float(M["m01"] / M["m00"])
            x, y, w, h = cv2.boundingRect(c)
            detections.append(
                ConeDetection(
                    cx=cx,
                    cy=cy,
                    colour_label=colour,
                    score=min(1.0, area / 4000.0),
                    bbox=(float(x), float(y), float(x + w), float(y + h)),
                )
            )
        return detections

    def _cuda_compatible_for_sam(self) -> bool:
        """Check if CUDA is usable for SAM (PyTorch 2.4 supports up to sm_90; RTX 5080/5090 use sm_120)."""
        try:
            import torch
            if not torch.cuda.is_available():
                return False
            cap = torch.cuda.get_device_capability()
            # sm_90 = (9, 0). Newer GPUs (RTX 5080/5090) use sm_120 = (12, 0).
            if cap[0] > 9:
                logger.info(
                    "CUDA device sm_%d%d not supported by PyTorch build (supports up to sm_90). "
                    "Using CPU for SAM cone detection.",
                    cap[0], cap[1],
                )
                return False
            return True
        except Exception:
            return False

    def _build_sam3_predictor(self):
        if self._sam_predictor is not None:
            return self._sam_predictor
        from ultralytics.models.sam.predict import SAM3SemanticPredictor
        from ultralytics.utils.downloads import attempt_download_asset

        model_path = self.sam_model_path
        if "/" not in model_path and "\\" not in model_path and not Path(model_path).exists():
            try:
                resolved = attempt_download_asset(model_path)
                if resolved and Path(resolved).exists():
                    model_path = str(resolved)
            except Exception:
                pass
        if "sam3" in Path(model_path).stem.lower() and not Path(model_path).exists():
            try:
                from huggingface_hub import hf_hub_download

                model_path = hf_hub_download(repo_id="1038lab/sam3", filename="sam3.pt")
            except Exception:
                pass

        overrides: dict = {"model": model_path, "imgsz": 1036}
        if self._sam_force_cpu or not self._cuda_compatible_for_sam():
            overrides["device"] = "cpu"
        self._sam_predictor = SAM3SemanticPredictor(overrides=overrides)
        return self._sam_predictor

    def _detect_cones_sam3_prompt(self, frame: np.ndarray) -> list[ConeDetection]:
        predictor = self._build_sam3_predictor()
        predictor.set_prompts({"text": [self.sam_prompt]})
        try:
            results = predictor(source=frame, verbose=False)
        except RuntimeError as e:
            if "no kernel image" in str(e) or "not compatible" in str(e).lower():
                logger.warning(
                    "CUDA error during SAM inference, falling back to CPU: %s", e
                )
                self._sam_force_cpu = True
                self._sam_predictor = None
                predictor = self._build_sam3_predictor()
                predictor.set_prompts({"text": [self.sam_prompt]})
                results = predictor(source=frame, verbose=False)
            else:
                raise
        if not results:
            return []
        r0 = results[0]
        if getattr(r0, "masks", None) is None or r0.masks is None:
            return []

        masks = r0.masks.data
        if hasattr(masks, "cpu"):
            masks = masks.cpu().numpy()
        boxes = getattr(r0, "boxes", None)
        confs = None
        if boxes is not None and getattr(boxes, "conf", None) is not None:
            confs = boxes.conf
            if hasattr(confs, "cpu"):
                confs = confs.cpu().numpy()

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        detections: list[ConeDetection] = []
        for i, mask in enumerate(masks):
            mask_bin = mask > 0.5
            ys, xs = np.where(mask_bin)
            if xs.size == 0:
                continue
            m = cv2.moments(mask_bin.astype(np.uint8))
            if m["m00"] <= 0:
                continue
            cx = float(m["m10"] / m["m00"])
            cy = float(m["m01"] / m["m00"])
            pix = hsv[ys, xs]
            h_mean = float(np.mean(pix[:, 0]))
            s_mean = float(np.mean(pix[:, 1]))
            v_mean = float(np.mean(pix[:, 2]))
            colour_label = self._label_colour_from_hsv(h_mean, s_mean, v_mean)
            score = float(confs[i]) if confs is not None and i < len(confs) else 0.5
            x1, x2 = float(xs.min()), float(xs.max())
            y1, y2 = float(ys.min()), float(ys.max())
            detections.append(
                ConeDetection(
                    cx=cx,
                    cy=cy,
                    colour_label=colour_label,
                    score=score,
                    bbox=(x1, y1, x2, y2),
                )
            )
        return detections

    def _filter_and_select_cones_for_layout(
        self,
        cone_objects: list[ConeDetection],
        layout_config: dict,
        num_cones: int,
    ) -> list[ConeDetection]:
        """
        Filter by confidence and select the target number of cones assuming a
        distorted grid/linear layout. Drops uncertain detections, then picks
        the N that best fit the expected layout.
        """
        # 1. Drop low-confidence detections (SAM3 outputs score in [0,1])
        filtered = [c for c in cone_objects if c.score >= self.min_confidence]
        # Minimum count needed for the partial-grid solver (8 DOF homography needs ≥4).
        # We only fall back to all detections when fewer than this many high-confidence
        # cones are found — preserving the filter when it removes genuine false positives.
        min_for_partial = int(layout_config.get("grid_fit_min_inliers", 4))
        if len(filtered) < min_for_partial:
            # Too few high-confidence detections to calibrate — fall back to all
            # detections so we don't lose real (low-score) cones entirely.
            logger.warning(
                "After confidence filter (min=%.2f): %d cones remain, need ≥%d for "
                "partial matching. Falling back to all %d detections.",
                self.min_confidence, len(filtered), min_for_partial, len(cone_objects),
            )
            filtered = cone_objects
        elif len(filtered) < num_cones:
            # Enough for partial matching but fewer than the full grid count.
            # Keep the high-confidence subset — false positives are filtered out and
            # the partial-grid solver handles missing cones gracefully.
            logger.info(
                "Confidence filter (min=%.2f): %d/%d cones kept "
                "(partial grid solver will handle missing cones).",
                self.min_confidence, len(filtered), num_cones,
            )
        if len(filtered) <= num_cones:
            return filtered[:num_cones]

        pts = np.array([(c.cx, c.cy) for c in filtered], dtype=np.float64)
        pattern = layout_config.get("pattern", "linear")
        direction = layout_config.get("direction", "x")

        if pattern == "linear":
            # Fit line through points (PCA), project, sort by position along line.
            # For linear layouts this correctly selects the N most co-linear cones;
            # the order is only used for selection, not for correspondence.
            center = pts.mean(axis=0)
            centered = pts - center
            cov = centered.T @ centered
            eigvals, eigvecs = np.linalg.eigh(cov)
            line_dir = eigvecs[:, np.argmax(eigvals)]
            line_dir = line_dir / (np.linalg.norm(line_dir) + 1e-9)
            proj = centered @ line_dir
            order = np.argsort(proj)
            if direction == "y" and line_dir[1] < 0:
                order = order[::-1]
            indices = order[:num_cones]
        else:
            # Grid: select top-N by detection confidence score.
            # Pixel position ordering must not be used here — solve_correspondence
            # and _partial_grid_correspondence both try all D4 orientations and
            # do not assume any positional ordering of the input pixel list.
            indices = np.argsort([c.score for c in filtered])[::-1][:num_cones]

        return [filtered[i] for i in indices]

    def _fit_grid_iterative(
        self,
        cone_objects: list[ConeDetection],
        world_coords_cm: list[tuple[float, float]],
        layout_config: dict,
    ) -> tuple[np.ndarray | None, list[tuple[float, float]], list[tuple[float, float]], float]:
        """
        Iteratively assign detected cones to grid positions and fit homography.
        Returns (H, cone_px, world_cm, reprojection_error) or (None, [], [], inf) on failure.
        """
        max_iters = int(layout_config.get("grid_fit_max_iters", 20))
        match_radius_px = float(layout_config.get("grid_fit_match_radius_px", 50.0))
        min_inliers = int(layout_config.get("grid_fit_min_inliers", 4))
        use_confidence = bool(layout_config.get("grid_fit_use_confidence_weights", False))

        logger.debug(
            "Grid iterative fit: n_det=%d, n_world=%d, max_iters=%d, match_radius_px=%.0f, min_inliers=%d",
            len(cone_objects), len(world_coords_cm), max_iters, match_radius_px, min_inliers,
        )

        pts_px = np.array([(c.cx, c.cy) for c in cone_objects], dtype=np.float32)
        scores = np.array([c.score for c in cone_objects], dtype=np.float64)
        world_pts = np.array(world_coords_cm, dtype=np.float32)
        n_det = len(pts_px)
        n_world = len(world_pts)
        if n_det < min_inliers or n_world < min_inliers:
            logger.debug(
                "Grid fit: too few points (det=%d, world=%d, min_inliers=%d).",
                n_det, n_world, min_inliers,
            )
            return (None, [], [], float("inf"))

        # Generate all 8 D4 orientations from layout config (if available).
        R = int(layout_config.get("rows", 2))
        C = int(layout_config.get("cols", 2))
        grid = np.arange(n_world).reshape(R, C) if R * C == n_world else np.arange(n_world).reshape(1, n_world)
        d4_variants: list[np.ndarray] = []
        seen_d4: set[tuple] = set()
        g = grid.copy()
        for _ in range(4):
            for variant in (g, np.fliplr(g)):
                flat = tuple(variant.flatten().tolist())
                if flat not in seen_d4:
                    d4_variants.append(np.array(list(flat)))
                    seen_d4.add(flat)
            g = np.rot90(g)

        best_H = None
        best_src: list[tuple[float, float]] = []
        best_dst: list[tuple[float, float]] = []
        best_err = float("inf")
        best_n = 0

        for world_try in d4_variants:
            H, inlier_src, inlier_dst, err, n_in = self._iterate_grid_fit(
                pts_px,
                scores,
                world_pts[world_try],
                max_iters,
                match_radius_px,
                use_confidence,
            )
            if H is not None and n_in >= min_inliers and (n_in > best_n or (n_in == best_n and err < best_err)):
                best_H = H
                best_src = inlier_src
                best_dst = inlier_dst
                best_err = err
                best_n = n_in

        if best_H is None or best_n < min_inliers:
            logger.warning(
                "Grid iterative fit failed: best inliers=%d (min=%d), reproj_err=%.2f px.",
                best_n, min_inliers, best_err,
            )
            return (None, [], [], float("inf"))
        logger.info(
            "Grid iterative fit: %d inliers, reprojection error %.2f px.",
            best_n, best_err,
        )
        return (best_H, best_src, best_dst, best_err)

    def _iterate_grid_fit(
        self,
        pts_px: np.ndarray,
        scores: np.ndarray,
        world_pts: np.ndarray,
        max_iters: int,
        match_radius_px: float,
        use_confidence_weights: bool,
    ) -> tuple[np.ndarray | None, list[tuple[float, float]], list[tuple[float, float]], float, int]:
        """One pass: centroid+scale initial H, then assign → refit until stable."""
        n_det, n_world = len(pts_px), len(world_pts)

        # Initialise H from centroid + isotropic scale — no pixel position ordering.
        px_center = pts_px.mean(axis=0)
        w_center = world_pts.mean(axis=0)
        px_spread = float(np.std(pts_px)) + 1e-6
        w_spread = float(np.std(world_pts)) + 1e-6
        scale = w_spread / px_spread
        H: np.ndarray = np.array(
            [
                [scale, 0.0, float(w_center[0]) - scale * float(px_center[0])],
                [0.0, scale, float(w_center[1]) - scale * float(px_center[1])],
                [0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )

        prev_matches = -1
        src_pts: list = []
        dst_pts: list = []
        for it in range(max_iters):
            # H maps pixel -> world; project world -> image with inv(H)
            if len(dst_pts) < 4:
                break
            H, _ = cv2.findHomography(
                np.array(src_pts, dtype=np.float32),
                np.array(dst_pts, dtype=np.float32),
                cv2.RANSAC,
                5.0,
            )
            if H is None:
                break
            H_inv = _safe_invert_H(H)
            if H_inv is None:
                break
            proj = cv2.perspectiveTransform(
                world_pts.reshape(-1, 1, 2).astype(np.float32), H_inv
            ).reshape(-1, 2)
            # Assign each detection to nearest projected grid point within radius (one-to-one)
            matches: list[tuple[int, int]] = []
            used_world = set()
            for i in range(n_det):
                dists = np.linalg.norm(proj - pts_px[i], axis=1)
                j = np.argmin(dists)
                if dists[j] <= match_radius_px and j not in used_world:
                    matches.append((i, j))
                    used_world.add(j)
            if len(matches) < 4:
                break
            src_pts = [tuple(pts_px[i].tolist()) for i, _ in matches]
            dst_pts = [tuple(world_pts[j].tolist()) for _, j in matches]
            if len(matches) == prev_matches:
                break
            prev_matches = len(matches)
            logger.debug(
                "Grid fit iter %d: %d matches, refitting H.",
                it + 1, len(matches),
            )
        if len(src_pts) < 4:
            return (None, [], [], float("inf"), 0)
        H_final, mask = cv2.findHomography(
            np.array(src_pts, dtype=np.float32),
            np.array(dst_pts, dtype=np.float32),
            cv2.RANSAC,
            5.0,
        )
        if H_final is None:
            return (None, [], [], float("inf"), 0)
        inlier = mask.ravel() > 0
        src_in = [src_pts[i] for i in range(len(src_pts)) if inlier[i]]
        dst_in = [dst_pts[i] for i in range(len(dst_pts)) if inlier[i]]
        if len(src_in) < 4:
            return (None, [], [], float("inf"), 0)
        # Reprojection error in world (cm) space: project pixel centroids through H,
        # compare to world targets.  This is consistent with calibrate_homography.
        proj_world = cv2.perspectiveTransform(
            np.array(src_in, dtype=np.float32).reshape(-1, 1, 2), H_final
        ).reshape(-1, 2)
        err_cm = float(np.linalg.norm(np.array(dst_in, dtype=np.float32) - proj_world, axis=1).mean())
        return (H_final, src_in, dst_in, err_cm, len(src_in))

    @staticmethod
    def _label_colour_from_hsv(h: float, s: float, v: float) -> str:
        # Assign a colour label for metadata/debugging only; no filtering.
        if s < 40 or v < 40:
            return "unknown"
        if 18 <= h <= 35:
            return "yellow"
        if 5 <= h < 18:
            return "orange"
        if 100 <= h <= 130:
            return "blue"
        if 0 <= h < 5 or h >= 170:
            return "red"
        return "unknown"

    # ------------------------------------------------------------------
    # Homography calibration
    # ------------------------------------------------------------------

    def calibrate_homography(
        self,
        frame: np.ndarray,
        known_world_coords_cm: list[tuple[float, float]],
        cone_colour: str = "yellow",
        cone_positions_px: list[tuple[float, float]] | None = None,
        layout_hint: str | None = None,
    ) -> CalibrationResult:
        """Compute 3×3 homography mapping pixel space → world floor plane (cm).

        Uses :func:`solve_correspondence` to find the geometrically correct
        pixel↔world assignment instead of the fragile (y, x) sort heuristic.

        Args:
            frame:                  BGR frame (typically first frame of clip).
            known_world_coords_cm:  List of (x_cm, y_cm) for each cone in real space.
            cone_colour:            Colour key in HSV_RANGES.
            cone_positions_px:      Optional pre-detected cone centres. When provided,
                                   skips detection and uses these.
            layout_hint:            Layout type for correspondence search —
                                   ``'linear'``, ``'grid_RxC'``, or ``'irregular'``
                                   (default).  Passing the correct hint dramatically
                                   reduces the candidate space.

        Returns:
            CalibrationResult (method='homography').
        """
        if cone_positions_px is not None:
            cone_px = list(cone_positions_px)
            cone_objects = [
                ConeDetection(cx=p[0], cy=p[1], colour_label=cone_colour, score=1.0)
                for p in cone_px
            ]
        else:
            cone_objects = self._detect_cone_objects(frame, colour=cone_colour)
            cone_px = [(c.cx, c.cy) for c in cone_objects]

        if len(cone_px) < 4:
            logger.warning(
                "Calibration failed: only %d cones detected (need ≥ 4 for homography). "
                "Try: detector_backend='hsv' with tuned HSV ranges, or check cone visibility in frame.",
                len(cone_px),
            )
            return CalibrationResult(
                method="homography",
                homography_matrix=None,
                pixels_per_cm=None,
                cone_positions_px=cone_px,
                cone_positions_world=known_world_coords_cm,
                reprojection_error_cm=float("inf"),
                is_valid=False,
            )

        expected = len(known_world_coords_cm)
        if len(cone_px) < expected:
            logger.info(
                "Using %d detected cones for calibration (layout has %d); homography needs ≥ 4.",
                len(cone_px), expected,
            )
            known_world_coords_cm = known_world_coords_cm[: len(cone_px)]
        if len(cone_px) > len(known_world_coords_cm):
            logger.warning(
                "Detected %d cones for %d world points; taking top-%d by score.",
                len(cone_px), len(known_world_coords_cm), len(known_world_coords_cm),
            )
            cone_objects = sorted(cone_objects, key=lambda c: c.score, reverse=True)[
                : len(known_world_coords_cm)
            ]
            cone_px = [(c.cx, c.cy) for c in cone_objects]

        pixel_arr = np.array(cone_px, dtype=np.float64)
        world_arr = np.array(known_world_coords_cm, dtype=np.float64)
        layout = layout_hint or "irregular"

        try:
            best = solve_correspondence(pixel_arr, world_arr, layout)
        except CalibrationError as exc:
            logger.warning("Correspondence solver failed: %s", exc)
            return CalibrationResult(
                method="homography",
                homography_matrix=None,
                pixels_per_cm=None,
                cone_positions_px=cone_px,
                cone_positions_world=known_world_coords_cm,
                reprojection_error_cm=float("inf"),
                is_valid=False,
            )

        H = best["H"]
        assignment = best["assignment"]
        error_cm = best["error_cm"]
        cond = best["cond"]
        ordered_world = [
            (float(world_arr[j, 0]), float(world_arr[j, 1])) for j in assignment
        ]

        logger.info(
            "Homography calibrated via %s correspondence (%d cones). "
            "Reprojection error: %.2f cm, condition number: %.1f.",
            layout, len(cone_px), error_cm, cond,
        )
        return CalibrationResult(
            method="homography",
            homography_matrix=H,
            pixels_per_cm=None,
            cone_positions_px=cone_px,
            cone_positions_world=ordered_world,
            reprojection_error_cm=error_cm,
            is_valid=error_cm < REPROJ_ERROR_THRESHOLD_CM,
            condition_number=cond,
        )

    # ------------------------------------------------------------------
    # Layout-based calibration (spacing + first cone)
    # ------------------------------------------------------------------

    def calibrate_from_layout(
        self,
        frame: np.ndarray,
        layout_config: dict,
        cone_colour: str = "yellow",
    ) -> CalibrationResult:
        """
        Calibrate using a layout config (spacing + first cone) instead of
        explicit world coords. Supports linear, grid, and clustered patterns.

        Args:
            frame:         BGR frame (typically first frame).
            layout_config: Dict with pattern, first_cone_cm, spacing_cm, etc.
                          See pipeline/cone_layout.py and notebook templates.
            cone_colour:   Colour key for HSV (ignored if using sam3_prompt).

        Returns:
            CalibrationResult (method='homography').
        """
        cone_objects = self._detect_cone_objects(frame)

        # Spatial ROI filter: drop cones outside the expected frame region.
        # Eliminates detections from other test setups visible on the gym floor.
        roi_cfg = layout_config.get("spatial_roi") or None
        cone_objects = _spatial_roi_filter(cone_objects, frame.shape, roi_cfg)

        # Publish all ROI-filtered detections so callers / notebooks can overlay them
        # alongside only the matched subset stored in CalibrationResult.
        self.last_detected_cones = [c for c in cone_objects if c.score >= self.min_confidence]
        cone_objects = self.last_detected_cones

        # Per-test reprojection threshold (overrides global default if specified).
        reproj_threshold = float(
            layout_config.get("reproj_error_threshold_cm", REPROJ_ERROR_THRESHOLD_CM)
        )

        # Camera extrinsics-based H initialisation.
        # Two routes (priority order):
        #   1. Explicit: `camera_extrinsics` dict with tilt_deg + focal_length_px.
        #   2. Auto-fit: `camera_orientation` ("behind"|"side") + height — all
        #      remaining parameters are solved from this frame's detections.
        extrinsics_H: np.ndarray | None = None
        ext = layout_config.get("camera_extrinsics") or {}
        orientation = layout_config.get("camera_orientation", "").strip().lower()
        cam_height_cm = float(
            ext.get("height_cm")
            or layout_config.get("height_cm")
            or (float(layout_config.get("camera_height_m", 0)) * 100)
            or 250.0
        )

        if ext and all(k in ext for k in ("height_cm", "tilt_deg")):
            # Route 1: fully-specified extrinsics.
            try:
                extrinsics_H = h_from_camera_extrinsics(
                    height_cm=float(ext["height_cm"]),
                    tilt_deg=float(ext["tilt_deg"]),
                    image_width=frame.shape[1],
                    image_height=frame.shape[0],
                    focal_length_px=ext.get("focal_length_px"),
                    fov_horizontal_deg=ext.get("fov_horizontal_deg", 70.0),
                    camera_x_world_cm=float(ext.get("camera_x_world_cm", 0.0)),
                    camera_y_world_cm=float(ext.get("camera_y_world_cm", 0.0)),
                    pan_deg=float(ext.get("pan_deg", 0.0)),
                )
                logger.info(
                    "Explicit camera extrinsics H: height=%.0fcm tilt=%.1f° "
                    "fov=%.0f° cond=%.1e",
                    ext["height_cm"], ext["tilt_deg"],
                    ext.get("fov_horizontal_deg", 70.0),
                    float(np.linalg.cond(extrinsics_H)),
                )
            except Exception as exc:
                logger.warning("Failed to compute explicit extrinsics H: %s", exc)

        cone_px = [(c.cx, c.cy) for c in cone_objects]

        if extrinsics_H is None and orientation in ("behind", "side") and len(cone_px) >= 6:
            # Route 2: auto-fit from orientation + height + this frame's detections.
            pixel_pts_arr = np.array(cone_px, dtype=np.float64)
            # cone_count lives at the top-level config, NOT in cone_layout; fall
            # back to rows × cols so auto_fit receives the full set of world pts.
            _auto_fit_n = (
                layout_config.get("cone_count")
                or (int(layout_config.get("rows", 2)) * int(layout_config.get("cols", 2)))
            )
            world_pts_arr = np.array(
                generate_cone_world_coords(layout_config, _auto_fit_n),
                dtype=np.float64,
            )
            try:
                extrinsics_H = auto_fit_camera_extrinsics(
                    pixel_pts=pixel_pts_arr,
                    world_pts=world_pts_arr,
                    camera_orientation=orientation,
                    height_cm=cam_height_cm,
                    image_width=frame.shape[1],
                    image_height=frame.shape[0],
                )
                if extrinsics_H is not None:
                    logger.info(
                        "Auto-fit camera extrinsics (%s, h=%.0fcm): cond=%.1e",
                        orientation, cam_height_cm, float(np.linalg.cond(extrinsics_H)),
                    )
            except Exception as exc:
                logger.warning("Auto-fit camera extrinsics failed: %s", exc)

        if len(cone_px) < 4:
            logger.warning(
                "Calibration failed: only %d cones detected (need ≥ 4 for homography). "
                "Try: detector_backend='hsv' with tuned HSV ranges, or check cone visibility.",
                len(cone_px),
            )
            return CalibrationResult(
                method="homography",
                homography_matrix=None,
                pixels_per_cm=None,
                cone_positions_px=cone_px,
                cone_positions_world=[],
                reprojection_error_cm=float("inf"),
                is_valid=False,
            )

        pattern = layout_config.get("pattern", "linear")

        if pattern == "clustered":
            cone_objects_filtered = [
                c for c in cone_objects if c.score >= self.min_confidence
            ]
            if len(cone_objects_filtered) < 4:
                cone_objects_filtered = cone_objects
            cone_px = [(c.cx, c.cy) for c in cone_objects_filtered]
            known_world_coords_cm = generate_cone_world_coords_from_pixels(
                layout_config, cone_px
            )
            num_cones = len(cone_px)
            cone_px_sorted = cone_px
            cone_objects_filtered_out = cone_objects_filtered
        elif pattern == "grid":
            R = int(layout_config.get("rows", 2))
            C = int(layout_config.get("cols", 2))
            num_cones = layout_config.get("cone_count") or R * C
            known_world_coords_cm = generate_cone_world_coords(layout_config, num_cones)
            layout_hint = f"grid_{R}x{C}"

            cone_objects_filtered = self._filter_and_select_cones_for_layout(
                cone_objects, layout_config, num_cones
            )
            n_det = len(cone_objects_filtered)

            pixel_pts = np.array([(c.cx, c.cy) for c in cone_objects_filtered], dtype=np.float64)
            world_pts = np.array(known_world_coords_cm, dtype=np.float64)
            scores_arr = np.array([c.score for c in cone_objects_filtered], dtype=np.float64)

            if n_det == num_cones:
                # Primary path: D4 exhaustive search (exact count).
                try:
                    best = solve_correspondence(pixel_pts, world_pts, layout_hint)
                    H, assignment, error_cm, cond = (
                        best["H"], best["assignment"], best["error_cm"], best["cond"]
                    )
                    ordered_world = [
                        (float(world_pts[j, 0]), float(world_pts[j, 1])) for j in assignment
                    ]
                    logger.info(
                        "Layout-based calibration (grid D4 exact): %d cones, "
                        "reproj=%.2f cm, cond=%.1f",
                        n_det, error_cm, cond,
                    )
                    return CalibrationResult(
                        method="homography",
                        homography_matrix=H,
                        pixels_per_cm=None,
                        cone_positions_px=[(c.cx, c.cy) for c in cone_objects_filtered],
                        cone_positions_world=ordered_world,
                        reprojection_error_cm=error_cm,
                        is_valid=error_cm < reproj_threshold,
                        condition_number=cond,
                    )
                except CalibrationError as exc:
                    logger.warning(
                        "D4 exact correspondence failed (%s). Falling back to partial solver.",
                        exc,
                    )

            # Partial path: N_det != N_world (missing/extra cones) or D4 exact failed.
            # _partial_grid_correspondence tries all 8 D4 orientations with a
            # centroid-initialised iterative nearest-neighbour assignment.
            logger.info(
                "Using partial grid correspondence: %d detected, %d expected (%dx%d grid).",
                n_det, num_cones, R, C,
            )
            match_radius_px = float(layout_config.get("grid_fit_match_radius_px", 60.0))

            # When camera extrinsics are available we run two passes and pick the
            # best result by quality score (n_matched / (error_cm + 1)):
            #   Pass A — tight radius only for the extrinsics-seeded candidate
            #            (avoids wrong matches when r is large).
            #   Pass B — standard radius, all row-structured candidates (no
            #            extrinsics H so it cannot win with a large-r bad result).
            # This prevents the extrinsics candidate at a wide radius from
            # dominating with more-but-wronger correspondences.
            def _quality(p: dict | None) -> float:
                return p["n_matched"] / (p["error_cm"] + 1.0) if p else -1.0

            partial = None
            if extrinsics_H is not None:
                tight_r = float(layout_config.get(
                    "grid_fit_extrinsics_match_radius_px",
                    min(match_radius_px, 50.0),
                ))
                partial_ext = _partial_grid_correspondence(
                    pixel_pts, scores_arr, world_pts, R, C,
                    match_radius_px=tight_r,
                    camera_extrinsics_H=extrinsics_H,
                )
                partial_std = _partial_grid_correspondence(
                    pixel_pts, scores_arr, world_pts, R, C,
                    match_radius_px=match_radius_px,
                    camera_extrinsics_H=None,
                )
                logger.info(
                    "Two-pass: tight(r=%.0f) n=%d err=%.1fcm Q=%.3f | "
                    "std(r=%.0f) n=%d err=%.1fcm Q=%.3f",
                    tight_r,
                    partial_ext["n_matched"] if partial_ext else 0,
                    partial_ext["error_cm"] if partial_ext else 999,
                    _quality(partial_ext),
                    match_radius_px,
                    partial_std["n_matched"] if partial_std else 0,
                    partial_std["error_cm"] if partial_std else 999,
                    _quality(partial_std),
                )

                # Direct extrinsics match: use the good extrinsics H to project
                # all world cones to pixel space and run a SINGLE tight-radius NN
                # pass at a radius smaller than the minimum inter-row pixel spacing.
                # This prevents cross-row misassignments that corrupt the DLT.
                # We do NOT route through _partial_grid_correspondence here (it
                # would mix in row-structured candidates that converge to wrong H).
                direct_ext: dict | None = None
                try:
                    direct_r = float(layout_config.get(
                        "grid_fit_direct_extrinsics_radius_px",
                        min(tight_r * 0.6, 30.0),
                    ))
                    H_ext_w2px = extrinsics_H  # world→pixel
                    H_ext_px2w = np.linalg.inv(H_ext_w2px)
                    proj_ext = cv2.perspectiveTransform(
                        world_pts.reshape(-1, 1, 2).astype(np.float32), H_ext_w2px
                    ).reshape(-1, 2)
                    score_ord = np.argsort(scores_arr)[::-1].tolist()
                    used_w_direct: set[int] = set()
                    pairs_direct: list[tuple[int, int]] = []
                    N_w = len(world_pts)
                    for di in score_ord:
                        dists = np.linalg.norm(proj_ext - pixel_pts[di], axis=1)
                        avail = [j for j in range(N_w) if j not in used_w_direct]
                        if not avail:
                            break
                        bj = avail[int(np.argmin(dists[avail]))]
                        if dists[bj] <= direct_r:
                            pairs_direct.append((di, bj))
                            used_w_direct.add(bj)
                    if len(pairs_direct) >= 4:
                        src_d = pixel_pts[[p[0] for p in pairs_direct]].astype(np.float32)
                        dst_d = world_pts[[p[1] for p in pairs_direct]].astype(np.float32)
                        H_d, _ = cv2.findHomography(src_d, dst_d, 0)
                        if H_d is not None:
                            proj_w_d = cv2.perspectiveTransform(
                                src_d.reshape(-1, 1, 2), H_d
                            ).reshape(-1, 2)
                            err_d = float(np.mean(np.linalg.norm(proj_w_d - dst_d, axis=1)))
                            # Perspective direction check (same as in _partial_grid_correspondence)
                            w_y_d = dst_d[:, 1]; p_y_d = src_d[:, 1]
                            corr_d = (
                                float(np.corrcoef(w_y_d, p_y_d)[0, 1])
                                if np.std(w_y_d) > 1e-3 and np.std(p_y_d) > 1e-3
                                else 0.0
                            )
                            q_d = len(pairs_direct) / (err_d + 1.0)
                            if corr_d > 0.3:
                                q_d *= 0.2
                            direct_ext = {
                                "H": H_d, "error_cm": err_d,
                                "cond": float(np.linalg.cond(H_d)),
                                "n_matched": len(pairs_direct),
                                "quality": q_d,
                                "cone_positions_px": [
                                    tuple(float(v) for v in p) for p in src_d
                                ],
                                "cone_positions_world": [
                                    tuple(float(v) for v in p) for p in dst_d
                                ],
                            }
                            logger.info(
                                "Direct extrinsics match (r=%.0fpx): n=%d err=%.1fcm "
                                "corr=%.2f Q=%.3f",
                                direct_r, len(pairs_direct), err_d, corr_d, q_d,
                            )
                except (np.linalg.LinAlgError, Exception) as _exc:
                    logger.debug("Direct extrinsics match failed: %s", _exc)

                best_so_far = max(
                    [partial_ext, partial_std, direct_ext],
                    key=_quality,
                )
                logger.info(
                    "Best candidate: n=%d err=%.1fcm Q=%.3f",
                    best_so_far["n_matched"] if best_so_far else 0,
                    best_so_far["error_cm"] if best_so_far else 999,
                    _quality(best_so_far),
                )
                partial = best_so_far
            else:
                partial = _partial_grid_correspondence(
                    pixel_pts, scores_arr, world_pts, R, C,
                    match_radius_px=match_radius_px,
                    camera_extrinsics_H=None,
                )
            if partial is not None and partial["n_matched"] >= 4:
                logger.info(
                    "Partial grid correspondence: %d/%d cones matched, "
                    "reproj=%.2f cm, cond=%.1f",
                    partial["n_matched"], num_cones,
                    partial["error_cm"], partial["cond"],
                )
                return CalibrationResult(
                    method="homography",
                    homography_matrix=partial["H"],
                    pixels_per_cm=None,
                    cone_positions_px=partial["cone_positions_px"],
                    cone_positions_world=partial["cone_positions_world"],
                    reprojection_error_cm=partial["error_cm"],
                    is_valid=partial["error_cm"] < reproj_threshold,
                    condition_number=partial["cond"],
                )
            logger.warning(
                "Partial grid correspondence failed (%s). Falling back to iterative fit.",
                "no result" if partial is None else f"only {partial['n_matched']} matched",
            )

            # Last-resort fallback: iterative nearest-neighbour (all detections, not just filtered).
            H, cone_px_matched, world_matched, reproj_err = self._fit_grid_iterative(
                cone_objects, known_world_coords_cm, layout_config
            )
            if H is not None and len(cone_px_matched) >= 4:
                logger.info(
                    "Layout-based calibration (grid iterative fallback): "
                    "%d matched cones, reproj=%.2f cm",
                    len(cone_px_matched), reproj_err,
                )
                return CalibrationResult(
                    method="homography",
                    homography_matrix=H,
                    pixels_per_cm=None,
                    cone_positions_px=cone_px_matched,
                    cone_positions_world=world_matched,
                    reprojection_error_cm=reproj_err,
                    is_valid=reproj_err < reproj_threshold,
                )
            logger.warning("Grid calibration failed (D4 + iterative both failed).")
            return CalibrationResult(
                method="homography",
                homography_matrix=None,
                pixels_per_cm=None,
                cone_positions_px=[(c.cx, c.cy) for c in cone_objects_filtered],
                cone_positions_world=[],
                reprojection_error_cm=float("inf"),
                is_valid=False,
            )
        else:
            # Linear or other pattern
            num_cones = layout_config.get("cone_count") or len(cone_px)
            known_world_coords_cm = generate_cone_world_coords(layout_config, num_cones)
            cone_objects_filtered = self._filter_and_select_cones_for_layout(
                cone_objects, layout_config, num_cones
            )
            cone_px_sorted = [(c.cx, c.cy) for c in cone_objects_filtered]
            cone_objects_filtered_out = cone_objects_filtered

        cone_px_sorted = [(c.cx, c.cy) for c in cone_objects_filtered]
        n = min(len(cone_px_sorted), num_cones)
        cone_px_sorted = cone_px_sorted[:n]
        if len(known_world_coords_cm) > n:
            known_world_coords_cm = known_world_coords_cm[:n]

        layout_hint = "linear" if pattern == "linear" else "irregular"
        logger.info(
            "Layout-based calibration: %d cones (from %d after confidence filter), pattern=%s",
            n, len(cone_objects_filtered), pattern,
        )
        return self.calibrate_homography(
            frame,
            known_world_coords_cm=list(known_world_coords_cm),
            cone_colour=cone_colour,
            cone_positions_px=cone_px_sorted,
            layout_hint=layout_hint,
        )

    # ------------------------------------------------------------------
    # Single-axis calibration (jump / balance tests)
    # ------------------------------------------------------------------

    def calibrate_single_axis(
        self,
        frame: np.ndarray,
        reference_height_cm: float = 23.0,
        cone_colour: str = "yellow",
    ) -> CalibrationResult:
        """
        Compute pixels-per-cm from a reference object of known height.
        Used for vertical jump and balance tests where only Y-axis scale matters.

        Args:
            frame:               BGR frame.
            reference_height_cm: Known physical height of reference object (cm).
            cone_colour:         Colour key in HSV_RANGES (cone as reference).

        Returns:
            CalibrationResult (method='single_axis').
        """
        cone_px = self.detect_cones(frame, colour=cone_colour)
        if len(cone_px) < 2:
            logger.warning(
                "Need ≥ 2 cone detections for single-axis calibration. Got %d.",
                len(cone_px),
            )
            return CalibrationResult(
                method="single_axis",
                homography_matrix=None,
                pixels_per_cm=None,
                cone_positions_px=cone_px,
                cone_positions_world=[],
                reprojection_error_cm=float("inf"),
                is_valid=False,
            )

        # Use vertical spread of detected cones as reference
        ys = [p[1] for p in cone_px]
        height_px = max(ys) - min(ys)
        pixels_per_cm = height_px / reference_height_cm if reference_height_cm > 0 else None

        logger.info(
            "Single-axis calibration: %.2f px/cm (ref=%.1f cm, height_px=%.1f)",
            pixels_per_cm, reference_height_cm, height_px,
        )

        return CalibrationResult(
            method="single_axis",
            homography_matrix=None,
            pixels_per_cm=pixels_per_cm,
            cone_positions_px=cone_px,
            cone_positions_world=[],
            reprojection_error_cm=0.0,
            is_valid=pixels_per_cm is not None and pixels_per_cm > 0,
        )

    # ------------------------------------------------------------------
    # Coordinate transform
    # ------------------------------------------------------------------

    def pixel_to_world(
        self, point_px: tuple[float, float], calibration: CalibrationResult
    ) -> tuple[float, float]:
        """
        Convert pixel coordinates to world coordinates using calibration result.

        Args:
            point_px:    (x, y) in pixel space.
            calibration: CalibrationResult from calibrate_homography or single_axis.

        Returns:
            (x_cm, y_cm) in world space.
        """
        if not calibration.is_valid:
            raise ValueError("Cannot transform with invalid calibration.")

        if calibration.method == "homography":
            pt = np.array([[point_px]], dtype=np.float32)
            world = cv2.perspectiveTransform(pt, calibration.homography_matrix)
            return float(world[0][0][0]), float(world[0][0][1])

        if calibration.method == "single_axis":
            if calibration.pixels_per_cm is None:
                raise ValueError("pixels_per_cm is None in single_axis calibration.")
            return point_px[0] / calibration.pixels_per_cm, point_px[1] / calibration.pixels_per_cm

        raise ValueError(f"Unknown calibration method: {calibration.method}")

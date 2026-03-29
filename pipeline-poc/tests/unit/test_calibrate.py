"""
Unit tests for Calibrator — pixel_to_world transform, cone filtering,
solve_correspondence (Fix 1), spacing fix (Fix 2), unit rename (Fix 3),
safe inversion (Fix 4), and CalibrationError guard (Fix 5).

Run: pytest tests/unit/test_calibrate.py
"""
import numpy as np
import pytest

from pipeline.calibrate import (
    CONDITION_NUMBER_REJECT,
    CalibrationError,
    Calibrator,
    ConeDetection,
    _enumerate_valid_assignments,
    _partial_grid_correspondence,
    _safe_invert_H,
    solve_correspondence,
)
from pipeline.models import CalibrationResult


def test_pixel_to_world_homography():
    """Identity homography: pixel == world."""
    calibrator = Calibrator()
    H = np.eye(3, dtype=np.float32)

    result = CalibrationResult(
        method="homography",
        homography_matrix=H,
        pixels_per_cm=None,
        cone_positions_px=[],
        cone_positions_world=[],
        reprojection_error_cm=0.0,
        is_valid=True,
    )
    wx, wy = calibrator.pixel_to_world((100.0, 200.0), result)
    assert wx == pytest.approx(100.0, abs=0.1)
    assert wy == pytest.approx(200.0, abs=0.1)


def test_pixel_to_world_single_axis():
    calibrator = Calibrator()
    result = CalibrationResult(
        method="single_axis",
        homography_matrix=None,
        pixels_per_cm=4.0,  # 4 px per cm
        cone_positions_px=[],
        cone_positions_world=[],
        reprojection_error_cm=0.0,
        is_valid=True,
    )
    wx, wy = calibrator.pixel_to_world((400.0, 200.0), result)
    assert wx == pytest.approx(100.0)   # 400 / 4
    assert wy == pytest.approx(50.0)    # 200 / 4


def test_invalid_calibration_raises():
    calibrator = Calibrator()
    result = CalibrationResult(
        method="homography",
        homography_matrix=None,
        pixels_per_cm=None,
        cone_positions_px=[],
        cone_positions_world=[],
        reprojection_error_cm=float("inf"),
        is_valid=False,
    )
    with pytest.raises(ValueError):
        calibrator.pixel_to_world((0, 0), result)


def test_filter_and_select_cones_linear():
    """Filter by confidence and select N cones along fitted line."""
    calibrator = Calibrator(min_confidence=0.6)
    # 8 cones in a line (y=100, x from 50 to 400), plus 2 low-confidence outliers
    cones = [
        ConeDetection(50 + i * 50, 100, "yellow", 0.9, None) for i in range(8)
    ] + [
        ConeDetection(250, 50, "yellow", 0.3, None),   # low conf, off line
        ConeDetection(300, 150, "yellow", 0.2, None),  # low conf
    ]
    selected = calibrator._filter_and_select_cones_for_layout(
        cones,
        {"pattern": "linear", "direction": "x", "cone_count": 6},
        6,
    )
    assert len(selected) == 6
    # Low-confidence cones should be dropped; selection follows line
    scores = [c.score for c in selected]
    assert all(s >= 0.6 for s in scores)
    # Order should follow line (increasing x)
    xs = [c.cx for c in selected]
    assert xs == sorted(xs)


# ---------------------------------------------------------------------------
# Fix 1: solve_correspondence + enumerate_valid_assignments
# ---------------------------------------------------------------------------

def _make_synthetic_homography() -> np.ndarray:
    """Return a minimal H for test use: pure scale (pixel → world cm).

    H maps pixel (px, py) to world (wx, wy) via simple scaling so that
    the resulting condition number stays well below CONDITION_NUMBER_REJECT.
    The scale factor (2 cm/px) is physically plausible for a camera 2–3 m above
    a floor plane.
    """
    # Scale-only H: pixel → world, no shear or translation.
    # Condition number ≈ 1 (identity-like), well-behaved for all tests.
    scale = 2.0  # cm/px
    H = np.array([
        [scale, 0.0, 0.0],
        [0.0,   scale, 0.0],
        [0.0,   0.0,   1.0],
    ], dtype=np.float64)
    return H


def _project_world_to_pixel(world_pts: np.ndarray, H: np.ndarray) -> np.ndarray:
    """Apply H_inv to world points to get pixel positions."""
    import cv2
    H_inv = np.linalg.inv(H)
    px = cv2.perspectiveTransform(
        world_pts.reshape(-1, 1, 2).astype(np.float32), H_inv.astype(np.float32)
    ).reshape(-1, 2)
    return px


class TestEnumerateValidAssignments:
    """Unit tests for _enumerate_valid_assignments."""

    def test_linear_two_candidates(self):
        world = np.array([[0, 0], [100, 0], [200, 0], [300, 0]], dtype=np.float64)
        cands = _enumerate_valid_assignments(world, "linear")
        assert len(cands) == 2
        assert list(range(4)) in cands
        assert list(range(3, -1, -1)) in cands

    def test_grid_2x2_candidates(self):
        world = np.array([[0, 0], [100, 0], [0, 100], [100, 100]], dtype=np.float64)
        cands = _enumerate_valid_assignments(world, "grid_2x2")
        # D4 of a square has 8 symmetries, but since it's a square R=C
        # some permutations may coincide; we still need ≥ 4 distinct candidates.
        assert 4 <= len(cands) <= 8
        # Every candidate is a permutation of [0,1,2,3]
        for c in cands:
            assert sorted(c) == [0, 1, 2, 3]

    def test_grid_2x3_eight_candidates(self):
        """Non-square 2×3 grid: D4 should produce exactly 8 distinct candidates."""
        world = np.zeros((6, 2), dtype=np.float64)
        cands = _enumerate_valid_assignments(world, "grid_2x3")
        assert len(cands) == 8
        for c in cands:
            assert sorted(c) == list(range(6))

    def test_irregular_small_brute_force(self):
        """N ≤ 6 irregular: should return all N! permutations."""
        world = np.zeros((4, 2), dtype=np.float64)
        cands = _enumerate_valid_assignments(world, "irregular")
        assert len(cands) == 24  # 4!

    def test_grid_wrong_count_raises(self):
        world = np.zeros((5, 2), dtype=np.float64)
        with pytest.raises(CalibrationError, match="expects 6"):
            _enumerate_valid_assignments(world, "grid_2x3")


class TestSolveCorrespondence:
    """Integration tests for solve_correspondence (Fix 1).

    Notes on test design
    --------------------
    cv2.findHomography with RANSAC is non-deterministic and can be finicky with
    perfectly-exact (zero-noise) data.  All grid/irregular tests here add a
    small amount of Gaussian noise (0.5 px, fixed seed) to mimic realistic
    SAM3 detection jitter.  This also makes RANSAC behave reliably.

    The test threshold is 2.0 cm (relaxed from the production 1.5 cm) to
    account for noise propagation: 0.5 px × 2 cm/px scale ≈ 1.0 cm world
    error per cone; the mean over 4-6 cones is safely below 2.0 cm.
    """

    # Noise added to pixel positions for RANSAC stability (realistic: ~SAM3 centroid jitter)
    NOISE_PX = 0.5
    # Test error threshold (cm) — relaxed from the production 1.5 cm due to noise
    TEST_THRESHOLD_CM = 2.0

    def _run(self, world_pts, permutation, layout, noise_px=None):
        """
        Project world_pts through a synthetic H to get pixel_pts in the given
        permuted order, add deterministic noise, then call solve_correspondence.
        """
        import cv2
        if noise_px is None:
            noise_px = self.NOISE_PX
        H_true = _make_synthetic_homography()
        H_inv = np.linalg.inv(H_true)
        pixel_pts = cv2.perspectiveTransform(
            world_pts.reshape(-1, 1, 2).astype(np.float32), H_inv.astype(np.float32)
        ).reshape(-1, 2).astype(np.float64)

        # Apply permutation to pixel_pts (simulates camera seeing cones out of world order)
        pixel_permuted = pixel_pts[permutation]
        rng = np.random.default_rng(42)
        pixel_permuted = pixel_permuted + rng.normal(0, noise_px, pixel_permuted.shape)

        return solve_correspondence(pixel_permuted, world_pts, layout,
                                    reproj_threshold_cm=self.TEST_THRESHOLD_CM)

    def test_linear_collinear_raises(self):
        """Collinear world points (linear shuttle cones) are degenerate for findHomography.

        Per the design doc Section 2, linear-layout tests (sprint, shuttle) should
        use pixel-threshold detection rather than H.  solve_correspondence correctly
        raises CalibrationError, making the failure loud rather than silent.
        """
        world = np.array([[0, 0], [100, 0], [200, 0], [300, 0]], dtype=np.float64)
        # Any permutation of collinear world points → collinear pixels → H is degenerate
        pixel = np.array([[10, 50], [60, 50], [110, 50], [160, 50]], dtype=np.float64)
        with pytest.raises(CalibrationError):
            solve_correspondence(pixel, world, "linear")

    def test_grid_2x3_identity(self):
        """Grid in natural order with realistic noise: error must be below test threshold."""
        world = np.array([
            [0, 0], [100, 0], [200, 0],
            [0, 300], [100, 300], [200, 300],
        ], dtype=np.float64)
        result = self._run(world, [0, 1, 2, 3, 4, 5], "grid_2x3")
        assert result["error_cm"] < self.TEST_THRESHOLD_CM
        assert result["cond"] < CONDITION_NUMBER_REJECT

    def test_grid_2x3_rotated_90(self):
        """2×3 grid with 90° rotation: D4 search recovers correct assignment."""
        world = np.array([
            [0, 0], [100, 0], [200, 0],
            [0, 300], [100, 300], [200, 300],
        ], dtype=np.float64)
        # Rotate the grid index matrix 90° and flatten to get a permuted pixel order
        grid = np.arange(6).reshape(2, 3)
        perm = np.rot90(grid).flatten().tolist()
        result = self._run(world, perm, "grid_2x3")
        assert result["error_cm"] < self.TEST_THRESHOLD_CM

    def test_grid_2x3_flipped(self):
        """Horizontally-flipped grid: one of the 8 D4 candidates recovers it."""
        world = np.array([
            [0, 0], [100, 0], [200, 0],
            [0, 300], [100, 300], [200, 300],
        ], dtype=np.float64)
        perm = [2, 1, 0, 5, 4, 3]  # left-right mirror
        result = self._run(world, perm, "grid_2x3")
        assert result["error_cm"] < self.TEST_THRESHOLD_CM

    def test_irregular_4_cones(self):
        """T-drill 4-cone layout (irregular, N ≤ 6): brute force recovers assignment."""
        world = np.array([
            [0, 0], [500, 0], [500, -300], [500, 300],
        ], dtype=np.float64)
        result = self._run(world, [2, 0, 3, 1], "irregular")
        assert result["error_cm"] < self.TEST_THRESHOLD_CM

    def test_too_few_points_raises(self):
        """Fewer than 4 pixel points must raise CalibrationError."""
        world = np.array([[0, 0], [100, 0], [200, 0]], dtype=np.float64)
        pixel = np.zeros((3, 2), dtype=np.float64)
        with pytest.raises(CalibrationError, match="≥ 4"):
            solve_correspondence(pixel, world, "linear")

    def test_degenerate_collinear_pixel_raises(self):
        """All pixel points collinear → H is degenerate → CalibrationError."""
        world = np.array([[0, 0], [100, 0], [0, 100], [100, 100]], dtype=np.float64)
        pixel = np.array([[10.0, 10.0], [20.0, 10.0], [30.0, 10.0], [40.0, 10.0]],
                         dtype=np.float64)
        with pytest.raises(CalibrationError):
            solve_correspondence(pixel, world, "grid_2x2", reproj_threshold_cm=5.0)


# ---------------------------------------------------------------------------
# Fix 4: _safe_invert_H condition-number check
# ---------------------------------------------------------------------------

class TestSafeInvertH:

    def test_identity_inverts_correctly(self):
        H = np.eye(3, dtype=np.float64)
        H_inv = _safe_invert_H(H)
        assert H_inv is not None
        np.testing.assert_allclose(H_inv, np.eye(3), atol=1e-10)

    def test_scale_homography_inverts_correctly(self):
        """A pure-scale H (cond == 1) should invert cleanly."""
        H = _make_synthetic_homography()   # 2 cm/px scale
        H_inv = _safe_invert_H(H)
        assert H_inv is not None
        product = H @ H_inv
        np.testing.assert_allclose(product, np.eye(3), atol=1e-8)

    def test_near_singular_returns_none(self):
        """Rows 0 and 1 identical → condition number >> 1e8 → must return None."""
        # Two identical rows → rank 2 at best → determinant == 0
        H = np.array([
            [1.0, 2.0, 3.0],
            [1.0, 2.0, 3.0],
            [0.0, 0.0, 1.0],
        ], dtype=np.float64)
        H_inv = _safe_invert_H(H)
        assert H_inv is None


# ---------------------------------------------------------------------------
# Fix 5: CalibrationError guard in BaseMetricExtractor
# ---------------------------------------------------------------------------

class TestCalibrationGuard:

    def _make_invalid_calib(self):
        return CalibrationResult(
            method="homography",
            homography_matrix=None,
            pixels_per_cm=None,
            cone_positions_px=[],
            cone_positions_world=[],
            reprojection_error_cm=float("inf"),
            is_valid=False,
        )

    def test_agility_raises_on_invalid_calibration(self):
        from pipeline.tests.agility import AgilityExtractor
        ext = AgilityExtractor({}, self._make_invalid_calib())
        with pytest.raises(CalibrationError):
            ext.extract([], [], [])

    def test_shuttle_raises_on_invalid_calibration(self):
        from pipeline.tests.shuttle import ShuttleExtractor
        ext = ShuttleExtractor({}, self._make_invalid_calib())
        with pytest.raises(CalibrationError):
            ext.extract([], [], [])

    def test_sprint_raises_on_invalid_calibration(self):
        from pipeline.tests.sprint import SprintExtractor
        ext = SprintExtractor({}, self._make_invalid_calib())
        with pytest.raises(CalibrationError):
            ext.extract([], [], [])

    def test_balance_does_not_raise_on_invalid_calibration(self):
        """Balance needs no calibration; invalid calibration must be tolerated."""
        from pipeline.tests.balance import BalanceExtractor
        ext = BalanceExtractor({}, self._make_invalid_calib())
        # Should not raise; will return [] because frames=[] fails validate_inputs
        result = ext.extract([], [], [])
        assert result == []

    def test_explosiveness_does_not_raise_on_invalid_calibration(self):
        """Explosiveness uses single_axis; invalid homography calibration is tolerated."""
        from pipeline.tests.explosiveness import ExplosivenessExtractor
        ext = ExplosivenessExtractor({}, self._make_invalid_calib())
        result = ext.extract([], [], [])
        assert result == []


# ---------------------------------------------------------------------------
# _partial_grid_correspondence — missing / scattered cones
# ---------------------------------------------------------------------------

class TestPartialGridCorrespondence:
    """Tests for D4-aware partial grid matching when N_det < N_world."""

    # Scale-only homography: 2 cm per pixel (world cm = pixel * 2)
    _SCALE = 2.0

    @staticmethod
    def _make_world_grid(R: int, C: int, sx: float = 100.0, sy: float = 200.0):
        """Return (R*C, 2) world points on a regular grid."""
        pts = []
        for r in range(R):
            for c in range(C):
                pts.append([c * sx, r * sy])
        return np.array(pts, dtype=np.float64)

    def _project_to_pixel(self, world_pts: np.ndarray) -> np.ndarray:
        """Apply inverse of scale H to get pixel coords."""
        return world_pts / self._SCALE

    def _make_scores(self, N: int, rng) -> np.ndarray:
        return rng.uniform(0.5, 1.0, N)

    def test_full_grid_no_missing(self):
        """All cones present — partial solver must recover H with low error."""
        R, C = 3, 4
        world = self._make_world_grid(R, C)
        pixel = self._project_to_pixel(world)
        rng = np.random.default_rng(0)
        scores = self._make_scores(len(pixel), rng)

        result = _partial_grid_correspondence(pixel, scores, world, R, C)
        assert result is not None
        assert result["n_matched"] == R * C
        assert result["error_cm"] < 2.0

    def test_10_missing_scattered(self):
        """Drop 10 random cones from a 6×7 grid — must still calibrate."""
        R, C = 6, 7
        world = self._make_world_grid(R, C, sx=70.0, sy=300.0)
        pixel = self._project_to_pixel(world)

        rng = np.random.default_rng(42)
        keep = sorted(rng.choice(R * C, R * C - 10, replace=False))
        pixel_partial = pixel[keep]
        scores = self._make_scores(len(pixel_partial), rng)

        result = _partial_grid_correspondence(pixel_partial, scores, world, R, C,
                                              match_radius_px=80.0)
        assert result is not None, "Partial grid solver returned None with 10 missing"
        assert result["n_matched"] >= R * C - 10, (
            f"Expected ≥ {R*C-10} matches, got {result['n_matched']}"
        )
        assert result["error_cm"] < 3.0, (
            f"Reprojection error {result['error_cm']:.2f} cm too high"
        )

    def test_rotated_180_with_missing(self):
        """Camera at opposite end (180° D4 rotation) with 5 missing cones."""
        R, C = 4, 3
        world = self._make_world_grid(R, C)
        pixel = self._project_to_pixel(world)

        # Simulate 180°: reverse pixel order, drop 5
        pixel_rotated = pixel[::-1]
        rng = np.random.default_rng(7)
        keep = sorted(rng.choice(R * C, R * C - 5, replace=False))
        pixel_partial = pixel_rotated[keep]
        scores = self._make_scores(len(pixel_partial), rng)

        result = _partial_grid_correspondence(pixel_partial, scores, world, R, C,
                                              match_radius_px=80.0)
        assert result is not None, "Should handle 180° rotation + 5 missing"
        assert result["n_matched"] >= R * C - 5
        assert result["error_cm"] < 3.0

    def test_score_priority_no_position_ordering(self):
        """Detections deliberately out of pixel order — result must not depend on position sort."""
        R, C = 2, 3
        world = self._make_world_grid(R, C)
        pixel = self._project_to_pixel(world)

        # Shuffle pixel order
        rng = np.random.default_rng(99)
        idx = rng.permutation(R * C)
        pixel_shuffled = pixel[idx]
        scores = self._make_scores(R * C, rng)

        result = _partial_grid_correspondence(pixel_shuffled, scores, world, R, C)
        assert result is not None
        assert result["n_matched"] == R * C
        assert result["error_cm"] < 2.0

    def test_too_few_detections_returns_none(self):
        """Fewer than 4 detections — must return None (can't solve H)."""
        R, C = 3, 3
        world = self._make_world_grid(R, C)
        pixel = self._project_to_pixel(world)[:3]  # only 3
        scores = np.ones(3)

        result = _partial_grid_correspondence(pixel, scores, world, R, C)
        assert result is None or result["n_matched"] < 4

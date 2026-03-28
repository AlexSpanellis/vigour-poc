"""
Unit tests for Calibrator — pixel_to_world transform, cone filtering.
Run: pytest tests/unit/test_calibrate.py
"""
import numpy as np
import pytest

from pipeline.calibrate import Calibrator, ConeDetection
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
        reprojection_error_px=0.0,
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
        reprojection_error_px=0.0,
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
        reprojection_error_px=float("inf"),
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

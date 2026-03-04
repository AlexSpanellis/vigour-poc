"""
Unit tests for Calibrator — pixel_to_world transform.
Run: pytest tests/unit/test_calibrate.py
"""
import numpy as np
import pytest

from pipeline.calibrate import Calibrator
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

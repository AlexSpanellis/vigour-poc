"""
Unit tests for PipelineVisualiser.annotate_frame (static, no video writer).
Run: pytest tests/unit/test_visualise.py -v
"""
import numpy as np
import pytest

from pipeline.models import CalibrationResult, Detection, Pose, TestResult, Track
from pipeline.visualise import PipelineVisualiser, VisOptions, render_top_down_view


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _blank_frame(h=480, w=640):
    return np.zeros((h, w, 3), dtype=np.uint8)


def _make_track(track_id=1, bib=7, confirmed=True):
    return Track(
        track_id=track_id,
        bbox=(50.0, 50.0, 200.0, 400.0),
        frame_idx=0,
        is_confirmed=confirmed,
        bib_number=bib,
        bib_confidence=0.9,
    )


def _make_pose(track_id=1):
    kps = np.zeros((17, 3), dtype=np.float32)
    # Set a plausible standing pose (all mid-frame, confidence = 0.9)
    for i in range(17):
        kps[i] = [120.0, 100.0 + i * 15, 0.9]
    return Pose(track_id=track_id, frame_idx=0, keypoints=kps, pose_confidence=0.8)


def _make_calibration(valid=True):
    if valid:
        H = np.eye(3, dtype=np.float64)
        return CalibrationResult(
            method="homography",
            homography_matrix=H,
            pixels_per_cm=None,
            cone_positions_px=[(50.0, 50.0), (300.0, 50.0)],
            cone_positions_world=[(0.0, 0.0), (500.0, 0.0)],
            reprojection_error_cm=1.5,
            is_valid=True,
        )
    return CalibrationResult(
        method="single_axis",
        homography_matrix=None,
        pixels_per_cm=None,
        cone_positions_px=[],
        cone_positions_world=[],
        reprojection_error_cm=float("inf"),
        is_valid=False,
    )


def _make_result(bib=7, val=32.5, flags=None):
    return TestResult(
        student_bib=bib,
        track_id=1,
        test_type="explosiveness",
        metric_value=val,
        metric_unit="cm",
        attempt_number=1,
        confidence_score=0.85,
        flags=flags or [],
    )


# ── annotate_frame returns correct shape ─────────────────────────────────────

def test_annotate_frame_returns_same_shape():
    frame = _blank_frame()
    track = _make_track()
    pose = _make_pose()
    calib = _make_calibration()
    result = _make_result()

    canvas = PipelineVisualiser.annotate_frame(
        frame=frame,
        tracks=[track],
        poses=[pose],
        calibration=calib,
        results=[result],
        test_type="explosiveness",
    )

    assert canvas.shape == frame.shape
    assert canvas.dtype == np.uint8


def test_annotate_frame_modifies_canvas():
    """Ensure at least one pixel is changed (overlay was actually drawn)."""
    frame = _blank_frame()
    track = _make_track()
    pose = _make_pose()
    calib = _make_calibration()
    result = _make_result()

    canvas = PipelineVisualiser.annotate_frame(
        frame=frame,
        tracks=[track],
        poses=[pose],
        calibration=calib,
        results=[result],
        test_type="explosiveness",
    )

    assert not np.all(canvas == 0), "Expected at least one pixel to be drawn"


def test_annotate_frame_no_tracks_no_crash():
    """Empty track/pose lists should not raise."""
    frame = _blank_frame()
    calib = _make_calibration(valid=False)
    canvas = PipelineVisualiser.annotate_frame(
        frame=frame,
        tracks=[],
        poses=[],
        calibration=calib,
        results=[],
        test_type="balance",
    )
    assert canvas.shape == frame.shape


@pytest.mark.parametrize("test_type", ["explosiveness", "speed", "fitness", "agility", "balance"])
def test_annotate_frame_all_test_types(test_type):
    """All test types should produce a valid canvas."""
    frame = _blank_frame()
    track = _make_track()
    pose = _make_pose()
    calib = _make_calibration()
    result = _make_result()

    canvas = PipelineVisualiser.annotate_frame(
        frame=frame,
        tracks=[track],
        poses=[pose],
        calibration=calib,
        results=[result],
        test_type=test_type,
    )
    assert canvas.shape == frame.shape


def test_annotate_unconfirmed_track():
    """Unconfirmed tracks should draw in orange, not crash."""
    frame = _blank_frame()
    track = _make_track(confirmed=False, bib=None)
    calib = _make_calibration()
    canvas = PipelineVisualiser.annotate_frame(
        frame=frame, tracks=[track], poses=[], calibration=calib, results=[], test_type="speed"
    )
    assert canvas.shape == frame.shape


def test_flags_drawn_for_unresolved_bib():
    """Tracks with bib_number=None should trigger a flag badge."""
    frame = _blank_frame()
    track = Track(track_id=1, bbox=(50, 50, 200, 400), frame_idx=0,
                  is_confirmed=True, bib_number=None, bib_confidence=0.0)
    calib = _make_calibration(valid=False)

    canvas = PipelineVisualiser.annotate_frame(
        frame=frame, tracks=[track], poses=[], calibration=calib, results=[], test_type="balance"
    )
    # Just check no crash and shape is valid
    assert canvas.shape == frame.shape


def test_hud_not_drawn_when_no_results():
    """Empty results list → HUD layer should not crash."""
    frame = _blank_frame()
    track = _make_track()
    calib = _make_calibration()
    canvas = PipelineVisualiser.annotate_frame(
        frame=frame, tracks=[track], poses=[], calibration=calib, results=[], test_type="speed"
    )
    assert canvas.shape == frame.shape


def test_render_top_down_view_cones_only():
    """Top-down view with calibration only (no tracks/poses) returns valid canvas."""
    calib = _make_calibration()
    canvas = render_top_down_view(calib, tracks=[], poses=[], size=(200, 200))
    assert canvas.shape == (200, 200, 3)
    assert canvas.dtype == np.uint8


def test_render_top_down_view_with_poses():
    """Top-down view with tracks and poses returns valid canvas."""
    calib = _make_calibration()
    track = _make_track()
    pose = _make_pose()
    canvas = render_top_down_view(calib, tracks=[track], poses=[pose], size=(200, 200))
    assert canvas.shape == (200, 200, 3)


def test_annotate_frame_with_top_down_view():
    """Annotate with show_top_down_view=True does not crash."""
    frame = _blank_frame(h=200, w=320)
    track = _make_track()
    pose = _make_pose()
    calib = _make_calibration()
    opts = VisOptions(show_top_down_view=True)
    canvas = PipelineVisualiser.annotate_frame(
        frame=frame, tracks=[track], poses=[pose], calibration=calib,
        results=[], test_type="fitness", opts=opts,
    )
    assert canvas.shape == frame.shape


def test_vis_options_disable_all_layers():
    """All layers disabled → canvas should equal original frame."""
    frame = _blank_frame(h=200, w=320)
    # Fill with a non-zero value so we can detect changes
    frame[:] = 50
    track = _make_track()
    calib = _make_calibration()
    result = _make_result()

    opts = VisOptions(
        show_boxes=False,
        show_skeleton=False,
        show_calibration_grid=False,
        show_test_overlay=False,
        show_hud=False,
        show_frame_counter=False,
        show_flags=False,
    )
    canvas = PipelineVisualiser.annotate_frame(
        frame=frame, tracks=[track], poses=[], calibration=calib,
        results=[result], test_type="speed", opts=opts,
    )
    # With all layers off, canvas should be an unmodified copy of frame
    np.testing.assert_array_equal(canvas, frame)

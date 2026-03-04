"""
Unit tests for shared pipeline data models.
Run: pytest tests/unit/test_models.py
"""
import numpy as np
import pytest

from pipeline.models import Detection, Track, Pose, CalibrationResult, TestResult


def test_detection_fields():
    d = Detection(bbox=(0, 0, 100, 200), confidence=0.95, class_id=0, frame_idx=5)
    assert d.class_id == 0
    assert d.confidence == pytest.approx(0.95)


def test_track_defaults():
    t = Track(track_id=1, bbox=(10, 20, 110, 220), frame_idx=0, is_confirmed=True)
    assert t.bib_number is None
    assert t.bib_confidence == 0.0


def test_pose_keypoints_shape():
    kps = np.zeros((17, 3), dtype=np.float32)
    p = Pose(track_id=1, frame_idx=0, keypoints=kps, pose_confidence=0.0)
    assert p.keypoints.shape == (17, 3)


def test_test_result_defaults():
    r = TestResult(
        student_bib=7,
        track_id=3,
        test_type="explosiveness",
        metric_value=32.5,
        metric_unit="cm",
        attempt_number=1,
        confidence_score=0.85,
    )
    assert r.flags == []
    assert r.raw_data == {}

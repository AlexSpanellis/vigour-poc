"""
Unit tests for PipelineCache — round-trip save/load for all stages.
Run: pytest tests/unit/test_cache.py -v

These tests use tmp_path (pytest fixture) so no persistent disk state.
"""
import numpy as np
import pytest

from pipeline.cache import PipelineCache
from pipeline.models import (
    CalibrationResult,
    Detection,
    Pose,
    TestResult,
    Track,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def cache(tmp_path):
    return PipelineCache(job_id="test-job-001", cache_root=tmp_path)


def _make_detections(n_frames=3, n_dets=2):
    return [
        [Detection(bbox=(10.0 * j, 20.0, 80.0, 200.0), confidence=0.9, class_id=0, frame_idx=i)
         for j in range(n_dets)]
        for i in range(n_frames)
    ]


def _make_tracks(n_frames=3, n_tracks=2):
    return [
        [Track(track_id=j + 1, bbox=(10.0 * j, 20.0, 80.0, 200.0),
               frame_idx=i, is_confirmed=True, bib_number=j + 1, bib_confidence=0.85)
         for j in range(n_tracks)]
        for i in range(n_frames)
    ]


def _make_poses(n_frames=3, n_poses=2):
    return [
        [Pose(track_id=j + 1, frame_idx=i,
              keypoints=np.ones((17, 3), dtype=np.float32) * (i + j + 1),
              pose_confidence=0.75)
         for j in range(n_poses)]
        for i in range(n_frames)
    ]


# ── Ingest ────────────────────────────────────────────────────────────────────

def test_ingest_roundtrip(cache):
    frame_indices = list(range(0, 60, 2))
    timestamps = [i / 15.0 for i in range(30)]
    cache.save_ingest(frame_indices, timestamps, test_type="explosiveness")

    assert cache.has("ingest")
    fi2, ts2 = cache.load_ingest()
    assert fi2 == frame_indices
    assert ts2 == pytest.approx(timestamps)


# ── Detections ────────────────────────────────────────────────────────────────

def test_detections_roundtrip(cache):
    dets = _make_detections()
    cache.save_detections(dets)
    assert cache.has("detect")
    loaded = cache.load_detections()

    assert len(loaded) == len(dets)
    for orig_frame, loaded_frame in zip(dets, loaded):
        assert len(orig_frame) == len(loaded_frame)
        for orig, loaded_d in zip(orig_frame, loaded_frame):
            assert orig.bbox == pytest.approx(loaded_d.bbox)
            assert orig.confidence == pytest.approx(loaded_d.confidence)


def test_empty_detections_roundtrip(cache):
    """Empty frames (no detections) should not crash."""
    dets = [[], [], []]
    cache.save_detections(dets)
    loaded = cache.load_detections()
    assert all(len(f) == 0 for f in loaded)


# ── Tracks ────────────────────────────────────────────────────────────────────

def test_tracks_roundtrip(cache):
    tracks = _make_tracks()
    cache.save_tracks(tracks)
    assert cache.has("track")
    loaded = cache.load_tracks()

    assert len(loaded) == len(tracks)
    for orig_frame, loaded_frame in zip(tracks, loaded):
        for orig, loaded_t in zip(orig_frame, loaded_frame):
            assert orig.track_id == loaded_t.track_id
            assert orig.bbox == pytest.approx(loaded_t.bbox)
            assert orig.is_confirmed == loaded_t.is_confirmed
            assert orig.bib_number == loaded_t.bib_number
            assert orig.bib_confidence == pytest.approx(loaded_t.bib_confidence)


def test_tracks_with_null_bib(cache):
    """Tracks with bib_number=None should survive round-trip."""
    tracks = [[
        Track(track_id=1, bbox=(0, 0, 100, 200), frame_idx=0, is_confirmed=True,
              bib_number=None, bib_confidence=0.0)
    ]]
    cache.save_tracks(tracks)
    loaded = cache.load_tracks()
    assert loaded[0][0].bib_number is None


# ── Poses ─────────────────────────────────────────────────────────────────────

def test_poses_roundtrip(cache):
    poses = _make_poses()
    cache.save_poses(poses)
    assert cache.has("pose")
    loaded = cache.load_poses()

    assert len(loaded) == len(poses)
    for orig_frame, loaded_frame in zip(poses, loaded):
        for orig, loaded_p in zip(orig_frame, loaded_frame):
            assert orig.track_id == loaded_p.track_id
            assert orig.frame_idx == loaded_p.frame_idx
            assert orig.pose_confidence == pytest.approx(loaded_p.pose_confidence)
            np.testing.assert_allclose(orig.keypoints, loaded_p.keypoints, rtol=1e-5)


# ── OCR ───────────────────────────────────────────────────────────────────────

def test_ocr_roundtrip(cache):
    frame_readings = [{1: 7, 2: 14}, {1: 7, 2: None}, {1: 8, 2: 14}]
    resolved = {1: (7, 0.85), 2: (14, 1.0)}
    cache.save_ocr(frame_readings, resolved)
    assert cache.has("ocr")
    loaded_readings, loaded_resolved = cache.load_ocr()

    assert loaded_readings[0][1] == 7
    assert loaded_readings[1][2] is None
    assert loaded_resolved[1] == (7, pytest.approx(0.85))
    assert loaded_resolved[2] == (14, pytest.approx(1.0))


# ── Calibration ───────────────────────────────────────────────────────────────

def test_calibration_homography_roundtrip(cache):
    H = np.eye(3, dtype=np.float64) * 2
    calib = CalibrationResult(
        method="homography",
        homography_matrix=H,
        pixels_per_cm=None,
        cone_positions_px=[(100.0, 200.0), (300.0, 400.0)],
        cone_positions_world=[(0.0, 0.0), (500.0, 0.0)],
        reprojection_error_px=1.23,
        is_valid=True,
    )
    cache.save_calibration(calib)
    assert cache.has("calibrate")
    loaded = cache.load_calibration()

    assert loaded.method == "homography"
    assert loaded.is_valid is True
    assert loaded.reprojection_error_px == pytest.approx(1.23)
    np.testing.assert_allclose(loaded.homography_matrix, H)
    assert len(loaded.cone_positions_px) == 2


def test_calibration_single_axis_roundtrip(cache):
    calib = CalibrationResult(
        method="single_axis",
        homography_matrix=None,
        pixels_per_cm=4.5,
        cone_positions_px=[],
        cone_positions_world=[],
        reprojection_error_px=0.0,
        is_valid=True,
    )
    cache.save_calibration(calib)
    loaded = cache.load_calibration()

    assert loaded.method == "single_axis"
    assert loaded.pixels_per_cm == pytest.approx(4.5)
    assert loaded.homography_matrix is None


# ── Results ───────────────────────────────────────────────────────────────────

def test_results_roundtrip(cache):
    results = [
        TestResult(
            student_bib=7,
            track_id=1,
            test_type="explosiveness",
            metric_value=32.5,
            metric_unit="cm",
            attempt_number=1,
            confidence_score=0.88,
            flags=[],
            raw_data={"baseline_y_px": 950.0},
        ),
        TestResult(
            student_bib=-1,
            track_id=2,
            test_type="explosiveness",
            metric_value=28.1,
            metric_unit="cm",
            attempt_number=1,
            confidence_score=0.4,
            flags=["bib_unresolved"],
        ),
    ]
    cache.save_results(results)
    assert cache.has("results")
    loaded = cache.load_results()

    assert len(loaded) == 2
    assert loaded[0].student_bib == 7
    assert loaded[0].metric_value == pytest.approx(32.5)
    assert loaded[1].flags == ["bib_unresolved"]


# ── Cache control ─────────────────────────────────────────────────────────────

def test_has_returns_false_before_save(cache):
    assert not cache.has("detect")
    assert not cache.has("pose")


def test_invalidate_removes_stage_and_downstream(cache):
    dets = _make_detections()
    tracks = _make_tracks()
    poses = _make_poses()
    cache.save_detections(dets)
    cache.save_tracks(tracks)
    cache.save_poses(poses)

    assert cache.has("detect")
    assert cache.has("track")
    assert cache.has("pose")

    cache.invalidate("track")  # should remove track + pose

    assert cache.has("detect")         # upstream retained
    assert not cache.has("track")      # invalidated
    assert not cache.has("pose")       # downstream also removed


def test_clear_removes_all(cache, tmp_path):
    cache.save_ingest([0, 1, 2], [0.0, 0.1, 0.2])
    cache.save_detections(_make_detections())
    cache.clear()

    # Cache directory should no longer exist
    import os
    assert not os.path.exists(str(tmp_path / "test-job-001"))


def test_summary_reports_size(cache):
    cache.save_ingest([0, 1], [0.0, 0.1])
    summary = cache.summary()
    assert "size_mb" in summary
    assert summary["size_mb"] >= 0
    assert "ingest" in summary["stages_cached"]


def test_list_jobs(tmp_path):
    for jid in ("job-a", "job-b"):
        c = PipelineCache(job_id=jid, cache_root=tmp_path)
        c.save_ingest([0], [0.0], test_type="balance")

    jobs = PipelineCache.list_jobs(cache_root=tmp_path)
    job_ids = [j["job_id"] for j in jobs]
    assert "job-a" in job_ids
    assert "job-b" in job_ids

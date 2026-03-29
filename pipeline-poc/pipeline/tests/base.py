"""
BaseMetricExtractor — shared interface for all test-specific extractors.
All five extractors (explosiveness, sprint, shuttle, agility, balance) inherit from this.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from pipeline.calibrate import CalibrationError
from pipeline.models import CalibrationResult, Pose, TestResult, Track


class BaseMetricExtractor(ABC):
    """Abstract base class for all test-specific metric extractors.

    Subclasses implement:
        extract()         — primary computation, returns list[TestResult]
        validate_inputs() — guards against bad data before heavy processing

    Class attribute
    ---------------
    requires_valid_calibration : bool
        When True, ``extract()`` raises :class:`~pipeline.calibrate.CalibrationError`
        if the supplied calibration has ``is_valid=False``, preventing a bad
        ``metric_value`` from ever reaching the database.
        Tests that need no spatial calibration (balance, push-ups, reflex)
        should set this to False.
    """

    requires_valid_calibration: bool = True

    def __init__(self, geometry_config: dict, calibration: CalibrationResult):
        self.config = geometry_config
        self.calibration = calibration

    def extract(
        self,
        tracks: list[list[Track]],
        poses: list[list[Pose]],
        frames: list[np.ndarray],
    ) -> list[TestResult]:
        """Run extraction, with a hard-halt guard for invalid calibrations.

        Raises
        ------
        CalibrationError
            If ``requires_valid_calibration`` is True and the calibration is
            not valid.  The caller (worker session boundary) must catch this
            and record a ``calibration_failed`` event rather than writing an
            empty or wrong ``metric_value``.
        """
        if self.requires_valid_calibration and not self.calibration.is_valid:
            raise CalibrationError(
                f"{type(self).__name__} requires valid calibration but "
                f"is_valid=False (error={self.calibration.reprojection_error_cm:.2f} cm). "
                "Record a calibration_failed event and do not write metric_value."
            )
        return self._extract(tracks, poses, frames)

    @abstractmethod
    def validate_inputs(
        self,
        tracks: list[list[Track]],
        poses: list[list[Pose]],
        frames: list[np.ndarray],
    ) -> bool:
        """Minimum data quality gate before running extraction.

        Return False to skip extraction and flag the clip.
        """
        raise NotImplementedError

    @abstractmethod
    def _extract(
        self,
        tracks: list[list[Track]],
        poses: list[list[Pose]],
        frames: list[np.ndarray],
    ) -> list[TestResult]:
        """Subclass implementation — called only after calibration guard passes."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    @staticmethod
    def hip_midpoint(pose: Pose) -> tuple[float, float] | None:
        """Return (x, y) midpoint of hip keypoints if both confident."""
        kps = pose.keypoints
        l_hip_conf = kps[11, 2]
        r_hip_conf = kps[12, 2]
        if l_hip_conf > 0.3 and r_hip_conf > 0.3:
            x = (kps[11, 0] + kps[12, 0]) / 2
            y = (kps[11, 1] + kps[12, 1]) / 2
            return (x, y)
        return None

    @staticmethod
    def ankle_positions(pose: Pose) -> tuple[tuple | None, tuple | None]:
        """Return ((lx, ly), (rx, ry)) ankle coords if confident, else None."""
        kps = pose.keypoints
        l = (kps[15, 0], kps[15, 1]) if kps[15, 2] > 0.3 else None
        r = (kps[16, 0], kps[16, 1]) if kps[16, 2] > 0.3 else None
        return l, r

    @staticmethod
    def build_track_pose_map(
        frame_tracks: list[Track],
        frame_poses: list[Pose],
    ) -> dict[int, Pose]:
        """Map track_id → Pose for quick lookup within a frame."""
        return {p.track_id: p for p in frame_poses}

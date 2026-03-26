"""
BaseMetricExtractor — shared interface for all test-specific extractors.
All five extractors (explosiveness, sprint, shuttle, agility, balance) inherit from this.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from pipeline.models import CalibrationResult, Pose, TestResult, Track


class BaseMetricExtractor(ABC):
    """
    Abstract base class for all test-specific metric extractors.

    Subclasses implement:
        extract()        — primary computation, returns list[TestResult]
        validate_inputs() — guards against bad data before heavy processing
    """

    def __init__(self, geometry_config: dict, calibration: CalibrationResult):
        self.config = geometry_config
        self.calibration = calibration

    @abstractmethod
    def extract(
        self,
        tracks: list[list[Track]],    # outer list = frames, inner = tracks per frame
        poses: list[list[Pose]],
        frames: list[np.ndarray],
    ) -> list[TestResult]:
        """
        Run test-specific metric extraction over the full clip.

        Args:
            tracks: Per-frame list of active Track objects.
            poses:  Per-frame list of Pose objects (aligned with tracks).
            frames: Raw BGR frames (for visualisation / fallback logic).

        Returns:
            One TestResult per student per attempt.
        """
        raise NotImplementedError

    @abstractmethod
    def validate_inputs(
        self,
        tracks: list[list[Track]],
        poses: list[list[Pose]],
        frames: list[np.ndarray],
    ) -> bool:
        """
        Minimum data quality gate before running extraction.
        Return False to skip extraction and flag the clip.
        """
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

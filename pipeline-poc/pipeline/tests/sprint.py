"""
Sprint (5m Speed) Metric Extractor

Algorithm:
    1. Detect start/finish cone positions → world coords via homography
    2. Project crossing lines into pixel space
    3. Per student: detect hip centroid crossing start line, then finish line
    4. Sprint time = (finish_frame - start_frame) / fps
    5. Sub-frame interpolation for precision

Exploration surface:
    - Pixel X threshold vs projected ground-plane line from homography
    - False start handling (crosses then returns)
    - Sub-frame interpolation method
"""
from __future__ import annotations

import logging

import numpy as np

from pipeline.models import CalibrationResult, Pose, TestResult, Track
from pipeline.tests.base import BaseMetricExtractor

logger = logging.getLogger(__name__)


class SprintExtractor(BaseMetricExtractor):

    def validate_inputs(self, tracks, poses, frames) -> bool:
        if not self.calibration.is_valid:
            logger.warning("Invalid calibration — cannot compute sprint times.")
            return False
        if len(frames) < 10:
            logger.warning("Too few frames for sprint detection.")
            return False
        return True

    def _extract(
        self,
        tracks: list[list[Track]],
        poses: list[list[Pose]],
        frames: list[np.ndarray],
    ) -> list[TestResult]:
        if not self.validate_inputs(tracks, poses, frames):
            return []

        fps = self.config.get("fps", 15)
        sprint_distance_m = self.config.get("sprint_distance_m", 5.0)
        num_attempts = self.config.get("num_attempts", 3)

        # --- Placeholder: start/finish line X positions in pixel space ---
        # In practice, derive from calibration.cone_positions_px + known geometry
        # TODO: parse from geometry_config once cone detection is validated
        start_line_x_px = self.config.get("start_line_x_px", 400)
        finish_line_x_px = self.config.get("finish_line_x_px", 1500)

        # Build per-track hip X time series
        track_hip_x: dict[int, list[tuple[int, float]]] = {}
        for frame_i, (frame_tracks, frame_poses) in enumerate(zip(tracks, poses)):
            pose_map = self.build_track_pose_map(frame_tracks, frame_poses)
            for track in frame_tracks:
                pose = pose_map.get(track.track_id)
                if pose is None:
                    continue
                hip = self.hip_midpoint(pose)
                if hip is None:
                    continue
                track_hip_x.setdefault(track.track_id, []).append((frame_i, hip[0]))

        results: list[TestResult] = []

        for track_id, hip_series in track_hip_x.items():
            attempts = []
            crossed_start = None

            for i, (frame_i, hip_x) in enumerate(hip_series):
                if crossed_start is None and hip_x >= start_line_x_px:
                    crossed_start = (frame_i, hip_x)
                elif crossed_start is not None and hip_x >= finish_line_x_px:
                    # Sub-frame interpolation
                    if i > 0:
                        prev_x = hip_series[i - 1][1]
                        t_interp = (finish_line_x_px - prev_x) / (hip_x - prev_x + 1e-9)
                        finish_time = (frame_i - 1 + t_interp) / fps
                    else:
                        finish_time = frame_i / fps
                    start_time = crossed_start[0] / fps
                    sprint_time = finish_time - start_time
                    if sprint_time > 0:
                        attempts.append(sprint_time)
                    crossed_start = None  # reset for next attempt

            bib = None
            for frame_tracks_inner in tracks:
                for t in frame_tracks_inner:
                    if t.track_id == track_id and t.bib_number is not None:
                        bib = t.bib_number
                        break
                if bib:
                    break

            flags = [] if bib else ["bib_unresolved"]

            for attempt_num, val in enumerate(attempts[:num_attempts], 1):
                results.append(
                    TestResult(
                        student_bib=bib or -1,
                        track_id=track_id,
                        test_type="speed",
                        metric_value=round(val, 3),
                        metric_unit="s",
                        attempt_number=attempt_num,
                        confidence_score=0.8 if bib else 0.4,
                        flags=flags,
                        raw_data={"sprint_distance_m": sprint_distance_m},
                    )
                )
        return results

"""
Agility (T-Drill) Metric Extractor

Algorithm:
    1. Map cone positions to T-drill pattern via homography
    2. Detect start: student hip leaves start zone (within 50 cm of start cone)
    3. Detect finish: student hip returns to start zone
    4. Timer = (finish_frame - start_frame) / fps
    5. Optional: validate cone touch sequence (proximity events)

Exploration surface:
    - Cone proximity threshold for touch validation (default 80 cm)
    - Start/finish zone size
"""
from __future__ import annotations

import logging

import numpy as np

from pipeline.models import Pose, TestResult, Track
from pipeline.tests.base import BaseMetricExtractor

logger = logging.getLogger(__name__)


class AgilityExtractor(BaseMetricExtractor):

    def validate_inputs(self, tracks, poses, frames) -> bool:
        if not self.calibration.is_valid:
            logger.warning("Invalid calibration for agility extraction.")
            return False
        return True

    def extract(
        self,
        tracks: list[list[Track]],
        poses: list[list[Pose]],
        frames: list[np.ndarray],
    ) -> list[TestResult]:
        if not self.validate_inputs(tracks, poses, frames):
            return []

        import cv2

        fps = self.config.get("fps", 15)
        num_attempts = self.config.get("num_attempts", 3)
        start_zone_cm = self.config.get("start_zone_cm", 50)
        cone_touch_threshold_cm = self.config.get("cone_touch_threshold_cm", 80)
        # Expected T-drill cone world positions [[x,y], ...]
        cone_positions_m = self.config.get("cone_positions_m", [[0, 0], [5, 0], [5, -3], [5, 3]])
        cone_positions_cm = [(x * 100, y * 100) for x, y in cone_positions_m]
        start_cone_cm = cone_positions_cm[0]

        H = self.calibration.homography_matrix

        # Build per-track world (X, Y) time series
        track_world_xy: dict[int, list[tuple[float, float, float]]] = {}  # → [(t, x, y)]
        for frame_i, (frame_tracks, frame_poses) in enumerate(zip(tracks, poses)):
            pose_map = self.build_track_pose_map(frame_tracks, frame_poses)
            for track in frame_tracks:
                pose = pose_map.get(track.track_id)
                if pose is None:
                    continue
                hip = self.hip_midpoint(pose)
                if hip is None:
                    continue
                pt = np.array([[hip]], dtype=np.float32)
                world_pt = cv2.perspectiveTransform(pt, H)[0][0]
                track_world_xy.setdefault(track.track_id, []).append(
                    (frame_i / fps, float(world_pt[0]), float(world_pt[1]))
                )

        results: list[TestResult] = []

        for track_id, world_series in track_world_xy.items():
            attempts_times = []
            in_drill = False
            drill_start_t = None

            for t, wx, wy in world_series:
                dist_to_start = np.hypot(wx - start_cone_cm[0], wy - start_cone_cm[1])

                if not in_drill and dist_to_start < start_zone_cm:
                    pass  # waiting at start
                elif not in_drill and dist_to_start >= start_zone_cm:
                    in_drill = True
                    drill_start_t = t
                elif in_drill and dist_to_start < start_zone_cm:
                    drill_time = t - (drill_start_t or t)
                    if drill_time > 1.0:  # filter spurious sub-1s events
                        attempts_times.append(drill_time)
                    in_drill = False
                    drill_start_t = None

            bib = None
            for ft in tracks:
                for t_obj in ft:
                    if t_obj.track_id == track_id and t_obj.bib_number:
                        bib = t_obj.bib_number
                        break
                if bib:
                    break

            flags = [] if bib else ["bib_unresolved"]
            for attempt_num, val in enumerate(attempts_times[:num_attempts], 1):
                results.append(
                    TestResult(
                        student_bib=bib or -1,
                        track_id=track_id,
                        test_type="agility",
                        metric_value=round(val, 2),
                        metric_unit="s",
                        attempt_number=attempt_num,
                        confidence_score=0.75 if bib else 0.4,
                        flags=flags,
                        raw_data={"cone_positions_cm": cone_positions_cm},
                    )
                )
        return results

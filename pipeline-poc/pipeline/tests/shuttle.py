"""
Fitness (Shuttle Run) Metric Extractor

Algorithm:
    1. Map 6 cone positions to world X [0, 200, 400, 600, 800, 1000] cm
    2. Per 15-second set: track student world X across frames
    3. Detect direction reversals: velocity sign change near a cone
    4. Count complete shuttles; add partial distance at set end
    5. Sum 3 sets per student

Exploration surface:
    - Velocity sign change vs cone proximity as reversal trigger
    - Require sign change to persist ≥ 3 frames to suppress noise
"""
from __future__ import annotations

import logging

import numpy as np

from pipeline.models import Pose, TestResult, Track
from pipeline.tests.base import BaseMetricExtractor

logger = logging.getLogger(__name__)

CONE_WORLD_X_CM = [0, 200, 400, 600, 800, 1000]  # standard shuttle layout


class ShuttleExtractor(BaseMetricExtractor):

    def validate_inputs(self, tracks, poses, frames) -> bool:
        if not self.calibration.is_valid:
            logger.warning("Invalid calibration.")
            return False
        return True

    def _get_pixel_to_world_matrix(self) -> np.ndarray | None:
        """Return 3×3 matrix for pixel→world (cm). Homography if available, else scale from single_axis."""
        H = self.calibration.homography_matrix
        if H is not None:
            return H
        px_cm = self.calibration.pixels_per_cm
        if px_cm is not None and px_cm > 0:
            s = 1.0 / px_cm
            return np.array([[s, 0, 0], [0, s, 0], [0, 0, 1]], dtype=np.float32)
        return None

    def extract(
        self,
        tracks: list[list[Track]],
        poses: list[list[Pose]],
        frames: list[np.ndarray],
    ) -> list[TestResult]:
        if not self.validate_inputs(tracks, poses, frames):
            return []

        fps = self.config.get("fps", 15)
        set_duration_s = self.config.get("set_duration_s", 15)
        num_sets = self.config.get("num_sets", 3)
        rest_between_sets_s = self.config.get("rest_between_sets_s", 30)
        reversal_proximity_cm = self.config.get("reversal_proximity_cm", 30)
        H = self._get_pixel_to_world_matrix()
        if H is None:
            logger.warning(
                "Shuttle extractor requires homography or single_axis calibration with pixels_per_cm. "
                "Skipping extraction."
            )
            return []

        import cv2

        # Build per-track world X time series
        track_world_x: dict[int, list[tuple[float, float]]] = {}  # track_id → [(time_s, world_x)]
        for frame_i, (frame_tracks, frame_poses) in enumerate(zip(tracks, poses)):
            pose_map = self.build_track_pose_map(frame_tracks, frame_poses)
            for track in frame_tracks:
                pose = pose_map.get(track.track_id)
                if pose is None:
                    continue
                hip = self.hip_midpoint(pose)
                if hip is None:
                    continue
                # Transform pixel hip to world X
                pt = np.array([[hip]], dtype=np.float32)
                world_pt = cv2.perspectiveTransform(pt, H)[0][0]
                world_x = float(world_pt[0])
                time_s = frame_i / fps
                track_world_x.setdefault(track.track_id, []).append((time_s, world_x))

        results: list[TestResult] = []

        for track_id, world_series in track_world_x.items():
            set_distances: list[float] = []

            for set_num in range(num_sets):
                t_start = set_num * (set_duration_s + rest_between_sets_s)
                t_end = t_start + set_duration_s
                set_data = [(t, x) for t, x in world_series if t_start <= t <= t_end]
                if len(set_data) < 2:
                    set_distances.append(0.0)
                    continue

                xs = np.array([x for _, x in set_data])
                # Cone-proximity reversal detection
                distance_cm = 0.0
                prev_x = xs[0]
                direction = 1  # +1 = moving right
                for curr_x in xs[1:]:
                    step = curr_x - prev_x
                    # Detect reversal: near a cone and direction changed
                    near_cone = any(abs(curr_x - cx) < reversal_proximity_cm for cx in CONE_WORLD_X_CM)
                    if near_cone and np.sign(step) != direction:
                        direction = int(np.sign(step)) if step != 0 else direction
                    distance_cm += abs(step)
                    prev_x = curr_x

                set_distances.append(distance_cm / 100.0)  # convert to metres

            total_distance_m = sum(set_distances)

            bib = None
            for ft in tracks:
                for t in ft:
                    if t.track_id == track_id and t.bib_number:
                        bib = t.bib_number
                        break
                if bib:
                    break

            flags = [] if bib else ["bib_unresolved"]
            results.append(
                TestResult(
                    student_bib=bib or -1,
                    track_id=track_id,
                    test_type="fitness",
                    metric_value=round(total_distance_m, 1),
                    metric_unit="m",
                    attempt_number=1,
                    confidence_score=0.75 if bib else 0.4,
                    flags=flags,
                    raw_data={"set_distances_m": set_distances},
                )
            )
        return results

"""
Explosiveness (Vertical Jump) Metric Extractor

Algorithm:
    1. Establish standing baseline: median ankle Y across first 30 frames
    2. Jump detection: ankle Y drops below baseline - jump_threshold_px
    3. Apex detection: minimum ankle Y within detected jump phase
    4. Height (px) → cm via single-axis calibration
    5. Return best-of-N attempts

Exploration surface:
    - Ankle midpoint vs lower ankle as floor contact reference
    - Knee-bend false baseline detection
    - Sequential jump handling (student jumps twice without full return)
"""
from __future__ import annotations

import logging

import numpy as np

from pipeline.models import CalibrationResult, Pose, TestResult, Track
from pipeline.tests.base import BaseMetricExtractor

logger = logging.getLogger(__name__)

# Default geometry config (overridden by configs/test_configs/explosiveness.json)
DEFAULT_CONFIG = {
    "test_type": "explosiveness",
    "camera_height_m": 2.0,
    "camera_distance_m": 5.0,
    "reference_height_cm": 23.0,
    "num_attempts": 3,
    "jump_min_height_cm": 5.0,
    "jump_threshold_px": 15,
    "baseline_frames": 30,
}


class ExplosivenessExtractor(BaseMetricExtractor):

    def validate_inputs(self, tracks, poses, frames) -> bool:
        if len(frames) < DEFAULT_CONFIG["baseline_frames"]:
            logger.warning("Too few frames for baseline estimation.")
            return False
        if not any(poses):
            logger.warning("No pose data available.")
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

        fps = self.config.get("fps", 15)
        jump_threshold_px = self.config.get("jump_threshold_px", DEFAULT_CONFIG["jump_threshold_px"])
        baseline_frames = self.config.get("baseline_frames", DEFAULT_CONFIG["baseline_frames"])
        num_attempts = self.config.get("num_attempts", DEFAULT_CONFIG["num_attempts"])
        pixels_per_cm = self.calibration.pixels_per_cm

        # Build per-track ankle Y time series
        track_ankle_y: dict[int, list[tuple[int, float]]] = {}  # track_id → [(frame_idx, y)]
        for frame_i, (frame_tracks, frame_poses) in enumerate(zip(tracks, poses)):
            pose_map = self.build_track_pose_map(frame_tracks, frame_poses)
            for track in frame_tracks:
                if track.track_id not in track_ankle_y:
                    track_ankle_y[track.track_id] = []
                pose = pose_map.get(track.track_id)
                if pose is None:
                    continue
                l_ankle, r_ankle = self.ankle_positions(pose)
                if l_ankle and r_ankle:
                    # Use lower ankle (higher pixel Y value) as floor contact
                    ankle_y = max(l_ankle[1], r_ankle[1])
                elif l_ankle:
                    ankle_y = l_ankle[1]
                elif r_ankle:
                    ankle_y = r_ankle[1]
                else:
                    continue
                track_ankle_y[track.track_id].append((frame_i, ankle_y))

        results: list[TestResult] = []

        for track_id, ankle_series in track_ankle_y.items():
            if len(ankle_series) < baseline_frames:
                continue

            ys = np.array([y for _, y in ankle_series])
            frame_idxs = [f for f, _ in ankle_series]

            # Baseline: median ankle Y in first N frames (standing position)
            baseline_y = float(np.median(ys[:baseline_frames]))

            # Detect jump events: ankle Y rises above floor (lower pixel Y)
            jump_threshold = baseline_y - jump_threshold_px
            attempts = []
            in_jump = False
            jump_start = None
            apex_y = None

            for i, (frame_i, y) in enumerate(ankle_series):
                if not in_jump and y < jump_threshold:
                    in_jump = True
                    jump_start = i
                    apex_y = y
                elif in_jump:
                    if y < apex_y:
                        apex_y = y
                    if y >= baseline_y - 5:  # returned to floor
                        height_px = baseline_y - apex_y
                        height_cm = height_px / pixels_per_cm if pixels_per_cm else 0.0
                        if height_cm >= self.config.get("jump_min_height_cm", 5.0):
                            attempts.append(height_cm)
                        in_jump = False
                        apex_y = None

            # Resolve bib for this track (use majority from first frame that has it)
            bib = None
            for frame_tracks in tracks:
                for t in frame_tracks:
                    if t.track_id == track_id and t.bib_number is not None:
                        bib = t.bib_number
                        break
                if bib is not None:
                    break

            flags = []
            if bib is None:
                flags.append("bib_unresolved")

            best_attempt = max(attempts) if attempts else 0.0
            for attempt_num, val in enumerate(attempts[:num_attempts], 1):
                results.append(
                    TestResult(
                        student_bib=bib or -1,
                        track_id=track_id,
                        test_type="explosiveness",
                        metric_value=round(val, 1),
                        metric_unit="cm",
                        attempt_number=attempt_num,
                        confidence_score=0.8 if bib else 0.4,
                        flags=flags,
                        raw_data={"baseline_y_px": baseline_y, "all_attempts_cm": attempts},
                    )
                )

        return results

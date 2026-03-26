"""
Balance Metric Extractor

Algorithm:
    1. Detect bilateral stance: both ankles near floor (Y within 5px of baseline)
    2. Balance start: one ankle rises above floor threshold (lifted foot)
    3. State machine: BILATERAL → BALANCING → FAILED
    4. Duration = frames_in_BALANCING / fps
    5. Torso lean: angle between nose and hip midpoint vs vertical

Exploration surface:
    - Lean threshold (10°–20°) vs manual ground truth
    - Hip keypoints alone vs nose for torso lean
    - Ankle lift threshold (px) calibration
"""
from __future__ import annotations

import logging

import numpy as np

from pipeline.models import Pose, TestResult, Track
from pipeline.tests.base import BaseMetricExtractor

logger = logging.getLogger(__name__)

# States
BILATERAL = "BILATERAL"
BALANCING = "BALANCING"
FAILED = "FAILED"


class BalanceExtractor(BaseMetricExtractor):

    def validate_inputs(self, tracks, poses, frames) -> bool:
        if len(frames) < 10:
            logger.warning("Too few frames for balance extraction.")
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
        lean_threshold_deg = self.config.get("lean_threshold_deg", 15)
        ankle_lift_threshold_px = self.config.get("ankle_lift_threshold_px", 20)
        baseline_frames = self.config.get("baseline_frames", 30)
        max_duration_s = self.config.get("max_duration_s", 60)

        # Build per-track ankle and nose/hip time series
        track_data: dict[int, list[dict]] = {}
        for frame_i, (frame_tracks, frame_poses) in enumerate(zip(tracks, poses)):
            pose_map = self.build_track_pose_map(frame_tracks, frame_poses)
            for track in frame_tracks:
                pose = pose_map.get(track.track_id)
                if pose is None:
                    continue
                kps = pose.keypoints
                entry = {
                    "frame_i": frame_i,
                    "l_ankle_y": kps[15, 1] if kps[15, 2] > 0.3 else None,
                    "r_ankle_y": kps[16, 1] if kps[16, 2] > 0.3 else None,
                    "nose_y": kps[0, 1] if kps[0, 2] > 0.3 else None,
                    "nose_x": kps[0, 0] if kps[0, 2] > 0.3 else None,
                    "hip_x": (kps[11, 0] + kps[12, 0]) / 2 if kps[11, 2] > 0.3 and kps[12, 2] > 0.3 else None,
                    "hip_y": (kps[11, 1] + kps[12, 1]) / 2 if kps[11, 2] > 0.3 and kps[12, 2] > 0.3 else None,
                }
                track_data.setdefault(track.track_id, []).append(entry)

        results: list[TestResult] = []

        for track_id, series in track_data.items():
            if len(series) < baseline_frames:
                continue

            # Baseline: median ankle Y in first N frames
            baseline_l = np.nanmedian([d["l_ankle_y"] for d in series[:baseline_frames] if d["l_ankle_y"]])
            baseline_r = np.nanmedian([d["r_ankle_y"] for d in series[:baseline_frames] if d["r_ankle_y"]])

            state = BILATERAL
            balance_start_frame = None
            balance_durations = []

            for d in series:
                frame_i = d["frame_i"]

                l_lifted = d["l_ankle_y"] is not None and d["l_ankle_y"] < baseline_l - ankle_lift_threshold_px
                r_lifted = d["r_ankle_y"] is not None and d["r_ankle_y"] < baseline_r - ankle_lift_threshold_px

                # Torso lean check
                lean_exceeded = False
                if d["nose_x"] and d["nose_y"] and d["hip_x"] and d["hip_y"]:
                    dx = d["nose_x"] - d["hip_x"]
                    dy = d["hip_y"] - d["nose_y"]  # positive upward in image space
                    lean_angle = abs(np.degrees(np.arctan2(abs(dx), max(dy, 1))))
                    lean_exceeded = lean_angle > lean_threshold_deg

                if state == BILATERAL:
                    if l_lifted or r_lifted:
                        state = BALANCING
                        balance_start_frame = frame_i

                elif state == BALANCING:
                    if lean_exceeded or (not l_lifted and not r_lifted):
                        duration_s = (frame_i - balance_start_frame) / fps
                        if duration_s > 0.1:
                            balance_durations.append(duration_s)
                        state = BILATERAL
                        balance_start_frame = None

            # Handle clip end while still balancing
            if state == BALANCING and balance_start_frame is not None:
                duration_s = (len(series) - balance_start_frame) / fps
                if duration_s > 0.1:
                    balance_durations.append(duration_s)

            bib = None
            for ft in tracks:
                for t_obj in ft:
                    if t_obj.track_id == track_id and t_obj.bib_number:
                        bib = t_obj.bib_number
                        break
                if bib:
                    break

            flags = [] if bib else ["bib_unresolved"]
            best_balance = max(balance_durations) if balance_durations else 0.0

            results.append(
                TestResult(
                    student_bib=bib or -1,
                    track_id=track_id,
                    test_type="balance",
                    metric_value=round(best_balance, 2),
                    metric_unit="s",
                    attempt_number=1,
                    confidence_score=0.8 if bib else 0.4,
                    flags=flags,
                    raw_data={
                        "all_balance_durations_s": balance_durations,
                        "lean_threshold_deg": lean_threshold_deg,
                        "ankle_lift_threshold_px": ankle_lift_threshold_px,
                    },
                )
            )
        return results

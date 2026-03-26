"""
Module 7 — Output: JSON results + annotated video
Writes TestResult list to JSON and renders annotated overlay video.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np

from pipeline.models import Pose, TestResult, Track

logger = logging.getLogger(__name__)


def write_results_json(results: list[TestResult], output_path: str | Path) -> None:
    """Serialise TestResult list to JSON."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [asdict(r) for r in results]
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    logger.info("Results written to %s (%d records)", output_path, len(results))


class AnnotatedVideoWriter:
    """
    Renders bounding boxes, track IDs, bib numbers, and pose keypoints
    onto frames and writes an output .mp4 clip.
    """

    KEYPOINT_PAIRS = [
        (5, 6),   # shoulders
        (5, 7), (7, 9),   # left arm
        (6, 8), (8, 10),  # right arm
        (11, 12),          # hips
        (5, 11), (6, 12), # torso
        (11, 13), (13, 15),  # left leg
        (12, 14), (14, 16),  # right leg
    ]

    def __init__(self, output_path: str | Path, fps: int = 15, frame_size: tuple = (1920, 1080)):
        self.output_path = str(output_path)
        self.fps = fps
        self.frame_size = frame_size
        self._writer: cv2.VideoWriter | None = None

    def open(self):
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self._writer = cv2.VideoWriter(self.output_path, fourcc, self.fps, self.frame_size)
        logger.info("AnnotatedVideoWriter opened: %s", self.output_path)

    def write_frame(
        self,
        frame: np.ndarray,
        tracks: list[Track],
        poses: list[Pose] | None = None,
    ) -> None:
        canvas = frame.copy()
        pose_map = {p.track_id: p for p in (poses or [])}

        for track in tracks:
            x1, y1, x2, y2 = map(int, track.bbox)
            colour = (0, 255, 0) if track.is_confirmed else (0, 165, 255)
            cv2.rectangle(canvas, (x1, y1), (x2, y2), colour, 2)

            label = f"ID:{track.track_id}"
            if track.bib_number is not None:
                label += f" Bib:{track.bib_number}"
            cv2.putText(canvas, label, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, colour, 2)

            if track.track_id in pose_map:
                kps = pose_map[track.track_id].keypoints
                for i in range(17):
                    if kps[i, 2] > 0.3:
                        cv2.circle(canvas, (int(kps[i, 0]), int(kps[i, 1])), 4, (0, 0, 255), -1)
                for a, b in self.KEYPOINT_PAIRS:
                    if kps[a, 2] > 0.3 and kps[b, 2] > 0.3:
                        cv2.line(
                            canvas,
                            (int(kps[a, 0]), int(kps[a, 1])),
                            (int(kps[b, 0]), int(kps[b, 1])),
                            (255, 0, 0), 2,
                        )

        if self._writer:
            self._writer.write(canvas)

    def close(self):
        if self._writer:
            self._writer.release()
            logger.info("AnnotatedVideoWriter closed: %s", self.output_path)

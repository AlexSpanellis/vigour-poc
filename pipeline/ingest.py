"""
Module 1 — Video Ingestion
Interface: extract_frames(video_path, target_fps) → Generator[(frame_idx, frame, timestamp_s)]

Recommended approach: OpenCV VideoCapture with stride-based sampling.
Alternatives to explore: ffmpeg subprocess pipe, PyAV, vidstab stabilisation.
See: notebooks/01_detection_eval.ipynb (shares clip samples with detection eval)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Generator

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

def extract_frames(
    video_path: str | Path,
    target_fps: int = 15,
    stabilize: bool = False,
) -> Generator[tuple[int, np.ndarray, float], None, None]:
    """
    Yield (frame_index, BGR frame, timestamp_seconds) at target_fps.

    Args:
        video_path: Path to .mp4 / .mov clip.
        target_fps:  Desired output frame rate. Original frames are sub-sampled.
        stabilize:   Apply video stabilisation (vidstab). Adds ~15% compute.

    Yields:
        (frame_idx, frame_bgr, timestamp_s)

    Evaluation criteria:
        - Correct frame count for 3 sample clips
        - Timestamps within 10 ms accuracy vs ffprobe
        - No dropped frames for clips up to 5 minutes
        - Handles iPhone .mov and Android .mp4 codec variants
    """
    video_path = str(video_path)
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")

    original_fps = cap.get(cv2.CAP_PROP_FPS)
    if original_fps <= 0:
        logger.warning("Could not read FPS from video metadata; defaulting to 30.")
        original_fps = 30.0

    stride = max(1, round(original_fps / target_fps))
    logger.info(
        "Ingesting %s | source FPS=%.1f | target FPS=%d | stride=%d",
        video_path, original_fps, target_fps, stride,
    )

    if stabilize:
        # TODO (exploration): integrate vidstab here
        # from vidstab import VidStab
        # stabilizer = VidStab()
        logger.warning("stabilize=True requested but not yet implemented. Skipping.")

    frame_idx = 0
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_idx % stride == 0:
                timestamp_s = frame_idx / original_fps
                yield (frame_idx, frame, timestamp_s)
            frame_idx += 1
    finally:
        cap.release()


# ---------------------------------------------------------------------------
# Alternative: ffmpeg subprocess pipe (explore if OpenCV has codec issues)
# ---------------------------------------------------------------------------

def extract_frames_ffmpeg(
    video_path: str | Path,
    target_fps: int = 15,
) -> Generator[tuple[int, np.ndarray, float], None, None]:
    """
    Alternative ingestion via ffmpeg pipe — more reliable for exotic codecs.
    NOT the default; use extract_frames() unless OpenCV fails.

    Decision log:
        Date | Approach Tried | Result | Decision
        ——   | ——             | ——     | ——
    """
    raise NotImplementedError(
        "ffmpeg pipe ingestion not yet implemented. "
        "Implement and benchmark against extract_frames() in notebooks."
    )

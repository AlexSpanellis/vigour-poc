"""
Global interface contracts — shared data structures for the Vigour pipeline.
All modules must use these dataclasses as input/output types.
Do NOT change field names or types without a team decision.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np


@dataclass
class Detection:
    """Output of the person detection stage (Module 2)."""
    bbox: tuple[float, float, float, float]  # x1, y1, x2, y2 (pixel)
    confidence: float                         # 0.0–1.0
    class_id: int                             # 0 = person
    frame_idx: int


@dataclass
class Track:
    """Output of the multi-person tracking stage (Module 3)."""
    track_id: int
    bbox: tuple[float, float, float, float]  # x1, y1, x2, y2
    frame_idx: int
    is_confirmed: bool
    bib_number: int | None = None            # None until OCR resolved
    bib_confidence: float = 0.0              # 0.0–1.0


@dataclass
class Pose:
    """
    Output of the pose estimation stage (Module 4).
    COCO keypoint order:
      0=nose, 1=l_eye, 2=r_eye, 3=l_ear, 4=r_ear,
      5=l_shoulder, 6=r_shoulder, 7=l_elbow, 8=r_elbow,
      9=l_wrist, 10=r_wrist, 11=l_hip, 12=r_hip,
      13=l_knee, 14=r_knee, 15=l_ankle, 16=r_ankle
    """
    track_id: int
    frame_idx: int
    keypoints: np.ndarray        # shape (17, 3) — x, y, confidence per keypoint
    pose_confidence: float       # mean keypoint confidence


@dataclass
class CalibrationResult:
    """Output of the cone detection & calibration stage (Module 6)."""
    method: Literal["homography", "single_axis"]
    homography_matrix: np.ndarray | None     # 3×3, None if single_axis
    pixels_per_cm: float | None              # None if homography
    cone_positions_px: list[tuple]           # detected cone centres in pixels
    cone_positions_world: list[tuple]        # corresponding world coords (cm)
    reprojection_error_cm: float             # mean reprojection error in world (cm) units
    is_valid: bool
    condition_number: float | None = None    # H condition number; high (>500) → ill-conditioned


@dataclass
class TestResult:
    """Final output of a test-specific metric extractor."""
    student_bib: int
    track_id: int
    test_type: str
    metric_value: float
    metric_unit: str
    attempt_number: int
    confidence_score: float              # 0.0–1.0, pipeline confidence in this result
    flags: list[str] = field(default_factory=list)  # e.g. ["bib_unresolved", "low_pose_confidence"]
    raw_data: dict = field(default_factory=dict)    # test-specific intermediates for debugging

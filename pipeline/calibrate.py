"""
Module 6 — Cone Detection & Camera Calibration
Interface: Calibrator.calibrate_homography / calibrate_single_axis → CalibrationResult

Recommended approach: HSV segmentation → contour centroids → cv2.findHomography.
Alternatives: Fine-tuned YOLO for cones, ArUco markers, floor court lines.
See: notebooks/05_calibration_eval.ipynb

HSV Ranges (March 2026 school hall footage — re-tune on first frame of each clip):
    Yellow:     H 18–35,   S 80–255,  V 80–255   (primary lane markers)
    Orange/Red: H 5–18,    S 100–255, V 100–255  (mid-lane agility markers)
    Blue:       H 100–130, S 80–255,  V 50–255   (far-end depth reference)
    Red:        H 0–5 or 170–180, S 100–255, V 100–255 (grid markers)

Decision log:
    Date | Approach | Reprojection Error | Detection Rate | Verdict
    ——   | ——       | ——                 | ——             | ——
"""
from __future__ import annotations

import logging
from typing import Literal

import cv2
import numpy as np

from pipeline.models import CalibrationResult

logger = logging.getLogger(__name__)

# Default HSV ranges — re-tune per lighting condition
HSV_RANGES = {
    "yellow": ((18, 80, 80), (35, 255, 255)),
    "orange": ((5, 100, 100), (18, 255, 255)),
    "blue":   ((100, 80, 50), (130, 255, 255)),
    "red_lo": ((0, 100, 100), (5, 255, 255)),
    "red_hi": ((170, 100, 100), (180, 255, 255)),
}

# Minimum contour area to treat as a cone (filters noise)
MIN_CONE_AREA = 100


class Calibrator:
    """
    Detects cones via HSV segmentation and computes pixel↔world mapping.

    Evaluation criteria:
        - All cones detected in ≥ 95% of frames from March 2026 footage
        - Homography reprojection error < 3 px
        - Known 5m cone separation reproduced within ±5 cm
        - Robust across all 6 clips from March 2026 footage
    """

    def __init__(self, hsv_ranges: dict | None = None, min_cone_area: int = MIN_CONE_AREA):
        self.hsv_ranges = hsv_ranges or HSV_RANGES
        self.min_cone_area = min_cone_area

    # ------------------------------------------------------------------
    # Cone detection
    # ------------------------------------------------------------------

    def detect_cones(
        self,
        frame: np.ndarray,
        colour: str = "yellow",
    ) -> list[tuple[float, float]]:
        """
        Detect cone centres via HSV mask + contour centroids.

        Args:
            frame:  BGR frame.
            colour: One of 'yellow', 'orange', 'blue', 'red_lo', 'red_hi'.

        Returns:
            List of (cx, cy) pixel centres for detected cones.
        """
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        if colour not in self.hsv_ranges:
            raise ValueError(f"Unknown cone colour '{colour}'. Add to HSV_RANGES.")

        lo, hi = self.hsv_ranges[colour]
        mask = cv2.inRange(hsv, np.array(lo), np.array(hi))

        # Morphological cleanup
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_DILATE, kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        centres: list[tuple[float, float]] = []
        for c in contours:
            if cv2.contourArea(c) < self.min_cone_area:
                continue
            M = cv2.moments(c)
            if M["m00"] > 0:
                cx = M["m10"] / M["m00"]
                cy = M["m01"] / M["m00"]
                centres.append((cx, cy))

        logger.debug("Detected %d %s cone(s).", len(centres), colour)
        return centres

    # ------------------------------------------------------------------
    # Homography calibration
    # ------------------------------------------------------------------

    def calibrate_homography(
        self,
        frame: np.ndarray,
        known_world_coords_cm: list[tuple[float, float]],
        cone_colour: str = "yellow",
    ) -> CalibrationResult:
        """
        Compute 3×3 homography mapping pixel space → world floor plane (cm).

        Requires ≥ 4 corresponding cone points.
        HSV range must be tuned to this clip before calling.

        Args:
            frame:                  BGR frame (typically first frame of clip).
            known_world_coords_cm:  List of (x_cm, y_cm) for each cone in real space.
            cone_colour:            Colour key in HSV_RANGES.

        Returns:
            CalibrationResult (method='homography').
        """
        cone_px = self.detect_cones(frame, colour=cone_colour)

        if len(cone_px) < 4:
            logger.warning(
                "Only %d cones detected; need ≥ 4 for homography. "
                "Try tuning HSV ranges. Returning invalid CalibrationResult.",
                len(cone_px),
            )
            return CalibrationResult(
                method="homography",
                homography_matrix=None,
                pixels_per_cm=None,
                cone_positions_px=cone_px,
                cone_positions_world=known_world_coords_cm,
                reprojection_error_px=float("inf"),
                is_valid=False,
            )

        if len(cone_px) != len(known_world_coords_cm):
            raise ValueError(
                f"Detected {len(cone_px)} cones but {len(known_world_coords_cm)} "
                "world coords provided. Ensure manual world coords match detected count "
                "or sort cone_px to match expected layout."
            )

        src_pts = np.array(cone_px, dtype=np.float32)
        dst_pts = np.array(known_world_coords_cm, dtype=np.float32)

        H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)

        # Compute reprojection error
        projected = cv2.perspectiveTransform(src_pts.reshape(-1, 1, 2), H).reshape(-1, 2)
        errors = np.linalg.norm(projected - dst_pts, axis=1)
        reprojection_error = float(errors.mean())

        logger.info(
            "Homography calibrated. Reprojection error: %.2f px", reprojection_error
        )

        return CalibrationResult(
            method="homography",
            homography_matrix=H,
            pixels_per_cm=None,
            cone_positions_px=list(map(tuple, src_pts.tolist())),
            cone_positions_world=known_world_coords_cm,
            reprojection_error_px=reprojection_error,
            is_valid=reprojection_error < 3.0,
        )

    # ------------------------------------------------------------------
    # Single-axis calibration (jump / balance tests)
    # ------------------------------------------------------------------

    def calibrate_single_axis(
        self,
        frame: np.ndarray,
        reference_height_cm: float = 23.0,
        cone_colour: str = "yellow",
    ) -> CalibrationResult:
        """
        Compute pixels-per-cm from a reference object of known height.
        Used for vertical jump and balance tests where only Y-axis scale matters.

        Args:
            frame:               BGR frame.
            reference_height_cm: Known physical height of reference object (cm).
            cone_colour:         Colour key in HSV_RANGES (cone as reference).

        Returns:
            CalibrationResult (method='single_axis').
        """
        cone_px = self.detect_cones(frame, colour=cone_colour)
        if len(cone_px) < 2:
            logger.warning(
                "Need ≥ 2 cone detections for single-axis calibration. Got %d.",
                len(cone_px),
            )
            return CalibrationResult(
                method="single_axis",
                homography_matrix=None,
                pixels_per_cm=None,
                cone_positions_px=cone_px,
                cone_positions_world=[],
                reprojection_error_px=float("inf"),
                is_valid=False,
            )

        # Use vertical spread of detected cones as reference
        ys = [p[1] for p in cone_px]
        height_px = max(ys) - min(ys)
        pixels_per_cm = height_px / reference_height_cm if reference_height_cm > 0 else None

        logger.info(
            "Single-axis calibration: %.2f px/cm (ref=%.1f cm, height_px=%.1f)",
            pixels_per_cm, reference_height_cm, height_px,
        )

        return CalibrationResult(
            method="single_axis",
            homography_matrix=None,
            pixels_per_cm=pixels_per_cm,
            cone_positions_px=cone_px,
            cone_positions_world=[],
            reprojection_error_px=0.0,
            is_valid=pixels_per_cm is not None and pixels_per_cm > 0,
        )

    # ------------------------------------------------------------------
    # Coordinate transform
    # ------------------------------------------------------------------

    def pixel_to_world(
        self, point_px: tuple[float, float], calibration: CalibrationResult
    ) -> tuple[float, float]:
        """
        Convert pixel coordinates to world coordinates using calibration result.

        Args:
            point_px:    (x, y) in pixel space.
            calibration: CalibrationResult from calibrate_homography or single_axis.

        Returns:
            (x_cm, y_cm) in world space.
        """
        if not calibration.is_valid:
            raise ValueError("Cannot transform with invalid calibration.")

        if calibration.method == "homography":
            pt = np.array([[point_px]], dtype=np.float32)
            world = cv2.perspectiveTransform(pt, calibration.homography_matrix)
            return float(world[0][0][0]), float(world[0][0][1])

        if calibration.method == "single_axis":
            if calibration.pixels_per_cm is None:
                raise ValueError("pixels_per_cm is None in single_axis calibration.")
            return point_px[0] / calibration.pixels_per_cm, point_px[1] / calibration.pixels_per_cm

        raise ValueError(f"Unknown calibration method: {calibration.method}")

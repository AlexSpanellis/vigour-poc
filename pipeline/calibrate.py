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
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import cv2
import numpy as np

from pipeline.cone_layout import (
    generate_cone_world_coords,
    generate_cone_world_coords_from_pixels,
)
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


@dataclass
class ConeDetection:
    """Internal cone representation with colour label metadata."""
    cx: float
    cy: float
    colour_label: str
    score: float
    bbox: tuple[float, float, float, float] | None = None


class Calibrator:
    """
    Detects cones via HSV segmentation and computes pixel↔world mapping.

    Evaluation criteria:
        - All cones detected in ≥ 95% of frames from March 2026 footage
        - Homography reprojection error < 3 px
        - Known 5m cone separation reproduced within ±5 cm
        - Robust across all 6 clips from March 2026 footage
    """

    def __init__(
        self,
        hsv_ranges: dict | None = None,
        min_cone_area: int = MIN_CONE_AREA,
        detector_backend: Literal["hsv", "sam3_prompt"] = "hsv",
        sam_model_path: str = "sam3.pt",
        sam_prompt: str = "training cone",
        min_confidence: float = 0.5,
    ):
        self.hsv_ranges = hsv_ranges or HSV_RANGES
        self.min_cone_area = min_cone_area
        self.detector_backend = detector_backend
        self.sam_model_path = sam_model_path
        self.sam_prompt = sam_prompt
        self.min_confidence = min_confidence
        self._sam_predictor = None
        self._sam_force_cpu = False  # Set when CUDA fails at runtime
        self.last_detected_cones: list[ConeDetection] = []

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
            List of (cx, cy) pixel centres for detected cones (score >= min_confidence).
        """
        cone_objects = self._detect_cone_objects(frame, colour=colour)
        cone_objects = [c for c in cone_objects if c.score >= self.min_confidence]
        self.last_detected_cones = cone_objects
        centres = [(c.cx, c.cy) for c in cone_objects]
        logger.debug("Detected %d cone(s) via %s backend (min_confidence=%.2f).", len(centres), self.detector_backend, self.min_confidence)
        return centres

    def _detect_cone_objects(self, frame: np.ndarray, colour: str = "yellow") -> list[ConeDetection]:
        if self.detector_backend == "sam3_prompt":
            return self._detect_cones_sam3_prompt(frame)
        return self._detect_cones_hsv(frame, colour)

    def _detect_cones_hsv(self, frame: np.ndarray, colour: str = "yellow") -> list[ConeDetection]:
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
        detections: list[ConeDetection] = []
        for c in contours:
            area = float(cv2.contourArea(c))
            if area < self.min_cone_area:
                continue
            M = cv2.moments(c)
            if M["m00"] <= 0:
                continue
            cx = float(M["m10"] / M["m00"])
            cy = float(M["m01"] / M["m00"])
            x, y, w, h = cv2.boundingRect(c)
            detections.append(
                ConeDetection(
                    cx=cx,
                    cy=cy,
                    colour_label=colour,
                    score=min(1.0, area / 4000.0),
                    bbox=(float(x), float(y), float(x + w), float(y + h)),
                )
            )
        return detections

    def _cuda_compatible_for_sam(self) -> bool:
        """Check if CUDA is usable for SAM (PyTorch 2.4 supports up to sm_90; RTX 5080/5090 use sm_120)."""
        try:
            import torch
            if not torch.cuda.is_available():
                return False
            cap = torch.cuda.get_device_capability()
            # sm_90 = (9, 0). Newer GPUs (RTX 5080/5090) use sm_120 = (12, 0).
            if cap[0] > 9:
                logger.info(
                    "CUDA device sm_%d%d not supported by PyTorch build (supports up to sm_90). "
                    "Using CPU for SAM cone detection.",
                    cap[0], cap[1],
                )
                return False
            return True
        except Exception:
            return False

    def _build_sam3_predictor(self):
        if self._sam_predictor is not None:
            return self._sam_predictor
        from ultralytics.models.sam.predict import SAM3SemanticPredictor
        from ultralytics.utils.downloads import attempt_download_asset

        model_path = self.sam_model_path
        if "/" not in model_path and "\\" not in model_path and not Path(model_path).exists():
            try:
                resolved = attempt_download_asset(model_path)
                if resolved and Path(resolved).exists():
                    model_path = str(resolved)
            except Exception:
                pass
        if "sam3" in Path(model_path).stem.lower() and not Path(model_path).exists():
            try:
                from huggingface_hub import hf_hub_download

                model_path = hf_hub_download(repo_id="1038lab/sam3", filename="sam3.pt")
            except Exception:
                pass

        overrides: dict = {"model": model_path, "imgsz": 1036}
        if self._sam_force_cpu or not self._cuda_compatible_for_sam():
            overrides["device"] = "cpu"
        self._sam_predictor = SAM3SemanticPredictor(overrides=overrides)
        return self._sam_predictor

    def _detect_cones_sam3_prompt(self, frame: np.ndarray) -> list[ConeDetection]:
        predictor = self._build_sam3_predictor()
        predictor.set_prompts({"text": [self.sam_prompt]})
        try:
            results = predictor(source=frame, verbose=False)
        except RuntimeError as e:
            if "no kernel image" in str(e) or "not compatible" in str(e).lower():
                logger.warning(
                    "CUDA error during SAM inference, falling back to CPU: %s", e
                )
                self._sam_force_cpu = True
                self._sam_predictor = None
                predictor = self._build_sam3_predictor()
                predictor.set_prompts({"text": [self.sam_prompt]})
                results = predictor(source=frame, verbose=False)
            else:
                raise
        if not results:
            return []
        r0 = results[0]
        if getattr(r0, "masks", None) is None or r0.masks is None:
            return []

        masks = r0.masks.data
        if hasattr(masks, "cpu"):
            masks = masks.cpu().numpy()
        boxes = getattr(r0, "boxes", None)
        confs = None
        if boxes is not None and getattr(boxes, "conf", None) is not None:
            confs = boxes.conf
            if hasattr(confs, "cpu"):
                confs = confs.cpu().numpy()

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        detections: list[ConeDetection] = []
        for i, mask in enumerate(masks):
            mask_bin = mask > 0.5
            ys, xs = np.where(mask_bin)
            if xs.size == 0:
                continue
            m = cv2.moments(mask_bin.astype(np.uint8))
            if m["m00"] <= 0:
                continue
            cx = float(m["m10"] / m["m00"])
            cy = float(m["m01"] / m["m00"])
            pix = hsv[ys, xs]
            h_mean = float(np.mean(pix[:, 0]))
            s_mean = float(np.mean(pix[:, 1]))
            v_mean = float(np.mean(pix[:, 2]))
            colour_label = self._label_colour_from_hsv(h_mean, s_mean, v_mean)
            score = float(confs[i]) if confs is not None and i < len(confs) else 0.5
            x1, x2 = float(xs.min()), float(xs.max())
            y1, y2 = float(ys.min()), float(ys.max())
            detections.append(
                ConeDetection(
                    cx=cx,
                    cy=cy,
                    colour_label=colour_label,
                    score=score,
                    bbox=(x1, y1, x2, y2),
                )
            )
        return detections

    def _filter_and_select_cones_for_layout(
        self,
        cone_objects: list[ConeDetection],
        layout_config: dict,
        num_cones: int,
    ) -> list[ConeDetection]:
        """
        Filter by confidence and select the target number of cones assuming a
        distorted grid/linear layout. Drops uncertain detections, then picks
        the N that best fit the expected layout.
        """
        # 1. Drop low-confidence detections (SAM3 outputs score in [0,1])
        filtered = [c for c in cone_objects if c.score >= self.min_confidence]
        if len(filtered) < num_cones:
            logger.warning(
                "After confidence filter (min=%.2f): %d cones remain, need %d. "
                "Relaxing filter or using all detections.",
                self.min_confidence, len(filtered), num_cones,
            )
            filtered = cone_objects  # Fall back to all
        if len(filtered) <= num_cones:
            return filtered[:num_cones]

        pts = np.array([(c.cx, c.cy) for c in filtered], dtype=np.float64)
        pattern = layout_config.get("pattern", "linear")
        direction = layout_config.get("direction", "x")

        if pattern == "linear":
            # Fit line through points (PCA), project, sort by position along line
            center = pts.mean(axis=0)
            centered = pts - center
            cov = centered.T @ centered
            eigvals, eigvecs = np.linalg.eigh(cov)
            line_dir = eigvecs[:, np.argmax(eigvals)]
            line_dir = line_dir / (np.linalg.norm(line_dir) + 1e-9)
            proj = centered @ line_dir
            order = np.argsort(proj)
            if direction == "y":
                # For direction y, line should run vertically; flip if needed
                if line_dir[1] < 0:
                    order = order[::-1]
            indices = order[:num_cones]
        else:
            # Grid: use PCA to get row/col axes, sort by (row, col) for row-major order
            center = pts.mean(axis=0)
            centered = pts - center
            cov = centered.T @ centered
            eigvals, eigvecs = np.linalg.eigh(cov)
            proj_row = centered @ eigvecs[:, np.argmax(eigvals)]
            proj_col = centered @ eigvecs[:, np.argmin(eigvals)]
            order = np.lexsort((proj_col, proj_row))
            indices = order[:num_cones]

        return [filtered[i] for i in indices]

    def _fit_grid_iterative(
        self,
        cone_objects: list[ConeDetection],
        world_coords_cm: list[tuple[float, float]],
        layout_config: dict,
    ) -> tuple[np.ndarray | None, list[tuple[float, float]], list[tuple[float, float]], float]:
        """
        Iteratively assign detected cones to grid positions and fit homography.
        Returns (H, cone_px, world_cm, reprojection_error) or (None, [], [], inf) on failure.
        """
        max_iters = int(layout_config.get("grid_fit_max_iters", 20))
        match_radius_px = float(layout_config.get("grid_fit_match_radius_px", 50.0))
        min_inliers = int(layout_config.get("grid_fit_min_inliers", 4))
        use_confidence = bool(layout_config.get("grid_fit_use_confidence_weights", False))

        logger.debug(
            "Grid iterative fit: n_det=%d, n_world=%d, max_iters=%d, match_radius_px=%.0f, min_inliers=%d",
            len(cone_objects), len(world_coords_cm), max_iters, match_radius_px, min_inliers,
        )

        pts_px = np.array([(c.cx, c.cy) for c in cone_objects], dtype=np.float32)
        scores = np.array([c.score for c in cone_objects], dtype=np.float64)
        world_pts = np.array(world_coords_cm, dtype=np.float32)
        n_det = len(pts_px)
        n_world = len(world_pts)
        if n_det < min_inliers or n_world < min_inliers:
            logger.debug(
                "Grid fit: too few points (det=%d, world=%d, min_inliers=%d).",
                n_det, n_world, min_inliers,
            )
            return (None, [], [], float("inf"))

        # Initial hypothesis: PCA order (detections) vs grid order (world) — try normal and reversed
        det_sorted_idx = np.lexsort((pts_px[:, 0], pts_px[:, 1]))
        world_order = np.arange(n_world)
        best_H = None
        best_src: list[tuple[float, float]] = []
        best_dst: list[tuple[float, float]] = []
        best_err = float("inf")
        best_n = 0

        for world_try in [world_order, world_order[::-1]]:
            H, inlier_src, inlier_dst, err, n_in = self._iterate_grid_fit(
                pts_px,
                scores,
                world_pts[world_try],
                max_iters,
                match_radius_px,
                use_confidence,
            )
            if H is not None and n_in >= min_inliers and (n_in > best_n or (n_in == best_n and err < best_err)):
                best_H = H
                best_src = inlier_src
                best_dst = inlier_dst
                best_err = err
                best_n = n_in

        if best_H is None or best_n < min_inliers:
            logger.warning(
                "Grid iterative fit failed: best inliers=%d (min=%d), reproj_err=%.2f px.",
                best_n, min_inliers, best_err,
            )
            return (None, [], [], float("inf"))
        logger.info(
            "Grid iterative fit: %d inliers, reprojection error %.2f px.",
            best_n, best_err,
        )
        return (best_H, best_src, best_dst, best_err)

    def _iterate_grid_fit(
        self,
        pts_px: np.ndarray,
        scores: np.ndarray,
        world_pts: np.ndarray,
        max_iters: int,
        match_radius_px: float,
        use_confidence_weights: bool,
    ) -> tuple[np.ndarray | None, list[tuple[float, float]], list[tuple[float, float]], float, int]:
        """One pass: initial H from first-N correspondence, then assign → refit until stable."""
        n_det, n_world = len(pts_px), len(world_pts)
        n_seed = min(max(4, n_det), n_world)
        det_order = np.lexsort((pts_px[:, 0], pts_px[:, 1]))
        src_seed = pts_px[det_order[:n_seed]]
        dst_seed = world_pts[:n_seed]
        H, _ = cv2.findHomography(src_seed, dst_seed, cv2.RANSAC, 5.0)
        if H is None:
            return (None, [], [], float("inf"), 0)

        prev_matches = -1
        src_pts = list(src_seed)
        dst_pts = list(dst_seed)
        for it in range(max_iters):
            # H maps pixel -> world; project world -> image with inv(H)
            if len(dst_pts) < 4:
                break
            H, _ = cv2.findHomography(
                np.array(src_pts, dtype=np.float32),
                np.array(dst_pts, dtype=np.float32),
                cv2.RANSAC,
                5.0,
            )
            if H is None:
                break
            H_inv = np.linalg.inv(H)
            proj = cv2.perspectiveTransform(
                world_pts.reshape(-1, 1, 2).astype(np.float32), H_inv
            ).reshape(-1, 2)
            # Assign each detection to nearest projected grid point within radius (one-to-one)
            matches: list[tuple[int, int]] = []
            used_world = set()
            for i in range(n_det):
                dists = np.linalg.norm(proj - pts_px[i], axis=1)
                j = np.argmin(dists)
                if dists[j] <= match_radius_px and j not in used_world:
                    matches.append((i, j))
                    used_world.add(j)
            if len(matches) < 4:
                break
            src_pts = [tuple(pts_px[i].tolist()) for i, _ in matches]
            dst_pts = [tuple(world_pts[j].tolist()) for _, j in matches]
            if len(matches) == prev_matches:
                break
            prev_matches = len(matches)
            logger.debug(
                "Grid fit iter %d: %d matches, refitting H.",
                it + 1, len(matches),
            )
        if len(src_pts) < 4:
            return (None, [], [], float("inf"), 0)
        H_final, mask = cv2.findHomography(
            np.array(src_pts, dtype=np.float32),
            np.array(dst_pts, dtype=np.float32),
            cv2.RANSAC,
            5.0,
        )
        if H_final is None:
            return (None, [], [], float("inf"), 0)
        inlier = mask.ravel() > 0
        src_in = [src_pts[i] for i in range(len(src_pts)) if inlier[i]]
        dst_in = [dst_pts[i] for i in range(len(dst_pts)) if inlier[i]]
        if len(src_in) < 4:
            return (None, [], [], float("inf"), 0)
        # Reprojection error in pixel space: project world back to image, compare to src_in
        H_inv = np.linalg.inv(H_final)
        proj_px = cv2.perspectiveTransform(
            np.array([dst_in], dtype=np.float32), H_inv
        ).reshape(-1, 2)
        err = float(np.linalg.norm(np.array(src_in) - proj_px, axis=1).mean())
        return (H_final, src_in, dst_in, err, len(src_in))

    @staticmethod
    def _label_colour_from_hsv(h: float, s: float, v: float) -> str:
        # Assign a colour label for metadata/debugging only; no filtering.
        if s < 40 or v < 40:
            return "unknown"
        if 18 <= h <= 35:
            return "yellow"
        if 5 <= h < 18:
            return "orange"
        if 100 <= h <= 130:
            return "blue"
        if 0 <= h < 5 or h >= 170:
            return "red"
        return "unknown"

    # ------------------------------------------------------------------
    # Homography calibration
    # ------------------------------------------------------------------

    def calibrate_homography(
        self,
        frame: np.ndarray,
        known_world_coords_cm: list[tuple[float, float]],
        cone_colour: str = "yellow",
        cone_positions_px: list[tuple[float, float]] | None = None,
    ) -> CalibrationResult:
        """
        Compute 3×3 homography mapping pixel space → world floor plane (cm).

        Requires ≥ 4 corresponding cone points.
        HSV range must be tuned to this clip before calling.

        Args:
            frame:                  BGR frame (typically first frame of clip).
            known_world_coords_cm:  List of (x_cm, y_cm) for each cone in real space.
            cone_colour:            Colour key in HSV_RANGES.
            cone_positions_px:      Optional pre-detected cone centres. When provided,
                                   skips detection and uses these (e.g. from layout-based filtering).

        Returns:
            CalibrationResult (method='homography').
        """
        if cone_positions_px is not None:
            cone_px = list(cone_positions_px)
            cone_objects = [
                ConeDetection(cx=p[0], cy=p[1], colour_label=cone_colour, score=1.0)
                for p in cone_px
            ]
        else:
            cone_objects = self._detect_cone_objects(frame, colour=cone_colour)
            cone_px = [(c.cx, c.cy) for c in cone_objects]

        if len(cone_px) < 4:
            logger.warning(
                "Calibration failed: only %d cones detected (need ≥ 4 for homography). "
                "Try: detector_backend='hsv' with tuned HSV ranges, or check cone visibility in frame.",
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

        expected = len(known_world_coords_cm)
        if len(cone_px) < expected:
            # Use subset of world coords: calibrate with available cones (order already matches).
            logger.info(
                "Using %d detected cones for calibration (layout has %d); homography needs ≥ 4.",
                len(cone_px), expected,
            )
            known_world_coords_cm = known_world_coords_cm[:len(cone_px)]
            expected = len(known_world_coords_cm)
        if len(cone_px) > expected:
            logger.warning(
                "Detected %d cones for %d world points; taking top-%d by score.",
                len(cone_px), expected, expected,
            )
            cone_objects = sorted(cone_objects, key=lambda c: c.score, reverse=True)[:expected]
            cone_px = [(c.cx, c.cy) for c in cone_objects]
        # Stable ordering for point correspondences.
        cone_px = sorted(cone_px, key=lambda p: (p[1], p[0]))

        src_pts = np.array(cone_px, dtype=np.float32)
        dst_pts = np.array(known_world_coords_cm, dtype=np.float32)

        # Try normal order first; if RANSAC fails, try reversed (camera may view cones from opposite end)
        for dst_try, world_try, order_label in [
            (dst_pts, known_world_coords_cm, "normal"),
            (dst_pts[::-1].copy(), list(reversed(known_world_coords_cm)), "reversed"),
        ]:
            H, mask = cv2.findHomography(src_pts, dst_try, cv2.RANSAC, 5.0)
            if H is not None:
                projected = cv2.perspectiveTransform(
                    src_pts.reshape(-1, 1, 2), H
                ).reshape(-1, 2)
                errors = np.linalg.norm(projected - dst_try, axis=1)
                reprojection_error = float(errors.mean())
                if order_label == "reversed":
                    logger.info(
                        "findHomography succeeded with reversed cone order "
                        "(camera views from opposite end). Reprojection error: %.2f px",
                        reprojection_error,
                    )
                else:
                    logger.info(
                        "Homography calibrated. Reprojection error: %.2f px",
                        reprojection_error,
                    )
                return CalibrationResult(
                    method="homography",
                    homography_matrix=H,
                    pixels_per_cm=None,
                    cone_positions_px=list(map(tuple, src_pts.tolist())),
                    cone_positions_world=world_try,
                    reprojection_error_px=reprojection_error,
                    is_valid=reprojection_error < 3.0,
                )
            if order_label == "normal":
                logger.info(
                    "findHomography failed with normal order, trying reversed cone order."
                )

        logger.warning(
            "findHomography failed for both normal and reversed order. "
            "Points may be degenerate, have too many outliers, or cone layout does not match. "
            "Detected %d cones. Try: detector_backend='hsv', tune HSV ranges, or set reverse_order in layout.",
            len(cone_px),
        )
        return CalibrationResult(
            method="homography",
            homography_matrix=None,
            pixels_per_cm=None,
            cone_positions_px=list(map(tuple, src_pts.tolist())),
            cone_positions_world=known_world_coords_cm,
            reprojection_error_px=float("inf"),
            is_valid=False,
        )

    # ------------------------------------------------------------------
    # Layout-based calibration (spacing + first cone)
    # ------------------------------------------------------------------

    def calibrate_from_layout(
        self,
        frame: np.ndarray,
        layout_config: dict,
        cone_colour: str = "yellow",
    ) -> CalibrationResult:
        """
        Calibrate using a layout config (spacing + first cone) instead of
        explicit world coords. Supports linear, grid, and clustered patterns.

        Args:
            frame:         BGR frame (typically first frame).
            layout_config: Dict with pattern, first_cone_cm, spacing_cm, etc.
                          See pipeline/cone_layout.py and notebook templates.
            cone_colour:   Colour key for HSV (ignored if using sam3_prompt).

        Returns:
            CalibrationResult (method='homography').
        """
        cone_objects = self._detect_cone_objects(frame, colour=cone_colour)
        cone_px = [(c.cx, c.cy) for c in cone_objects]

        if len(cone_px) < 4:
            logger.warning(
                "Calibration failed: only %d cones detected (need ≥ 4 for homography). "
                "Try: detector_backend='hsv' with tuned HSV ranges, or check cone visibility.",
                len(cone_px),
            )
            return CalibrationResult(
                method="homography",
                homography_matrix=None,
                pixels_per_cm=None,
                cone_positions_px=cone_px,
                cone_positions_world=[],
                reprojection_error_px=float("inf"),
                is_valid=False,
            )

        pattern = layout_config.get("pattern", "linear")
        if pattern == "clustered":
            # Filter by confidence for clustered
            cone_objects_filtered = [
                c for c in cone_objects if c.score >= self.min_confidence
            ]
            if len(cone_objects_filtered) < 4:
                cone_objects_filtered = cone_objects
            cone_px = [(c.cx, c.cy) for c in cone_objects_filtered]
            known_world_coords_cm = generate_cone_world_coords_from_pixels(
                layout_config, cone_px
            )
            num_cones = len(cone_px)
        elif pattern == "grid" and layout_config.get("grid_fit_use_iterative", True):
            num_cones = layout_config.get("cone_count") or len(cone_px)
            known_world_coords_cm = generate_cone_world_coords(
                layout_config, num_cones
            )
            H, cone_px_matched, world_matched, reproj_err = self._fit_grid_iterative(
                cone_objects, known_world_coords_cm, layout_config
            )
            if H is not None and len(cone_px_matched) >= 4:
                logger.info(
                    "Layout-based calibration (grid iterative): %d matched cones, pattern=grid, reproj_err=%.2f px",
                    len(cone_px_matched), reproj_err,
                )
                return CalibrationResult(
                    method="homography",
                    homography_matrix=H,
                    pixels_per_cm=None,
                    cone_positions_px=cone_px_matched,
                    cone_positions_world=world_matched,
                    reprojection_error_px=reproj_err,
                    is_valid=reproj_err < 3.0,
                )
            # Fall back to legacy grid path
            cone_objects_filtered = self._filter_and_select_cones_for_layout(
                cone_objects, layout_config, num_cones
            )
            cone_px_sorted = [(c.cx, c.cy) for c in cone_objects_filtered]
            n = min(len(cone_px_sorted), num_cones)
            cone_px_sorted = cone_px_sorted[:n]
            known_world_coords_cm = known_world_coords_cm[:n]
            logger.info(
                "Layout-based calibration: %d cones (grid fallback), pattern=%s",
                n, pattern,
            )
            return self.calibrate_homography(
                frame,
                known_world_coords_cm=list(known_world_coords_cm),
                cone_colour=cone_colour,
                cone_positions_px=cone_px_sorted,
            )
        else:
            num_cones = layout_config.get("cone_count") or len(cone_px)
            known_world_coords_cm = generate_cone_world_coords(
                layout_config, num_cones
            )
            # Filter by confidence and select target cones assuming distorted grid
            cone_objects_filtered = self._filter_and_select_cones_for_layout(
                cone_objects, layout_config, num_cones
            )

        cone_px_sorted = [(c.cx, c.cy) for c in cone_objects_filtered]
        n = min(len(cone_px_sorted), num_cones)
        cone_px_sorted = cone_px_sorted[:n]
        if len(known_world_coords_cm) > n:
            known_world_coords_cm = known_world_coords_cm[:n]

        logger.info(
            "Layout-based calibration: %d cones (from %d after confidence filter), pattern=%s",
            n, len(cone_objects_filtered), pattern,
        )
        return self.calibrate_homography(
            frame,
            known_world_coords_cm=list(known_world_coords_cm),
            cone_colour=cone_colour,
            cone_positions_px=cone_px_sorted,
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

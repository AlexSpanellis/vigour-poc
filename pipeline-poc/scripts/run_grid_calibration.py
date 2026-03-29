#!/usr/bin/env python3
"""
Run layout-based calibration with fitness config (grid 6x7, iterative fit).
Use for validating iterative grid fitting with partial cone detections.

Success: With grid_fit_use_iterative and fitness.json, calibration succeeds
with partial detections (e.g. 5+ cones); reprojection error stays low (< 3 px).

Usage:
  python scripts/run_grid_calibration.py [video_path]
  VIDEO_PATH defaults to data/raw_footage/shuttles_test_behind.mp4
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# Ensure project root on path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.calibrate import Calibrator
from pipeline.ingest import extract_frames

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    video_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data/raw_footage/shuttles_test_behind.mp4"
    config_path = ROOT / "configs/test_configs/fitness.json"
    if not config_path.exists():
        logger.error("Config not found: %s", config_path)
        sys.exit(1)
    if not video_path.exists():
        logger.error("Video not found: %s", video_path)
        sys.exit(1)

    with open(config_path) as f:
        config = json.load(f)

    geometry_config = config
    cone_layout = dict(geometry_config.get("cone_layout", {}))
    if "cone_count" not in cone_layout and "cone_count" in geometry_config:
        cone_layout["cone_count"] = geometry_config["cone_count"]

    calibrator = Calibrator(
        detector_backend=geometry_config.get("calibration_detector", "sam3_prompt"),
        sam_model_path=geometry_config.get("calibration_model", "sam3.pt"),
        sam_prompt=geometry_config.get("calibration_prompt", "training cone"),
        min_confidence=geometry_config.get("calibration_min_confidence", 0.5),
    )

    frames_iter = extract_frames(str(video_path), target_fps=15)
    _, first_frame, _ = next(frames_iter)
    logger.info("First frame shape: %s", first_frame.shape)

    calibration = calibrator.calibrate_from_layout(first_frame, cone_layout)

    print("\n--- Grid calibration result ---")
    print("Method:              ", calibration.method)
    print("Valid:               ", calibration.is_valid)
    print("Reprojection error cm:", calibration.reprojection_error_cm)
    print("Cones used:          ", len(calibration.cone_positions_px))
    if calibration.homography_matrix is not None:
        print("Homography shape:    ", calibration.homography_matrix.shape)
    print("------------------------------\n")

    sys.exit(0 if calibration.is_valid else 1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Standalone full-pipeline runner — no Celery/Redis required.

Runs: Ingest → Detect → Track → Pose → OCR → Calibrate (SAM3 cones) → Extract → Output
with top-down rendered view and metric estimates.

Usage:
  python scripts/run_full_pipeline.py [video_path] [--test-type fitness]
  Defaults: video=data/raw_footage/shuttles_test_behind.mp4, test_type=fitness
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_full_pipeline")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run vigour POC pipeline end-to-end")
    parser.add_argument("video", nargs="?",
                        default=str(ROOT / "data/raw_footage/shuttles_test_behind.mp4"),
                        help="Path to input video")
    parser.add_argument("--test-type", default="fitness",
                        choices=["explosiveness", "speed", "fitness", "agility", "balance"],
                        help="Test type (default: fitness)")
    parser.add_argument("--no-pose", action="store_true", help="Skip pose estimation")
    parser.add_argument("--no-ocr", action="store_true", help="Skip OCR/bib detection")
    parser.add_argument("--output", default=None, help="Output annotated video path")
    args = parser.parse_args()

    video_path = Path(args.video)
    test_type = args.test_type
    run_pose = not args.no_pose
    run_ocr = not args.no_ocr

    if not video_path.exists():
        logger.error("Video not found: %s", video_path)
        sys.exit(1)

    # ── Load geometry config ────────────────────────────────────────────────
    config_path = ROOT / "configs/test_configs" / f"{test_type}.json"
    if config_path.exists():
        with open(config_path) as f:
            geometry_config = json.load(f)
    else:
        logger.warning("No config for '%s'; using empty config.", test_type)
        geometry_config = {}

    target_fps = geometry_config.get("capture_fps", 15)
    t0 = time.time()

    # ── Stage 1: Ingest ─────────────────────────────────────────────────────
    logger.info("Stage 1/8: Ingest — %s", video_path.name)
    from pipeline.ingest import extract_frames

    raw_frames, frame_indices, timestamps_s = [], [], []
    for fi, frame, ts in extract_frames(str(video_path), target_fps=target_fps):
        raw_frames.append(frame)
        frame_indices.append(fi)
        timestamps_s.append(ts)
    logger.info("  %d frames extracted (%.1f s)", len(raw_frames), time.time() - t0)

    # ── Stage 2: Detect ─────────────────────────────────────────────────────
    logger.info("Stage 2/8: Person detection (YOLOv8s)")
    from pipeline.detect import PersonDetector

    detector = PersonDetector()
    all_detections = []
    for i, frame in enumerate(raw_frames):
        dets = detector.detect(frame)
        for d in dets:
            d.frame_idx = frame_indices[i]
        all_detections.append(dets)
    logger.info("  Detection done (%.1f s total)", time.time() - t0)

    # ── Stage 3: Track ──────────────────────────────────────────────────────
    logger.info("Stage 3/8: Multi-person tracking (ByteTrack)")
    from pipeline.track import PersonTracker

    tracker = PersonTracker()
    all_tracks = []
    for i, (frame, dets) in enumerate(zip(raw_frames, all_detections)):
        tracks = tracker.update(dets, frame_idx=frame_indices[i])
        all_tracks.append(tracks)
    logger.info("  Tracking done (%.1f s total)", time.time() - t0)

    # ── Stage 4: Pose (optional) ────────────────────────────────────────────
    if run_pose:
        logger.info("Stage 4/8: Pose estimation (RTMPose-m)")
        from pipeline.pose import PoseEstimator

        estimator = PoseEstimator()
        all_poses = []
        for frame, tracks in zip(raw_frames, all_tracks):
            poses = estimator.estimate_batch(frame, tracks)
            all_poses.append(poses)
        logger.info("  Pose done (%.1f s total)", time.time() - t0)
    else:
        logger.info("Stage 4/8: Pose SKIPPED")
        all_poses = [[] for _ in raw_frames]

    # ── Stage 5: OCR (optional) ─────────────────────────────────────────────
    resolved = {}
    if run_ocr:
        logger.info("Stage 5/8: Bib OCR (PaddleOCR)")
        from pipeline.ocr import BibOCR, resolve_bibs

        ocr = BibOCR()
        frame_readings = []
        for i, (frame, tracks) in enumerate(zip(raw_frames, all_tracks)):
            if i % 5 == 0:
                readings = ocr.read_frame(frame, tracks)
                frame_readings.append(readings)
        resolved = resolve_bibs(frame_readings)
        logger.info("  OCR done — %d bibs resolved (%.1f s total)", len(resolved), time.time() - t0)
    else:
        logger.info("Stage 5/8: OCR SKIPPED")

    # Attach bib numbers
    for frame_tracks in all_tracks:
        for track in frame_tracks:
            bib, conf = resolved.get(track.track_id, (None, 0.0))
            track.bib_number = bib
            track.bib_confidence = conf

    # ── Stage 6: Calibrate (SAM3 + 2D cone grid) ───────────────────────────
    logger.info("Stage 6/8: Calibration (SAM3 cone detection + 2D homography)")
    from pipeline.calibrate import Calibrator
    from pipeline.models import CalibrationResult

    calibrator = Calibrator(
        detector_backend=geometry_config.get("calibration_detector", "sam3_prompt"),
        sam_model_path=geometry_config.get("calibration_model", "sam3.pt"),
        sam_prompt=geometry_config.get("calibration_prompt", "training cone"),
        min_confidence=geometry_config.get("calibration_min_confidence", 0.5),
    )

    first_frame = raw_frames[0] if raw_frames else None
    cone_layout = dict(geometry_config.get("cone_layout", {}))
    if "cone_count" not in cone_layout and "cone_count" in geometry_config:
        cone_layout["cone_count"] = geometry_config["cone_count"]

    if first_frame is not None and cone_layout and cone_layout.get("pattern"):
        calibration = calibrator.calibrate_from_layout(first_frame, cone_layout)
    elif first_frame is not None:
        calibration = calibrator.calibrate_single_axis(first_frame)
    else:
        import numpy as np
        calibration = CalibrationResult(
            method="none", homography_matrix=None, pixels_per_cm=None,
            cone_positions_px=[], cone_positions_world=[],
            reprojection_error_cm=float("inf"), is_valid=False,
        )

    logger.info("  Calibration: method=%s valid=%s reproj_err=%.2f cm cones=%d (%.1f s total)",
                calibration.method, calibration.is_valid,
                calibration.reprojection_error_cm,
                len(calibration.cone_positions_px), time.time() - t0)

    # ── Stage 7: Extract metrics ────────────────────────────────────────────
    logger.info("Stage 7/8: Metric extraction (%s)", test_type)
    from pipeline.tests.explosiveness import ExplosivenessExtractor
    from pipeline.tests.sprint import SprintExtractor
    from pipeline.tests.shuttle import ShuttleExtractor
    from pipeline.tests.agility import AgilityExtractor
    from pipeline.tests.balance import BalanceExtractor

    extractors = {
        "explosiveness": ExplosivenessExtractor,
        "speed": SprintExtractor,
        "fitness": ShuttleExtractor,
        "agility": AgilityExtractor,
        "balance": BalanceExtractor,
    }

    results = []
    if not run_pose and test_type == "balance":
        logger.warning("  Balance test requires pose — skipping extraction.")
    else:
        try:
            extractor = extractors[test_type](geometry_config, calibration)
            results = extractor.extract(all_tracks, all_poses, raw_frames)
        except Exception as exc:
            logger.error("  Extraction failed: %s", exc)

    logger.info("  %d results extracted (%.1f s total)", len(results), time.time() - t0)

    # ── Stage 8: Output (annotated video with top-down view) ────────────────
    output_dir = ROOT / "data" / "annotated"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = Path(args.output) if args.output else output_dir / f"pipeline_{test_type}_topdown.mp4"
    json_path = output_path.with_suffix(".json")

    logger.info("Stage 8/8: Output — annotated video with top-down view")

    from pipeline.output import write_results_json
    write_results_json(results, json_path)

    from pipeline.visualise import PipelineVisualiser, VisOptions

    vis_opts = VisOptions(
        show_boxes=True,
        show_skeleton=run_pose,
        show_calibration_grid=calibration.is_valid,
        show_test_overlay=True,
        show_hud=True,
        show_frame_counter=True,
        show_flags=True,
        show_top_down_view=True,          # <-- enabled
        top_down_view_size=(280, 280),     # slightly larger for clarity
        trace_history_frames=geometry_config.get("trace_history_frames", 60),
    )

    with PipelineVisualiser(output_path, test_type=test_type, fps=target_fps, options=vis_opts) as vis:
        for frame, tracks, poses, ts in zip(raw_frames, all_tracks, all_poses, timestamps_s):
            vis.write_frame(frame, tracks, poses, calibration, results, timestamp_s=ts)

    elapsed = time.time() - t0
    logger.info("Pipeline complete in %.1f s", elapsed)
    logger.info("Annotated video: %s", output_path)
    logger.info("Results JSON:    %s", json_path)

    # ── Print results summary ───────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"  VIGOUR POC — {test_type.upper()} TEST RESULTS")
    print("=" * 60)
    print(f"  Video:       {video_path.name}")
    print(f"  Frames:      {len(raw_frames)}")
    print(f"  Calibration: {calibration.method} (valid={calibration.is_valid}, "
          f"error={calibration.reprojection_error_cm:.2f} cm)")
    print(f"  Cones found: {len(calibration.cone_positions_px)}")
    print(f"  Top-down:    enabled (280x280 inset)")
    print("-" * 60)
    if results:
        for r in results:
            bib = r.bib_number if hasattr(r, "bib_number") and r.bib_number else f"track-{r.track_id}"
            print(f"  [{bib}] {r.test_type}: {r.metric_value:.2f} {r.metric_unit}"
                  f"  (conf={r.confidence_score:.2f})")
            if r.flags:
                print(f"         flags: {', '.join(r.flags)}")
    else:
        print("  No metric results extracted.")
    print("=" * 60)
    print(f"  Output: {output_path}")
    print()


if __name__ == "__main__":
    main()

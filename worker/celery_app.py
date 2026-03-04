"""
Vigour POC — Celery Worker
Orchestrates the full CV pipeline as a background task.

Start worker:
    celery -A worker.celery_app worker --concurrency=1 --loglevel=info
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from pathlib import Path

from celery import Celery

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CONFIGS_DIR = Path(os.getenv("CONFIGS_DIR", "configs/test_configs"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "data/annotated"))

celery = Celery(
    "vigour_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    result_expires=86400,  # 24 hours
)


@celery.task(bind=True, name="worker.celery_app.process_clip")
def process_clip(
    self,
    job_id: str,
    video_path: str,
    test_type: str,
    config_override: str | None = None,
) -> list[dict]:
    """
    Full pipeline execution for a single video clip.

    Stages: Ingest → Detect → Track → Pose → OCR → Calibrate → Extract → Output

    Args:
        job_id:          Unique job identifier.
        video_path:      Absolute path to uploaded video.
        test_type:       Which metric extractor to run.
        config_override: Optional JSON string with geometry config overrides.

    Returns:
        List of serialised TestResult dicts.
    """
    self.update_state(state="STARTED", meta={"stage": "initialising"})
    logger.info("[%s] Starting pipeline for %s (test=%s)", job_id, video_path, test_type)

    # Load geometry config
    config_path = CONFIGS_DIR / f"{test_type}.json"
    if config_path.exists():
        with open(config_path) as f:
            geometry_config = json.load(f)
    else:
        logger.warning("No config file for %s. Using empty config.", test_type)
        geometry_config = {}

    if config_override:
        overrides = json.loads(config_override)
        geometry_config.update(overrides)

    # --- Stage 1: Ingest ---
    self.update_state(state="STARTED", meta={"stage": "ingestion"})
    from pipeline.ingest import extract_frames
    target_fps = geometry_config.get("capture_fps", 15)
    frames_gen = extract_frames(video_path, target_fps=target_fps)

    raw_frames, frame_indices = [], []
    for frame_idx, frame, _ in frames_gen:
        raw_frames.append(frame)
        frame_indices.append(frame_idx)

    logger.info("[%s] Ingested %d frames.", job_id, len(raw_frames))

    # --- Stage 2: Detect ---
    self.update_state(state="STARTED", meta={"stage": "detection"})
    from pipeline.detect import PersonDetector
    detector = PersonDetector()
    all_detections = []
    for i, frame in enumerate(raw_frames):
        dets = detector.detect(frame)
        for d in dets:
            d.frame_idx = frame_indices[i]
        all_detections.append(dets)

    # --- Stage 3: Track ---
    self.update_state(state="STARTED", meta={"stage": "tracking"})
    from pipeline.track import PersonTracker
    tracker = PersonTracker()
    all_tracks = []
    for i, (frame, dets) in enumerate(zip(raw_frames, all_detections)):
        tracks = tracker.update(dets, frame_idx=frame_indices[i])
        all_tracks.append(tracks)

    # --- Stage 4: Pose ---
    self.update_state(state="STARTED", meta={"stage": "pose_estimation"})
    from pipeline.pose import PoseEstimator
    pose_estimator = PoseEstimator()
    all_poses = []
    for frame, tracks in zip(raw_frames, all_tracks):
        poses = pose_estimator.estimate_batch(frame, tracks)
        all_poses.append(poses)

    # --- Stage 5: OCR ---
    self.update_state(state="STARTED", meta={"stage": "ocr"})
    from pipeline.ocr import BibOCR, resolve_bibs
    ocr = BibOCR()
    frame_readings = []
    for i, (frame, tracks) in enumerate(zip(raw_frames, all_tracks)):
        if i % 5 == 0:  # sample every 5th frame
            readings = ocr.read_frame(frame, tracks)
            frame_readings.append(readings)

    resolved = resolve_bibs(frame_readings)
    # Attach bib numbers to track objects
    for frame_tracks in all_tracks:
        for track in frame_tracks:
            bib, conf = resolved.get(track.track_id, (None, 0.0))
            track.bib_number = bib
            track.bib_confidence = conf

    # --- Stage 6: Calibrate ---
    self.update_state(state="STARTED", meta={"stage": "calibration"})
    from pipeline.calibrate import Calibrator
    calibrator = Calibrator()
    first_frame = raw_frames[0] if raw_frames else None
    world_coords = geometry_config.get("cone_world_coords_cm", [])

    if first_frame is not None and world_coords:
        calibration = calibrator.calibrate_homography(first_frame, world_coords)
    elif first_frame is not None:
        calibration = calibrator.calibrate_single_axis(first_frame)
    else:
        from pipeline.models import CalibrationResult
        import numpy as np
        calibration = CalibrationResult(
            method="single_axis",
            homography_matrix=None,
            pixels_per_cm=None,
            cone_positions_px=[],
            cone_positions_world=[],
            reprojection_error_px=float("inf"),
            is_valid=False,
        )

    # --- Stage 7: Extract ---
    self.update_state(state="STARTED", meta={"stage": "metric_extraction"})
    extractor = _get_extractor(test_type, geometry_config, calibration)
    results = extractor.extract(all_tracks, all_poses, raw_frames)

    # --- Stage 8: Output ---
    self.update_state(state="STARTED", meta={"stage": "output"})
    from pipeline.output import write_results_json, AnnotatedVideoWriter
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / f"{job_id}_results.json"
    write_results_json(results, json_path)

    annotated_path = OUTPUT_DIR / f"{job_id}_annotated.mp4"
    writer = AnnotatedVideoWriter(annotated_path)
    writer.open()
    for frame, tracks, poses in zip(raw_frames, all_tracks, all_poses):
        writer.write_frame(frame, tracks, poses)
    writer.close()

    logger.info("[%s] Pipeline complete. %d results.", job_id, len(results))
    return [asdict(r) for r in results]


def _get_extractor(test_type: str, config: dict, calibration):
    from pipeline.tests.explosiveness import ExplosivenessExtractor
    from pipeline.tests.sprint import SprintExtractor
    from pipeline.tests.shuttle import ShuttleExtractor
    from pipeline.tests.agility import AgilityExtractor
    from pipeline.tests.balance import BalanceExtractor

    mapping = {
        "explosiveness": ExplosivenessExtractor,
        "speed": SprintExtractor,
        "fitness": ShuttleExtractor,
        "agility": AgilityExtractor,
        "balance": BalanceExtractor,
    }
    cls = mapping.get(test_type)
    if cls is None:
        raise ValueError(f"Unknown test_type: {test_type}")
    return cls(config, calibration)

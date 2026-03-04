"""
Vigour POC — Celery Worker
Orchestrates the full CV pipeline as a background task.

Start worker:
    celery -A worker.celery_app worker --concurrency=1 --loglevel=info

Cache behaviour (controlled by PIPELINE_FORCE_RERUN env var):
    - By default each stage checks the PipelineCache before running.
      If a valid cached result exists it is loaded and the stage is skipped.
    - Set PIPELINE_FORCE_RERUN=1 to bypass all caches and re-run every stage.
    - The /cache/{job_id} DELETE endpoint (api/main.py) invalidates from a
      given stage onwards, then re-runs from that point on next trigger.

Stage toggles:
    ENABLE_POSE=0   — Skip pose estimation (speeds up runs without GPU; pose-based
                      metrics will be unavailable; balance extractor is disabled).
    ENABLE_OCR=0    — Skip OCR / bib resolution (all bib_numbers remain None;
                      tracks are still reported with track_id-based identity).
    Both can also be passed as per-job parameters to process_clip().
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from pathlib import Path

from celery import Celery

logger = logging.getLogger(__name__)

REDIS_URL   = os.getenv("REDIS_URL",    "redis://localhost:6379/0")
CONFIGS_DIR = Path(os.getenv("CONFIGS_DIR",  "configs/test_configs"))
OUTPUT_DIR  = Path(os.getenv("OUTPUT_DIR",   "data/annotated"))
FORCE_RERUN = os.getenv("PIPELINE_FORCE_RERUN", "0") == "1"

# ── Stage toggles (env defaults; can be overridden per-job call) ─────────────
_DEFAULT_ENABLE_POSE = os.getenv("ENABLE_POSE", "1") == "1"
_DEFAULT_ENABLE_OCR  = os.getenv("ENABLE_OCR",  "1") == "1"

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
    enable_pose: bool | None = None,
    enable_ocr: bool | None = None,
) -> list[dict]:
    """
    Full pipeline execution for a single video clip.

    Stages: Ingest → Detect → Track → [Pose] → [OCR] → Calibrate → Extract → Output

    Each stage checks PipelineCache first — only runs if no valid cache entry.

    Args:
        job_id:          Unique job identifier (UUID).
        video_path:      Absolute path to uploaded video clip.
        test_type:       One of: explosiveness, speed, fitness, agility, balance.
        config_override: Optional JSON string to override geometry config values.
        enable_pose:     Override ENABLE_POSE env var for this job. Default: env setting.
        enable_ocr:      Override ENABLE_OCR env var for this job. Default: env setting.
    """
    from pipeline.cache import PipelineCache

    # Resolve stage toggles (per-job param takes priority over env default)
    run_pose = _DEFAULT_ENABLE_POSE if enable_pose is None else bool(enable_pose)
    run_ocr  = _DEFAULT_ENABLE_OCR  if enable_ocr  is None else bool(enable_ocr)

    self.update_state(state="STARTED", meta={
        "stage": "initialising",
        "enable_pose": run_pose,
        "enable_ocr": run_ocr,
    })
    logger.info(
        "[%s] Starting pipeline for %s (test=%s, pose=%s, ocr=%s)",
        job_id, video_path, test_type, run_pose, run_ocr,
    )

    cache = PipelineCache(job_id=job_id)

    # ── Load geometry config ─────────────────────────────────────────────────
    config_path = CONFIGS_DIR / f"{test_type}.json"
    if config_path.exists():
        with open(config_path) as f:
            geometry_config = json.load(f)
    else:
        logger.warning("No config for test type '%s'. Using empty config.", test_type)
        geometry_config = {}

    if config_override:
        geometry_config.update(json.loads(config_override))

    target_fps = geometry_config.get("capture_fps", 15)

    # ── Stage 1: Ingest ──────────────────────────────────────────────────────
    self.update_state(state="STARTED", meta={"stage": "ingestion"})
    if not FORCE_RERUN and cache.has("ingest"):
        logger.info("[%s] Cache hit: ingest", job_id)
        frame_indices, timestamps_s = cache.load_ingest()
        # Raw frames must be re-read (not cached — too large)
        from pipeline.ingest import extract_frames
        raw_frames = [f for _, f, _ in extract_frames(video_path, target_fps=target_fps)]
    else:
        from pipeline.ingest import extract_frames
        raw_frames, frame_indices, timestamps_s = [], [], []
        for fi, frame, ts in extract_frames(video_path, target_fps=target_fps):
            raw_frames.append(frame)
            frame_indices.append(fi)
            timestamps_s.append(ts)
        cache.save_ingest(frame_indices, timestamps_s, test_type=test_type)

    logger.info("[%s] %d frames ready.", job_id, len(raw_frames))

    # ── Stage 2: Detect ──────────────────────────────────────────────────────
    self.update_state(state="STARTED", meta={"stage": "detection"})
    if not FORCE_RERUN and cache.has("detect"):
        logger.info("[%s] Cache hit: detect", job_id)
        all_detections = cache.load_detections()
    else:
        from pipeline.detect import PersonDetector
        detector = PersonDetector()
        all_detections = []
        for i, frame in enumerate(raw_frames):
            dets = detector.detect(frame)
            for d in dets:
                d.frame_idx = frame_indices[i]
            all_detections.append(dets)
        cache.save_detections(all_detections)

    # ── Stage 3: Track ───────────────────────────────────────────────────────
    self.update_state(state="STARTED", meta={"stage": "tracking"})
    if not FORCE_RERUN and cache.has("track"):
        logger.info("[%s] Cache hit: track", job_id)
        all_tracks = cache.load_tracks()
    else:
        from pipeline.track import PersonTracker
        tracker = PersonTracker()
        all_tracks = []
        for i, (frame, dets) in enumerate(zip(raw_frames, all_detections)):
            tracks = tracker.update(dets, frame_idx=frame_indices[i])
            all_tracks.append(tracks)
        cache.save_tracks(all_tracks)

    # ── Stage 4: Pose (optional) ─────────────────────────────────────────────
    self.update_state(state="STARTED", meta={"stage": "pose_estimation" if run_pose else "pose_skipped"})
    if run_pose:
        if not FORCE_RERUN and cache.has("pose"):
            logger.info("[%s] Cache hit: pose", job_id)
            all_poses = cache.load_poses()
        else:
            from pipeline.pose import PoseEstimator
            estimator = PoseEstimator()
            all_poses = []
            for frame, tracks in zip(raw_frames, all_tracks):
                poses = estimator.estimate_batch(frame, tracks)
                all_poses.append(poses)
            cache.save_poses(all_poses)
    else:
        logger.info("[%s] Pose estimation DISABLED (enable_pose=False)", job_id)
        all_poses = [[] for _ in raw_frames]  # empty pose list per frame

    # ── Stage 5: OCR (optional) ──────────────────────────────────────────────
    self.update_state(state="STARTED", meta={"stage": "ocr" if run_ocr else "ocr_skipped"})
    if run_ocr:
        if not FORCE_RERUN and cache.has("ocr"):
            logger.info("[%s] Cache hit: ocr", job_id)
            frame_readings, resolved = cache.load_ocr()
        else:
            from pipeline.ocr import BibOCR, resolve_bibs
            ocr = BibOCR()
            frame_readings = []
            for i, (frame, tracks) in enumerate(zip(raw_frames, all_tracks)):
                if i % 5 == 0:
                    readings = ocr.read_frame(frame, tracks)
                    frame_readings.append(readings)
            resolved = resolve_bibs(frame_readings)
            cache.save_ocr(frame_readings, resolved)
    else:
        logger.info("[%s] OCR DISABLED (enable_ocr=False) — bibs will be unresolved", job_id)
        resolved = {}  # no bib assignments; tracks keep bib_number=None

    # Attach bib numbers to track objects
    for frame_tracks in all_tracks:
        for track in frame_tracks:
            bib, conf = resolved.get(track.track_id, (None, 0.0))
            track.bib_number = bib
            track.bib_confidence = conf

    # ── Stage 6: Calibrate ───────────────────────────────────────────────────
    self.update_state(state="STARTED", meta={"stage": "calibration"})
    if not FORCE_RERUN and cache.has("calibrate"):
        logger.info("[%s] Cache hit: calibrate", job_id)
        calibration = cache.load_calibration()
    else:
        from pipeline.calibrate import Calibrator
        from pipeline.models import CalibrationResult
        calibrator = Calibrator()
        first_frame = raw_frames[0] if raw_frames else None
        world_coords = geometry_config.get("cone_world_coords_cm", [])
        if first_frame is not None and world_coords:
            calibration = calibrator.calibrate_homography(first_frame, world_coords)
        elif first_frame is not None:
            calibration = calibrator.calibrate_single_axis(first_frame)
        else:
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
        cache.save_calibration(calibration)

    # ── Stage 7: Extract ─────────────────────────────────────────────────────
    self.update_state(state="STARTED", meta={"stage": "metric_extraction"})
    if not FORCE_RERUN and cache.has("results"):
        logger.info("[%s] Cache hit: results", job_id)
        results = cache.load_results()
    else:
        if not run_pose and test_type == "balance":
            logger.warning(
                "[%s] Balance test requires pose — results will be empty (enable_pose=False).",
                job_id,
            )
            results = []
        else:
            extractor = _get_extractor(test_type, geometry_config, calibration)
            results = extractor.extract(all_tracks, all_poses, raw_frames)
        cache.save_results(results)

    # ── Stage 8: Output (annotated video + JSON) ─────────────────────────────
    self.update_state(state="STARTED", meta={"stage": "output"})
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    from pipeline.output import write_results_json
    json_path = OUTPUT_DIR / f"{job_id}_results.json"
    write_results_json(results, json_path)

    from pipeline.visualise import PipelineVisualiser, VisOptions
    annotated_path = OUTPUT_DIR / f"{job_id}_annotated.mp4"
    vis_opts = VisOptions(
        show_calibration_grid=calibration.is_valid,
        show_skeleton=run_pose,          # hide skeleton layer when pose is off
        trace_history_frames=geometry_config.get("trace_history_frames", 60),
    )
    with PipelineVisualiser(annotated_path, test_type=test_type, fps=target_fps, options=vis_opts) as vis:
        for frame, tracks, poses, ts in zip(raw_frames, all_tracks, all_poses, timestamps_s):
            vis.write_frame(frame, tracks, poses, calibration, results, timestamp_s=ts)

    logger.info(
        "[%s] Pipeline complete. %d results. Video: %s",
        job_id, len(results), annotated_path,
    )
    return [asdict(r) for r in results]


# ── Extractor factory ────────────────────────────────────────────────────────

def _get_extractor(test_type: str, config: dict, calibration):
    from pipeline.tests.explosiveness import ExplosivenessExtractor
    from pipeline.tests.sprint       import SprintExtractor
    from pipeline.tests.shuttle      import ShuttleExtractor
    from pipeline.tests.agility      import AgilityExtractor
    from pipeline.tests.balance      import BalanceExtractor

    mapping = {
        "explosiveness": ExplosivenessExtractor,
        "speed":         SprintExtractor,
        "fitness":       ShuttleExtractor,
        "agility":       AgilityExtractor,
        "balance":       BalanceExtractor,
    }
    cls = mapping.get(test_type)
    if cls is None:
        raise ValueError(f"Unknown test_type: {test_type}")
    return cls(config, calibration)

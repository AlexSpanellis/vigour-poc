"""
Vigour POC — FastAPI Service

Endpoints:
    POST   /upload                  — Upload video clip + test config, returns job_id
    GET    /results/{job_id}        — Poll job status and retrieve TestResult JSON
    GET    /health                  — Liveness probe

    GET    /cache                   — List all cached jobs (summary)
    GET    /cache/{job_id}          — Cache summary + per-stage metadata for one job
    DELETE /cache/{job_id}          — Clear entire cache for a job
    DELETE /cache/{job_id}/{stage}  — Invalidate from {stage} onwards (re-runs that
                                       stage + all downstream on next process_clip call)
    GET    /annotated/{job_id}      — Stream the annotated output .mp4 for review
"""
from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Vigour POC API",
    version="0.2.0",
    description="CV pipeline for physical fitness test analysis.",
)

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/tmp/vigour_uploads"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "data/annotated"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

VALID_TEST_TYPES = {"explosiveness", "speed", "fitness", "agility", "balance"}
PIPELINE_STAGES  = ["ingest", "detect", "track", "pose", "ocr", "calibrate", "results"]


# ── Health ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.2.0"}


# ── Video upload + processing ─────────────────────────────────────────────────

@app.post("/upload")
async def upload_clip(
    file: UploadFile = File(...),
    test_type: str = Form(...),
    config_override: str | None = Form(None),
) -> JSONResponse:
    """
    Accept a video clip and enqueue a pipeline processing job.

    Args:
        file:            .mp4 or .mov video clip.
        test_type:       One of: explosiveness, speed, fitness, agility, balance.
        config_override: Optional JSON string to override default geometry config.

    Returns:
        {"job_id": "<uuid>", "status": "queued"}
    """
    if test_type not in VALID_TEST_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid test_type '{test_type}'. Must be one of: {VALID_TEST_TYPES}",
        )

    job_id = str(uuid.uuid4())
    save_path = UPLOAD_DIR / f"{job_id}_{file.filename}"
    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)

    logger.info("Uploaded %s → %s (job_id=%s)", file.filename, save_path, job_id)

    try:
        from worker.celery_app import process_clip  # type: ignore
        process_clip.delay(
            job_id=job_id,
            video_path=str(save_path),
            test_type=test_type,
            config_override=config_override,
        )
    except Exception as exc:
        logger.error("Failed to enqueue task: %s", exc)
        raise HTTPException(status_code=500, detail="Worker unavailable. Try again.")

    return JSONResponse({"job_id": job_id, "status": "queued"})


@app.get("/results/{job_id}")
async def get_results(job_id: str) -> JSONResponse:
    """
    Poll job status and return results once complete.

    Returns:
        {"job_id": "...", "status": "pending|processing|complete|failed", "results": [...]}
    """
    try:
        from worker.celery_app import celery  # type: ignore
        from celery.result import AsyncResult  # type: ignore

        result = AsyncResult(job_id, app=celery)
        if result.state == "PENDING":
            return JSONResponse({"job_id": job_id, "status": "pending"})
        elif result.state == "STARTED":
            meta = result.info or {}
            return JSONResponse({"job_id": job_id, "status": "processing", "stage": meta.get("stage")})
        elif result.state == "SUCCESS":
            return JSONResponse({"job_id": job_id, "status": "complete", "results": result.result})
        elif result.state == "FAILURE":
            return JSONResponse({"job_id": job_id, "status": "failed", "error": str(result.result)})
        else:
            return JSONResponse({"job_id": job_id, "status": result.state})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Annotated video download ──────────────────────────────────────────────────

@app.get("/annotated/{job_id}")
async def get_annotated_video(job_id: str) -> FileResponse:
    """
    Stream the annotated output video for browser/VLC review.
    Returns 404 if the pipeline has not yet completed.
    """
    _validate_job_id(job_id)
    video_path = OUTPUT_DIR / f"{job_id}_annotated.mp4"
    if not video_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Annotated video not found for job {job_id}. Has the pipeline completed?",
        )
    return FileResponse(
        path=str(video_path),
        media_type="video/mp4",
        filename=f"vigour_{job_id}_annotated.mp4",
    )


# ── Cache management ──────────────────────────────────────────────────────────

@app.get("/cache")
async def list_cached_jobs() -> JSONResponse:
    """
    Return a summary of all jobs that have cached pipeline data.

    Returns:
        {"jobs": [{"job_id": "...", "stages_cached": [...], "size_mb": ...}]}
    """
    from pipeline.cache import PipelineCache
    jobs = PipelineCache.list_jobs()
    return JSONResponse({"jobs": jobs, "total": len(jobs)})


@app.get("/cache/{job_id}")
async def get_cache_info(job_id: str) -> JSONResponse:
    """
    Return cache metadata and per-stage status for a specific job.

    Returns:
        {
            "job_id": "...",
            "test_type": "...",
            "stages_cached": ["ingest", "detect", ...],
            "size_mb": 12.4,
            "available_stages": ["ingest", ...]
        }
    """
    _validate_job_id(job_id)
    from pipeline.cache import PipelineCache
    cache = PipelineCache(job_id=job_id)
    summary = cache.summary()
    summary["available_stages"] = PIPELINE_STAGES
    return JSONResponse(summary)


@app.delete("/cache/{job_id}")
async def clear_job_cache(job_id: str) -> JSONResponse:
    """
    Delete all cached pipeline data for a job.
    Next call to process_clip with this job_id will re-run all stages from scratch.
    """
    _validate_job_id(job_id)
    from pipeline.cache import PipelineCache
    cache = PipelineCache(job_id=job_id)
    cache.clear()
    logger.info("Cache cleared for job %s", job_id)
    return JSONResponse({"job_id": job_id, "status": "cache_cleared"})


@app.delete("/cache/{job_id}/{stage}")
async def invalidate_cache_from_stage(job_id: str, stage: str) -> JSONResponse:
    """
    Invalidate cache from {stage} onwards for a job.
    On the next process_clip call, stages before {stage} load from cache;
    {stage} and all downstream stages re-run.

    Valid stages: ingest, detect, track, pose, ocr, calibrate, results

    Common use cases:
        DELETE /cache/{id}/results   → Re-run only metric extraction (fastest)
        DELETE /cache/{id}/pose      → Re-run pose + OCR + calibration + extraction
        DELETE /cache/{id}/detect    → Re-run everything from detection onwards
    """
    _validate_job_id(job_id)
    if stage not in PIPELINE_STAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown stage '{stage}'. Valid stages: {PIPELINE_STAGES}",
        )
    from pipeline.cache import PipelineCache
    cache = PipelineCache(job_id=job_id)
    cache.invalidate(stage)
    invalidated = PIPELINE_STAGES[PIPELINE_STAGES.index(stage):]
    logger.info("Cache invalidated from '%s' for job %s", stage, job_id)
    return JSONResponse({
        "job_id":            job_id,
        "status":            "invalidated",
        "stages_invalidated": invalidated,
        "stages_retained":   PIPELINE_STAGES[:PIPELINE_STAGES.index(stage)],
    })


# ── Validation helpers ────────────────────────────────────────────────────────

def _validate_job_id(job_id: str) -> None:
    """Guard: job_id must be a valid UUID to prevent path traversal."""
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid job_id: '{job_id}'")

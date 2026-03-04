"""
Vigour POC — FastAPI Service
Accepts video upload, enqueues Celery pipeline job, returns results by job ID.

Endpoints:
    POST /upload          — Upload video clip + test config, returns job_id
    GET  /results/{id}    — Poll job status and retrieve TestResult JSON
    GET  /health          — Liveness probe
"""
from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Vigour POC API",
    version="0.1.0",
    description="CV pipeline for physical fitness test analysis.",
)

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/tmp/vigour_uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}


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
        config_override: Optional JSON string to override default test config.

    Returns:
        {"job_id": "<uuid>", "status": "queued"}
    """
    valid_test_types = {"explosiveness", "speed", "fitness", "agility", "balance"}
    if test_type not in valid_test_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid test_type '{test_type}'. Must be one of: {valid_test_types}",
        )

    job_id = str(uuid.uuid4())
    save_path = UPLOAD_DIR / f"{job_id}_{file.filename}"

    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)

    logger.info("Uploaded %s → %s (job_id=%s)", file.filename, save_path, job_id)

    # Enqueue Celery task
    try:
        from worker.celery_app import process_clip  # type: ignore
        task = process_clip.delay(
            job_id=job_id,
            video_path=str(save_path),
            test_type=test_type,
            config_override=config_override,
        )
        logger.info("Enqueued Celery task: %s", task.id)
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
            return JSONResponse({"job_id": job_id, "status": "processing"})
        elif result.state == "SUCCESS":
            return JSONResponse({"job_id": job_id, "status": "complete", "results": result.result})
        elif result.state == "FAILURE":
            return JSONResponse({"job_id": job_id, "status": "failed", "error": str(result.result)})
        else:
            return JSONResponse({"job_id": job_id, "status": result.state})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

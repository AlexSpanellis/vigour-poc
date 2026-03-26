# Expose Granular Pipeline Stage Progress via API

**Priority**: UI development phase

## Context

The Celery worker already calls `self.update_state()` with stage-level metadata as it moves through the 8 pipeline stages, and this data lives in Redis. However, `GET /results/{job_id}` only returns a top-level status (`pending`, `processing`, `complete`, `failed`) — it does not surface which stage is currently running.

## Proposal

Either extend `GET /results/{job_id}` or add a dedicated `GET /status/{job_id}` endpoint that queries Celery's backend for custom task state and returns:

- **Current stage** — number (1-8) and name
- **Per-stage status** — complete, running, or pending
- **Optional stage flags** — whether pose and OCR stages are enabled or skipped
- **Progress hint** — percentage estimate or ETA (if feasible)

Example response shape:

```json
{
  "job_id": "abc-123",
  "status": "processing",
  "current_stage": 3,
  "stages": [
    { "stage": 1, "name": "detection", "status": "complete" },
    { "stage": 2, "name": "tracking", "status": "complete" },
    { "stage": 3, "name": "segmentation", "status": "running" },
    { "stage": 4, "name": "pose", "status": "pending", "enabled": true },
    { "stage": 5, "name": "ocr", "status": "pending", "enabled": false }
  ],
  "progress_pct": 30
}
```

## Why

Processing takes 30-120 seconds per clip. A stage-by-stage progress display gives users meaningful feedback and is a much better UX than a simple spinner.

## Implementation Notes

- The custom state data is already being written to Redis by the worker; the main work is reading and shaping it in the API layer.
- A separate `/status` endpoint keeps concerns clean, but enriching `/results` avoids an extra call from the frontend — pick based on how the UI polling is structured.
- Consider including `enabled` flags so the UI can render skipped stages differently.

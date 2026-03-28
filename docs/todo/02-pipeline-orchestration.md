# Pipeline Orchestration: Job Queuing & Configurable Runner

**Priority**: Pipeline integration phase

## Context

The CV pipeline currently runs as a single sequential process on one GPU with all models loaded. As the system scales — multiple clients uploading videos, different test types requiring different pipeline steps, potential GPU memory constraints — we need job queuing and a configurable pipeline runner.

Discussion with Alex (2026-03-23) confirmed:
- The pipeline steps are largely reusable but different tests need different configurations of steps (some optional, some skipped).
- Currently tested with up to 8 students; batch sizes should be configurable, not assumed at 30.
- Each pipeline stage has different GPU/VRAM requirements. Models are currently all loaded on one GPU — this won't scale indefinitely.
- Multiple videos may be submitted concurrently (e.g. a client uploads 3 clips). Need queuing and ordering.

## Decision: No DAG Orchestrator Yet

We considered Airflow, Temporal, and GCP Cloud Composer. **Decision: don't introduce a DAG orchestrator now.** The pipelines are still simple sequential chains. A DAG tool adds operational overhead (config, monitoring, deployment, debugging) that isn't justified yet.

**When to reconsider:** When pipeline topology has genuine branching logic that's painful to maintain in code, or when non-engineers need to reason about pipeline structure.

If we do eventually need one, **Vertex AI Pipelines** is the natural GCP fit — it's managed Kubeflow, designed for ML workloads, and supports per-step GPU allocation natively.

## TODO

### 1. Job Queuing via Pub/Sub

- [ ] Set up a **Cloud Pub/Sub** topic for video processing jobs
- [ ] Client uploads video → Application API publishes message to queue → worker picks it up
- [ ] This replaces the current direct `POST /upload` call with an async queue-based submission
- [ ] Handles the "3 videos uploaded at once" case — they queue up and process in order
- [ ] Consider Cloud Tasks as an alternative if we want built-in retry/scheduling

### 2. Configurable Pipeline Runner

- [ ] Refactor the pipeline runner so the step list is configurable per test type
- [ ] Each test type defines which stages it needs (e.g. balance needs pose, speed doesn't need OCR)
- [ ] Steps should be composable — a list of step classes/functions that the runner chains
- [ ] `enable_pose` and `enable_ocr` flags already exist; generalise this pattern to all optional stages
- [ ] Configuration should be declarative (e.g. a dict/config per test type listing active steps)

### 3. GPU Memory Management (When Needed)

Not urgent now, but groundwork to do:

- [ ] **Profile VRAM per stage** — Alex to log `torch.cuda.memory_allocated()` after each model loads to get real numbers
- [ ] **Lazy load + explicit unload** — each step loads its model on entry and does `del model; torch.cuda.empty_cache()` on exit
- [ ] **Identify the big models** — SAM2 is likely the largest; determine if everything fits on a single 24GB+ GPU

### 4. Future Scaling (Not Now)

Two paths when single-GPU is no longer enough:

- **Batched model loading** — group pending jobs and run all through Stage 1, then unload, load Stage 2, run all through Stage 2, etc. Amortises load/unload cost. Good for steady throughput.
- **Step-specific workers** — each stage gets its own worker/GPU. Steps communicate via queues. This is effectively a DAG built from queues. GKE with node pools or Cloud Run Jobs can right-size GPU per step.

## Relationship to Existing Architecture

- The Celery worker architecture (section 3 of `08-pipeline-integration.md`) already supports queuing — Pub/Sub would sit in front of it or replace it.
- The config passthrough mechanism (section 8) already handles per-job overrides — the configurable runner extends this to per-test-type step selection.
- Stage-level caching (section 7) works regardless of orchestration approach — cached stages are still skipped on re-runs.

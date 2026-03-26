# Vigour POC - Project Overview

## What Is Vigour?

Vigour is a computer vision pipeline for **automated physical fitness test analysis** from school hall video footage. It targets **South African school students** (heights vary by age group; the CV pipeline adapts to configured grade ranges) wearing numbered bibs (01-30) in maroon or navy colours.

The system takes a video clip of a fitness test being performed, processes it through an 8-stage computer vision pipeline, and outputs:
1. **Quantitative metrics** for each student (jump height, sprint time, etc.)
2. **An annotated video** with bounding boxes, pose skeletons, calibration grids, and metric overlays
3. **Structured JSON results** ready for database storage

## The Problem It Solves

Physical fitness assessments in schools are traditionally measured manually by teachers using stopwatches, tape measures, and clipboards. This is:
- **Slow**: One teacher timing one student at a time
- **Error-prone**: Human reaction time in stopwatch usage, subjective balance judgments
- **Labour-intensive**: Recording results for 30+ students across 5 different tests

Vigour automates this by pointing a camera at the test area and letting the CV pipeline measure everything simultaneously for all visible students.

## Five Fitness Tests Supported

| Test | What It Measures | Metric | Unit | Target Accuracy |
|------|-----------------|--------|------|-----------------|
| **Explosiveness** | Vertical jump height | How high they jump | cm | ±2 cm |
| **Sprint** | 5-metre speed | Time to cover 5m | seconds | ±0.05 s |
| **Fitness (Shuttle)** | Shuttle run distance | Total distance in 3×15s sets | metres | ±0.5 m |
| **Agility** | T-drill time | Time to complete T-drill pattern | seconds | ±0.1 s |
| **Balance** | Single-leg balance duration | Time standing on one leg | seconds | ±0.5 s |

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT / UI                              │
│  Upload video → Poll status → View results → Download video     │
└──────────────┬──────────────────────────────────┬───────────────┘
               │ POST /upload                     │ GET /results
               ▼                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                     FastAPI  (api/main.py)                       │
│  Accepts uploads, enqueues jobs, serves results & annotated vids│
└──────────────┬──────────────────────────────────────────────────┘
               │ Celery task
               ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Celery Worker  (worker/celery_app.py)           │
│  Orchestrates the 8-stage pipeline with caching                 │
└──────────────┬──────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────┐
│                    8-Stage CV Pipeline                           │
│                                                                 │
│  1. Ingest ──► 2. Detect ──► 3. Track ──► 4. Pose (optional)   │
│       │              │            │            │                 │
│       ▼              ▼            ▼            ▼                │
│  5. OCR (optional) ──► 6. Calibrate ──► 7. Extract ──► 8. Output│
└─────────────────────────────────────────────────────────────────┘
               │                              │
               ▼                              ▼
┌──────────────────┐               ┌─────────────────────┐
│   PostgreSQL 15  │               │    Redis 7          │
│   (sessions,     │               │    (Celery broker    │
│    clips,        │               │     + result backend)│
│    results)      │               │                     │
└──────────────────┘               └─────────────────────┘
```

## Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **API** | FastAPI 0.110+ | REST endpoints for upload, polling, cache management |
| **Task Queue** | Celery 5.3.6 + Redis 7 | Async job processing |
| **Detection** | YOLOv8s (Ultralytics) | Person bounding box detection |
| **Tracking** | ByteTrack | Multi-person identity tracking across frames |
| **Pose** | RTMPose-m (MMPose, ONNX) | 17-keypoint COCO skeleton estimation |
| **OCR** | PaddleOCR PP-OCRv4 | Bib number recognition |
| **Calibration** | HSV segmentation / SAM3 | Cone detection for pixel→world mapping |
| **Database** | PostgreSQL 15 | Results persistence |
| **Cloud** | GCP (Terraform) | Production deployment (L4 GPU VM) |
| **Containerisation** | Docker + Docker Compose | Local dev + deployment |

## Project Status

- **Phase**: Proof of Concept (POC)
- **Timeline**: March 4-15, 2026 (initial development sprint)
- **State**: Core pipeline complete, 37 unit tests passing, 8 evaluation notebooks, ready for field footage validation
- **Next**: UI development for video upload, result viewing, and pipeline management

## Environment Context

- **Floor**: Light wooden parquet (school hall)
- **Lighting**: Diffuse indoor fluorescent
- **Students**: School-age children, maroon/navy numbered bibs (01-30)
- **Cones**: Yellow (H 18-35), Orange (H 5-18), Blue (H 100-130), Red (H 0-5/170-180) in HSV
- **Capture**: 30 fps camera → 15 fps pipeline ingestion (60 fps for sprint)

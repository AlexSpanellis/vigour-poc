# UI Development Considerations

This document captures the key considerations for building a frontend UI for the Vigour pipeline, based on the existing backend architecture.

## What the UI Needs to Do

### Core Workflows

1. **Upload & Process**
   - Upload video files (.mp4, .mov) for a specific test type
   - Select test type (explosiveness, speed, fitness, agility, balance)
   - Optionally override configuration parameters
   - Toggle pose estimation and OCR on/off

2. **Monitor Progress**
   - Poll job status (pending → processing → complete/failed)
   - Show which pipeline stage is currently running
   - Display estimated completion time or progress indicator

3. **View Results**
   - Per-student metrics (bib number, metric value, confidence)
   - Flag indicators (bib_unresolved, low_pose_confidence, etc.)
   - Per-attempt breakdown for multi-attempt tests

4. **Review Annotated Video**
   - Playback of annotated video with overlays
   - Toggle overlay layers (boxes, skeleton, calibration grid, etc.)

5. **Manage Cache**
   - List all cached jobs
   - View cache details per job (stages cached, size)
   - Clear entire cache or invalidate specific stages
   - Force pipeline re-run from a specific stage

6. **Session Management**
   - Create/manage test sessions (school, date)
   - Associate clips with sessions
   - View all results for a session

## Existing API Endpoints Available

| Endpoint | Method | Purpose | UI Feature |
|----------|--------|---------|------------|
| `/upload` | POST | Submit video + test type | Upload form |
| `/results/{job_id}` | GET | Poll status + results | Progress + results view |
| `/annotated/{job_id}` | GET | Download annotated video | Video player |
| `/health` | GET | Service health check | Status indicator |
| `/cache` | GET | List all cached jobs | Cache management |
| `/cache/{job_id}` | GET | Job cache details | Cache inspector |
| `/cache/{job_id}` | DELETE | Clear job cache | Cache management |
| `/cache/{job_id}/{stage}` | DELETE | Invalidate stage+ | Stage re-run |

## Data to Display

### Results Table Structure
```
| Bib # | Track ID | Test Type      | Value  | Unit | Attempt | Confidence | Flags              |
|-------|----------|----------------|--------|------|---------|------------|--------------------|
| 7     | 1        | explosiveness  | 34.2   | cm   | 1       | 0.92       |                    |
| 14    | 2        | explosiveness  | 28.8   | cm   | 1       | 0.85       | low_pose_confidence|
| -1    | 5        | explosiveness  | 22.1   | cm   | 1       | 0.40       | bib_unresolved     |
```

### Test Types & Their Metrics

| Test Type | Metric Display | Unit | Target Accuracy | Visual Indicator |
|-----------|---------------|------|-----------------|------------------|
| Explosiveness | Jump Height | cm | ±2 cm | Vertical bar chart |
| Speed | Sprint Time | s | ±0.05 s | Horizontal bar chart |
| Fitness | Shuttle Distance | m | ±0.5 m | Distance indicator |
| Agility | T-Drill Time | s | ±0.1 s | Horizontal bar chart |
| Balance | Duration | s | ±0.5 s | Timer display |

### Confidence Levels

| Score Range | Meaning | Suggested UI |
|-------------|---------|-------------|
| 0.8 – 1.0 | High confidence, bib resolved | Green indicator |
| 0.6 – 0.8 | Moderate confidence | Yellow indicator |
| 0.4 – 0.6 | Low confidence, possible issues | Orange indicator |
| 0.0 – 0.4 | Very low, bib unresolved | Red indicator |

## Pipeline Stages for Progress Display

```
1. Ingesting frames...     ████████████████████ 100%
2. Detecting persons...    ████████████░░░░░░░░  60%
3. Tracking identities...  ░░░░░░░░░░░░░░░░░░░░   0%
4. Estimating pose...      ░░░░░░░░░░░░░░░░░░░░   0%  (skipped if disabled)
5. Reading bib numbers...  ░░░░░░░░░░░░░░░░░░░░   0%  (skipped if disabled)
6. Calibrating camera...   ░░░░░░░░░░░░░░░░░░░░   0%
7. Extracting metrics...   ░░░░░░░░░░░░░░░░░░░░   0%
8. Generating output...    ░░░░░░░░░░░░░░░░░░░░   0%
```

## Database Entities for UI

### Sessions
- School name + date
- Number of clips processed
- Overall status

### Clips
- Video filename
- Test type
- Job status (pending/processing/complete/failed)
- Timestamps (created, completed)

### Results
- Student bib number
- Test metrics with confidence
- Flags and warnings
- Raw debug data (expandable)

## Configuration Override UI

The UI could provide test-specific configuration forms:

### Common Parameters
- FPS override
- Enable/disable pose estimation
- Enable/disable OCR
- Force cache rerun

### Per-Test Parameters
- **Explosiveness**: Jump threshold, baseline frames, min height
- **Sprint**: Sprint distance, start/finish line positions
- **Shuttle**: Cone count, set duration, number of sets
- **Agility**: Drill pattern, cone positions, start zone size
- **Balance**: Lean threshold, max duration

## Technical Notes

### Video Handling
- Accepted formats: .mp4, .mov
- Annotated output: H.264 MP4
- Video streaming via `/annotated/{job_id}` endpoint
- Consider video.js or similar player for in-browser playback

### Real-Time Considerations
- Job processing is async (Celery)
- Results polling via GET `/results/{job_id}` (consider WebSocket for live updates)
- Typical processing time: 30-120 seconds per clip depending on length and GPU

### Error States to Handle
- Upload failure (file too large, wrong format)
- Pipeline failure (check worker logs)
- Invalid calibration (not enough cones detected)
- OCR failure (bib unresolved for all students)
- GPU unavailable (fallback to CPU, slower processing)

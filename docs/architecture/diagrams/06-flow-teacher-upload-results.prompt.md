# 06 - Teacher: Upload, Processing and Results

**Tool**: `gemini --yolo "/diagram '...'"`
**Generated**: 2026-03-24

## Prompt

```
Teacher Complete Session Workflow - Part 2: Upload, Processing and Results. User flow diagram.

Flow (top to bottom):
1. Teacher taps Upload → App requests upload from API, Clip record created + signed GCS URL returned, session uploading
2. Upload Progress Screen - progress bar 0-100%, estimated time, do not close app
3. Decision: Upload successful? If no (network error) → Upload Failed screen, option to Retry or queue for Later (auto-retry when connected)
4. If yes → Upload confirmed, Stage 0: Metadata Stripping (audio stripped, GPS/device metadata removed via FFmpeg), pipeline job submitted, session queued
5. Pipeline Status Screen showing progress through 8 stages: Ingest, Detect, Track, Pose, OCR, Calibrate, Extract, Output with progress bars
6. Teacher can leave screen, push notification when results ready
7. Decision: Pipeline outcome? If failed → Pipeline Failed Screen with options: Retry Processing, Re-record Video, Get Help. Second failure escalates to support.
8. If success → Results Processing Screen with summary cards: Tracked, High conf, Review needed
9. Per-student result review: High confidence (green check) → approve. Low confidence (warning) → accept or reassign to different student. Unresolved bib (red X) → manually assign student or discard
10. Bulk approve option for all high confidence results
11. Consent Verification at result ingestion: verify METRIC_PROCESSING consent for each resolved student before storing. Students without consent → results discarded with audit log entry
12. All reviewed → Commit Results to Profiles → Session complete
13. Results linked to student profiles
14. Session Complete Screen with ranked results
15. Options: View student profile, New session, Return home

Modern clean style with decision diamonds, color-coded confidence levels (green/yellow/red).
```

## Regenerate

```bash
cd docs/architecture/diagrams
GEMINI_API_KEY="$NANOBANANA_GEMINI_API_KEY" gemini --yolo "/diagram 'Teacher Complete Session Workflow - Part 2: Upload, Processing and Results. User flow diagram.

Flow (top to bottom):
1. Teacher taps Upload → App requests upload from API, Clip record created + signed GCS URL returned, session uploading
2. Upload Progress Screen - progress bar 0-100%, estimated time, do not close app
3. Decision: Upload successful? If no (network error) → Upload Failed screen, option to Retry or queue for Later (auto-retry when connected)
4. If yes → Upload confirmed, Stage 0: Metadata Stripping (audio stripped, GPS/device metadata removed via FFmpeg), pipeline job submitted, session queued
5. Pipeline Status Screen showing progress through 8 stages: Ingest, Detect, Track, Pose, OCR, Calibrate, Extract, Output with progress bars
6. Teacher can leave screen, push notification when results ready
7. Decision: Pipeline outcome? If failed → Pipeline Failed Screen with options: Retry Processing, Re-record Video, Get Help. Second failure escalates to support.
8. If success → Results Processing Screen with summary cards: Tracked, High conf, Review needed
9. Per-student result review: High confidence (green check) → approve. Low confidence (warning) → accept or reassign to different student. Unresolved bib (red X) → manually assign student or discard
10. Bulk approve option for all high confidence results
11. Consent Verification at result ingestion: verify METRIC_PROCESSING consent for each resolved student before storing. Students without consent → results discarded with audit log entry
12. All reviewed → Commit Results to Profiles → Session complete
13. Results linked to student profiles
14. Session Complete Screen with ranked results
15. Options: View student profile, New session, Return home

Modern clean style with decision diamonds, color-coded confidence levels (green/yellow/red).'"
```

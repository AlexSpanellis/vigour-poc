# 03 - End-to-End Data Flow

**Tool**: `gemini --yolo "/diagram '...'"`
**Generated**: 2026-03-24

## Prompt

```
End-to-end data flow diagram for the Vigour fitness testing platform. Show the complete journey with consent, data residency, and schema separation annotations:

1. Teacher creates TestSession (selects class and test type)
2. Teacher assigns bib numbers to students (BibAssignment)
3. Teacher runs pre-flight checks
4. [CONSENT GATE] App verifies consent status for all students in class before recording is allowed
5. Teacher records video on mobile device
6. Teacher reviews clip locally
7. [STAGE 0 - METADATA STRIP] App strips audio + GPS metadata from video before upload
8. App requests upload from API (Tier 1, UUID-only) - API creates Clip record and signed GCS URL
9. App uploads sanitised video directly to GCS africa-south1 via signed URL
10. App confirms upload complete
11. Application API submits job to Pipeline API (africa-south1)
12. [EPHEMERAL GPU - European region] Pipeline runs 8 CV stages: Ingest → Detect (YOLOv8s) → Track (ByteTrack) → Pose (RTMPose) → OCR (PaddleOCR) → Calibrate (HSV/SAM) → Extract → Output. Auto-purge all video data from GPU workers after processing.
13. Pipeline returns results to Pipeline API (africa-south1)
14. Application API ingests results
15. [CONSENT VERIFICATION] Verify consent status before storing results against students
16. Match bib numbers to students via BibAssignment lookup
17. [SCHEMA SEPARATION] Results stored in core_data schema (UUID-only), identity in identity schema
18. Flag unresolved bibs and low-confidence results
19. Teacher reviews and approves results (Tier 1 API)
20. [TIER 2 API BOUNDARY] Identity-enriched views for reporting - Teacher, Coach (class view), School Head (school view)

Modern flowchart style, top to bottom, with pipeline stages highlighted as a distinct section. Annotate Tier 1/Tier 2 API boundaries. Show data residency regions (africa-south1 persistent, European region ephemeral).
```

## Regenerate

```bash
cd docs/architecture/diagrams
GEMINI_API_KEY="$NANOBANANA_GEMINI_API_KEY" gemini --yolo "/diagram 'End-to-end data flow diagram for the Vigour fitness testing platform. Show the complete journey with consent, data residency, and schema separation annotations:

1. Teacher creates TestSession (selects class and test type)
2. Teacher assigns bib numbers to students (BibAssignment)
3. Teacher runs pre-flight checks
4. [CONSENT GATE] App verifies consent status for all students in class before recording is allowed
5. Teacher records video on mobile device
6. Teacher reviews clip locally
7. [STAGE 0 - METADATA STRIP] App strips audio + GPS metadata from video before upload
8. App requests upload from API (Tier 1, UUID-only) - API creates Clip record and signed GCS URL
9. App uploads sanitised video directly to GCS africa-south1 via signed URL
10. App confirms upload complete
11. Application API submits job to Pipeline API (africa-south1)
12. [EPHEMERAL GPU - European region] Pipeline runs 8 CV stages: Ingest → Detect (YOLOv8s) → Track (ByteTrack) → Pose (RTMPose) → OCR (PaddleOCR) → Calibrate (HSV/SAM) → Extract → Output. Auto-purge all video data from GPU workers after processing.
13. Pipeline returns results to Pipeline API (africa-south1)
14. Application API ingests results
15. [CONSENT VERIFICATION] Verify consent status before storing results against students
16. Match bib numbers to students via BibAssignment lookup
17. [SCHEMA SEPARATION] Results stored in core_data schema (UUID-only), identity in identity schema
18. Flag unresolved bibs and low-confidence results
19. Teacher reviews and approves results (Tier 1 API)
20. [TIER 2 API BOUNDARY] Identity-enriched views for reporting - Teacher, Coach (class view), School Head (school view)

Modern flowchart style, top to bottom, with pipeline stages highlighted as a distinct section. Annotate Tier 1/Tier 2 API boundaries. Show data residency regions (africa-south1 persistent, European region ephemeral).'"
```

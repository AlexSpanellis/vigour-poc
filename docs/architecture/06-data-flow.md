# Data Flow

## 1. Overview

This document traces how data moves through the Vigour platform end-to-end, from a teacher setting up a test session through to results appearing on dashboards. It covers the session lifecycle, data ownership boundaries, the result approval workflow, data aggregation, and video handling.

The session lifecycle state machine in Section 3 is the **canonical reference** for session states. Other documents (domain model, API architecture, client applications) should defer to this definition.

---

## 2. End-to-End Flow

![End-to-End Data Flow](./diagrams/03-data-flow.png)

The upload step follows the **resolved "task before upload" pattern (Option B)**: the Application API creates a task record (Clip) and returns a signed GCS URL in one response. The client uploads directly to cloud storage — no video bytes pass through the API. On completion, the client confirms the upload, which triggers pipeline processing.

```mermaid
flowchart TD
    A[Teacher creates test session\nclass + test type] --> B[Teacher assigns bibs to students]
    B --> B2[Consent verification gate\nall bib-assigned students must have\nactive VIDEO_CAPTURE + METRIC_PROCESSING consent]
    B2 --> C[Teacher runs pre-flight checks]
    C --> D[Teacher records video]
    D --> E[Teacher reviews clip locally]
    E --> F[App requests upload from API\nAPI creates Clip + signed GCS URL]
    F --> G[App uploads video\ndirectly to GCS via signed URL]
    G --> H[App confirms upload complete\nPATCH /clips status: uploaded]
    H --> I[Application API submits job\nto Pipeline API]

    I --> P1[Ingest]
    P1 --> P2[Detect]
    P2 --> P3[Track]
    P3 --> P4[Pose]
    P4 --> P5[OCR]
    P5 --> P6[Calibrate]
    P6 --> P7[Extract]
    P7 --> P8[Output]

    P8 --> J[Application API ingests results]
    J --> K[Match bibs to students\nvia BibAssignment lookup]
    K --> K2[Flag unresolved bibs and\nlow-confidence results for review]
    K2 --> L[Teacher reviews and\napproves results]
    L --> M[Approved results stored\nagainst student profiles]
    M --> O1[Coach: class view]
    M --> O2[School Head: school view]

    subgraph Pipeline["CV Pipeline (8 stages)"]
        P1
        P2
        P3
        P4
        P5
        P6
        P7
        P8
    end
```

---

## 3. Session Lifecycle States

This is the **canonical state machine** for test sessions. The `TestSession.status` field in the domain model tracks the top-level state. The `processing` state contains the 8 pipeline sub-stages (Ingest, Detect, Track, Pose, OCR, Calibrate, Extract, Output).

```mermaid
stateDiagram-v2
    [*] --> draft
    draft --> ready : Bibs assigned, consent verified
    ready --> recording : Teacher starts capture
    recording --> recorded : Capture complete
    recorded --> uploading : Teacher confirms clip
    uploading --> queued : Upload complete, job submitted
    queued --> processing : Pipeline picks up job
    processing --> review : Pipeline complete
    processing --> failed : Pipeline error
    failed --> queued : Retry submitted
    review --> complete : Teacher approves all results
    complete --> [*]

    state processing {
        [*] --> ingest
        ingest --> detect
        detect --> track
        track --> pose
        pose --> ocr
        ocr --> calibrate
        calibrate --> extract
        extract --> output
        output --> [*]
    }
```

**State descriptions:**

| State | Description |
|-------|-------------|
| `draft` | Session created with class and test type selected. No bibs assigned yet. |
| `ready` | Bibs assigned to students. All bib-assigned students verified to have active `VIDEO_CAPTURE` + `METRIC_PROCESSING` consent. Students without consent must be removed before the session can move to `recording`. Teacher can begin recording. |
| `recording` | Teacher is actively capturing video. |
| `recorded` | Capture complete. Teacher can review the clip locally before uploading. |
| `uploading` | Video is being uploaded directly to GCS via signed URL. |
| `queued` | Upload confirmed; job submitted to Pipeline API. Waiting for a worker. |
| `processing` | Pipeline is actively processing the video through 8 stages. |
| `failed` | Pipeline encountered an error. Teacher can retry or re-record. |
| `review` | Pipeline complete. Results are matched to students and awaiting teacher approval. |
| `complete` | Teacher has approved all results. Results linked to student profiles. |

> **Note**: The domain model (`01-domain-model.md`) defines the full set of 10 states on the `TestSession` entity. This document provides the canonical state machine with transition triggers and the processing sub-states.

---

## 4. Data Ownership

The Application DB and Pipeline DB are **separate databases** (or separate schemas within a single PostgreSQL instance — see [07-infrastructure.md](./07-infrastructure.md)). Each service owns its own data. The Application API never writes to the Pipeline DB, and the Pipeline never writes to the Application DB.

```mermaid
flowchart LR
    subgraph AppDB["Application DB (PostgreSQL)"]
        subgraph core_data["core_data schema"]
            schools["schools (UUID, contract_status)"]
            students["students (UUID, age_band, gender_category)"]
            classes
            sessions["test sessions"]
            clips
            approved_results["results (approved)"]
            bib_assignments
            jurisdiction_config
        end
        subgraph identity["identity schema"]
            student_identities["student_identities\n(name, DOB, grade, gender, external IDs)"]
            school_identities["school_identities\n(name, district, province)"]
            user_identities["user_identities\n(email, name)"]
        end
        subgraph consent_schema["consent schema"]
            consent_records
            audit_log
        end
    end

    subgraph PipelineDB["Pipeline DB (PostgreSQL)"]
        raw_detections["raw detections"]
        tracks
        poses
        ocr_readings["OCR readings"]
        calibration_data["calibration data"]
        pipeline_results["pipeline results (raw)"]
        stage_cache["stage cache"]
    end

    subgraph GCS["GCS / S3"]
        raw_video["raw video files"]
        annotated_video["annotated videos"]
    end

    subgraph ZITADEL
        identities["user identities"]
        organizations
        credentials
    end

    subgraph OpenFGA
        relationship_tuples["relationship tuples\nwho can access what"]
    end

    subgraph Redis
        celery_queue["Celery task queue"]
        task_state["task state / progress"]
        ephemeral_cache["ephemeral caching"]
    end
```

**Ownership rules:**

- **Application API** owns all three schemas: `core_data` (schools, students as UUID-keyed records, classes, sessions, clips, results, bib_assignments, jurisdiction_config), `identity` (student_identities, school_identities, user_identities — Layer 2 PII), and `consent` (consent_records, audit_log).
- **Pipeline API** owns: raw detections, tracks, poses, OCR readings, calibration data, raw pipeline results, stage cache.
- **GCS** holds: raw video, annotated video (written by pipeline workers).
- **ZITADEL** owns: user identities, organizations, credentials. Application DB stores a `zitadel_id` foreign reference.
- **OpenFGA** owns: all authorization relationship tuples.
- **Redis** holds: Celery task queue, task state, pipeline stage progress, ephemeral caches. All data is transient.

---

## 5. Result Approval Flow

When the pipeline completes, results flow through a structured ingestion and approval process. This aligns with the result ingestion defined in [08-pipeline-integration.md](./08-pipeline-integration.md).

```mermaid
sequenceDiagram
    participant Pipeline as Pipeline API
    participant App as Application API
    participant DB as Application DB
    participant Teacher

    App->>Pipeline: GET /results/{job_id}
    Pipeline-->>App: {status: complete, results: [TestResult...]}

    Note over App: Each TestResult carries: student_bib,<br/>metric_value, confidence_score, flags

    App->>App: For each TestResult:<br/>Look up BibAssignment(session_id, bib_number)<br/>to resolve student_id

    App->>App: For each resolved student_id:<br/>verify active METRIC_PROCESSING consent.<br/>Results for students without consent are discarded.

    App->>App: Resolved bibs (student_bib >= 1 with BibAssignment match<br/>and active METRIC_PROCESSING consent)<br/>create Result with student_id populated

    App->>App: Unresolved bibs (student_bib = -1 or no BibAssignment match)<br/>create Result with student_id = NULL, flagged for manual review

    App->>App: Low-confidence results (confidence < threshold)<br/>flagged for teacher review regardless of bib match

    App->>DB: INSERT Result records (approved = false)
    App->>DB: UPDATE TestSession SET status = review

    Teacher->>App: Open Results Processing screen
    App->>Teacher: Display results grouped by confidence:<br/>high-confidence matches, low-confidence, unresolved

    loop For each result
        alt High confidence, correct match
            Teacher->>App: Approve
        else Low confidence or mismatch
            Teacher->>App: Manually select correct student or reject
        else Unresolved bib
            Teacher->>App: Manually assign student
        end
    end

    Note over Teacher,App: Bulk action: Approve All High Confidence<br/>approves results with confidence > threshold

    Teacher->>App: Commit approved results
    App->>DB: UPDATE Result SET approved = true,<br/>approved_by = teacher_user_id
    App->>DB: UPDATE TestSession SET status = complete
    App->>App: Results linked to student profiles
```

**Key details:**

- **BibAssignment** is the bridge between pipeline output (bib numbers) and application data (named students). See [01-domain-model.md](./01-domain-model.md) for the bib assignment workflow.
- **Confidence-based flagging**: The pipeline attaches a `confidence_score` (0.0-1.0) and `flags` array (e.g. `["low_confidence", "partial_occlusion"]`) to each result. Low-confidence results are flagged for manual review even if the bib resolved successfully.
- **Unresolved bibs**: When `student_bib = -1` or there is no matching `BibAssignment` for the session, the result is created with `student_id = NULL` and must be manually assigned by the teacher.
- **Rejected results** can be reassigned to a different student, discarded, or left unresolved.

---

## 6. Data Aggregation Flow

Data aggregates upward through progressive levels, with PII stripped at each boundary.

```mermaid
flowchart BT
    A["Individual Results\n(per test, per attempt)\nTier 1 — UUID + raw scores"] --> B["Student Profile View\nTier 2 — enriched at API boundary\nLayer 1 results + Layer 2 identity"]
    B --> D["Class Averages\ncoach dashboard\nk-anonymity: k≥5"]
    D --> E["School Metrics\nschool head dashboard\nk-anonymity: k≥10"]
    E --> F["District Metrics\nk-anonymity: k≥20"]

    style A fill:#e8f4f8
    style B fill:#d1ecf1
    style D fill:#a2cdff
    style E fill:#7eb8ff
    style F fill:#5a9fef
```

At each aggregation level:

- **Individual Results** — raw metric values per test attempt, linked to a student via approved Result records. Stored as UUID + raw scores only (Tier 1, Layer 1).
- **Student Profile View** — an enrichment operation, NOT a stored entity containing "full PII." Layer 1 results (UUIDs + scores) are enriched with Layer 2 identity (names) at the API boundary (Tier 2) for display. PII and results are never co-located in storage. Visible to teacher and parent.
- **Class Averages** — aggregated from student test results. No individual student names. Groups with fewer than 5 students are suppressed (k-anonymity threshold k≥5). Visible to coach and school head.
- **School Metrics** — school-wide averages, grade breakdowns, participation rates, at-risk counts. Groups with fewer than 10 students are suppressed (k≥10). Visible to school head.
- **District Metrics** — cross-school aggregation. Groups with fewer than 20 students are suppressed (k≥20). Visible to district administrators.

> **Scoring engine note:** Only raw scores are stored in the data layer. Categorical labels (e.g. "above average"), percentiles, and risk flags are computed in the presentation layer (client app), not stored.

---

## 7. Video Data Flow

Video upload follows the **task-before-upload pattern (Option B)**, a resolved architectural decision (see [00-system-overview.md](./00-system-overview.md)). The API creates a Clip record and returns both a clip ID and a signed GCS URL in one response. The client uploads directly to cloud storage. No video bytes pass through the Application API.

```mermaid
sequenceDiagram
    participant Phone as Teacher Phone
    participant AppAPI as Application API
    participant GCS as GCS Bucket
    participant PipeAPI as Pipeline API

    Phone->>Phone: Record video (60fps, 4K)

    Phone->>AppAPI: POST /sessions/{id}/clips<br/>{test_type, metadata}
    Note over AppAPI: Create Clip record (status: pending)<br/>Generate signed GCS upload URL
    AppAPI-->>Phone: {clip_id, upload_url (signed)}

    Phone->>GCS: PUT video directly via signed URL<br/>(no bytes through the API)
    GCS-->>Phone: 200 OK

    Phone->>AppAPI: PATCH /sessions/{id}/clips/{clip_id}<br/>{status: uploaded}

    Note over AppAPI: Stage 0: Audio stripped and GPS/device<br/>metadata removed via FFmpeg at ingestion,<br/>before pipeline processing

    Note over AppAPI: Confirm upload, submit job to pipeline
    AppAPI->>PipeAPI: POST /upload<br/>{video_path (GCS URI), test_type}
    PipeAPI-->>AppAPI: {job_id}
    Note over AppAPI: Store job_id on Clip record

    PipeAPI->>GCS: Pull video from GCS (africa-south1)
    Note over PipeAPI: Ephemeral GPU VM (European region):<br/>video processed in memory/tmpfs,<br/>local copy auto-purged on completion.<br/>Never permanently stored outside region.
    PipeAPI->>PipeAPI: Process through 8-stage pipeline
    PipeAPI->>GCS: Write annotated video to GCS

    Note over Phone,GCS: Annotated video playback
    Phone->>AppAPI: GET /sessions/{id}/annotated-video
    AppAPI->>GCS: Generate signed URL for annotated video
    AppAPI-->>Phone: Signed URL (time-limited)
    Phone->>GCS: Stream video directly via signed URL
```

**Key points:**

- **Signed URLs only** — all GCS access (upload and download) uses time-limited signed URLs generated by the Application API. No public buckets.
- **Client confirms upload** — the client sends a PATCH to confirm the upload is complete. This triggers pipeline job submission. There is no GCS-to-API notification; the client is the source of truth for upload completion.
- **Task handle always available** — because the Clip record is created before the upload, the client always has a clip ID to track status. Orphaned uploads (started but never confirmed) are detectable and recoverable.
- **Metadata stripping (Stage 0)** — on ingestion, before pipeline processing, audio is stripped and GPS/device metadata is removed via FFmpeg. The sanitised video is what enters the pipeline.
- **Ephemeral GPU processing** — video is pulled from GCS (africa-south1) to an ephemeral GPU VM in a European region. Processing occurs in memory/tmpfs. Metrics are returned to the Application DB, and the local video copy is auto-purged on VM completion. Video is never permanently stored outside the source region.
- **Annotated video** is written to GCS by the pipeline workers and served to clients via signed URLs generated by the Application API.

---

## 8. Tier 1 / Tier 2 Boundary Annotations

Operations in the data flow are split across two API tiers:

| Operation | Tier | Data Accessed |
|-----------|------|---------------|
| Result ingestion (bib → student_id resolution) | Tier 1 | UUID-keyed records only (`core_data` schema) |
| Consent verification at recording and ingestion | Cross-cutting middleware (pre-tier) | `consent` schema (no PII) — runs before tier-specific logic |
| Pipeline submission and progress tracking | Tier 1 | Clip records, job IDs |
| Dashboard aggregation (class/school/district) | Tier 1 | Aggregated scores by UUID |
| Teacher review screen (display student names alongside results) | Tier 2 | Enriches Layer 1 UUIDs with Layer 2 student names from `identity` schema |
| Parent view (child's results with name) | Tier 2 | Enriches Layer 1 results with Layer 2 identity |
| Admin user management | Tier 2 | `identity.user_identities` |

Tier 2 enrichment happens at the API boundary — the response joins Layer 1 and Layer 2 data for display, but they remain in separate schemas in storage.

---

## 9. Consent Withdrawal Flow

When consent is withdrawn for a student, the system executes cascading actions depending on the consent type:

**VIDEO_CAPTURE withdrawn:**
- Delete all retained video (raw and annotated) in GCS for clips where the student was a bib-assigned participant.
- Automatically withdraw dependent consents: `METRIC_PROCESSING` and `MODEL_TRAINING`.
- Flag the student for exclusion from future video captures (student cannot be assigned a bib until consent is re-granted).

**METRIC_PROCESSING withdrawn:**
- Approved results linked to the student remain but are marked as `consent_withdrawn` and excluded from aggregation and dashboards.
- Future pipeline results for this student are discarded at ingestion (see consent verification gate in Section 5).

**IDENTITY_STORAGE withdrawn:**
- Delete the student's Layer 2 record (`identity.student_identities`).
- Layer 1 data (`core_data.students` UUID, age_band, gender_category, and any linked results) becomes orphaned/anonymous — it can no longer be linked to a named individual.

**ALL consent withdrawn:**
- Execute all of the above.
- Additionally, delete the Layer 1 student record and all linked results from `core_data`.
- Generate a deletion confirmation record in `consent.audit_log` with timestamp and scope of deletion.

> **Note:** Consent withdrawal is recorded in `consent.audit_log` with the withdrawing party, timestamp, consent type, and resulting actions taken. Withdrawal is processed asynchronously via a background job to handle cascading deletions across GCS and database schemas.

---

## 10. Open Questions

- **Audit trail for result changes** — Do we need event sourcing for result changes? At minimum we need an audit log of who approved/rejected each result and when. Full event sourcing may be overkill for the POC.
- **Result aggregation trigger** — Should dashboard data be recomputed synchronously on approval or via an async job? Synchronous is simpler but could slow down the approval commit for large classes. Async via Celery is more robust but adds latency before dashboards update.

### Resolved

| Question | Resolution | Reference |
|----------|-----------|-----------|
| Raw pipeline results in Application DB? | Raw pipeline results stay in the Pipeline DB. The Application DB stores only ingested Result records (pre-approval and approved). Raw results can be re-fetched via `GET /results/{job_id}` if re-review is needed. | [08-pipeline-integration.md](./08-pipeline-integration.md) |
| Upload flow pattern | Task before upload (Option B). API creates Clip + signed URL, client uploads directly to GCS, client confirms, processing starts. | [00-system-overview.md](./00-system-overview.md) |
| Real-time pipeline progress vs polling | Polling for MVP. WebSocket/pub-sub as future enhancement. | [08-pipeline-integration.md](./08-pipeline-integration.md) |
| Video retention policy | 0–90 days hot (GCS Standard), then cold (Nearline/Coldline). Deleted when linked metrics are deleted or on consent withdrawal. No fixed maximum — configurable per jurisdiction via `jurisdiction_config.video_max_retention_days`. | [07-infrastructure.md](./07-infrastructure.md) |

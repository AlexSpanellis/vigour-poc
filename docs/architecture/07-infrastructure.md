# Infrastructure

## Overview

The Vigour platform runs on Google Cloud Platform. **All application infrastructure is deployed to `africa-south1` (Johannesburg)** to comply with POPIA data residency requirements. The only exception is GPU processing, which runs on ephemeral VMs in a European region (see [Ephemeral Cross-Region GPU Processing](#ephemeral-cross-region-gpu-processing) below).

The existing POC already provisions a GPU VM, Cloud SQL, Cloud Storage, and Memorystore (Redis) via Terraform (`infra/main.tf`). The full platform adds three services on top of this foundation:

- **ZITADEL** -- OIDC-based authentication provider (see [03-authentication.md](./03-authentication.md))
- **OpenFGA** -- relationship-based authorization service (see [04-authorization.md](./04-authorization.md))
- **Application API** -- public-facing API serving web and mobile clients (see [02-api-architecture.md](./02-api-architecture.md))

All other infrastructure (Pipeline API, Celery workers, PostgreSQL, Redis, GCS) carries forward from the POC with changes noted below -- primarily network hardening, separate database schemas, and distinct GCS buckets.

---

## Service Map

```mermaid
graph TD
    subgraph Public
        CLB[Cloud Load Balancer]
        ZIT[ZITADEL<br/>OIDC Provider]
    end

    subgraph VPC["GCP VPC — africa-south1 (Private Network)"]
        APP[Application API<br/>Cloud Run / Compute Engine]
        FGA[OpenFGA<br/>Cloud Run]
        PIPE[Pipeline API<br/>Compute Engine]
        APP_DB[("Application DB<br/>core_data / identity / consent<br/>(PostgreSQL)")]
        PIPE_DB[("Pipeline DB<br/>vigour_pipeline<br/>(PostgreSQL)")]
        REDIS[(Redis<br/>Memorystore)]
        GCS[(GCS<br/>Cloud Storage)]
    end

    subgraph GPU_REGION["Ephemeral GPU Region (Europe)"]
        CELERY[Celery Worker<br/>Ephemeral GPU VM<br/>g2-standard-4 / L4]
    end

    CLB --> APP
    CLB --> ZIT

    APP -->|Validate tokens| ZIT
    APP -->|Check permissions| FGA
    APP -->|Submit jobs, poll status, fetch results| PIPE
    APP -->|Domain CRUD, result approval| APP_DB
    APP -->|Caching, session state| REDIS
    APP -->|Signed URLs| GCS

    FGA -->|openfga schema| APP_DB

    PIPE -->|Task management| REDIS
    PIPE -->|Pipeline cache, stage outputs| PIPE_DB

    CELERY -->|Task queue, progress updates| REDIS
    CELERY -->|Read/write video| GCS
    CELERY -->|Pipeline cache, stage outputs| PIPE_DB

    ZIT -->|zitadel schema| APP_DB
```

> **Note**: Application DB and Pipeline DB are shown separately to match the system overview. Application DB hosts three schemas (`core_data`, `identity`, `consent`) plus `zitadel` and `openfga`. Pipeline DB hosts `vigour_pipeline`. In practice these may be separate schemas within a single Cloud SQL instance or separate instances -- see [Database Strategy](#database-strategy) below.

---

## Environment Strategy

The environment strategy follows a phased approach aligned with commercial traction:

### Phase 1 — MVP Pilot (Option A: Production + Local Dev)

A single GCP production environment in `africa-south1` plus local Docker Compose development. All development and testing happens locally using the 7-service Docker Compose stack (which faithfully replicates the production topology). Deploy directly to production when ready.

**When this works**: Solo developer or small team, infrequent releases, pilot schools only.

**Move to Phase 2 when**: Paying clients are on the platform and deploying directly to production becomes too risky.

### Phase 2 — Growth (Option B: Production + Ephemeral Staging)

Production remains always-on. A staging environment is spun up on-demand via Terraform (`terraform apply -var="env=staging"`) with smaller instance sizes, used for pre-release validation, then torn down. Staging cost when off: $0. Staging cost when on: ~$100–150/mo (smaller instances, no GPU unless testing pipeline).

**When to use staging**: Pre-release validation, testing ZITADEL with real DNS/SSL, database migration dry-runs, QA by someone other than the developer.

**Terraform parameterisation**: The Terraform configuration must support an `env` variable that controls instance sizes, naming, and network configuration so that `staging` and `production` are the same topology at different scales.

### Environment Tiers

| Tier | Platform | GPU | Application API | Notes |
|------|----------|-----|-----------------|-------|
| **Local Dev** | Docker Compose | None (CPU-only ML) | Single container | All 7 services containerised locally |
| **Staging** (Phase 2) | GCP | None (or smaller GPU on demand) | Single instance | Ephemeral — spun up via Terraform, torn down after use |
| **Production** | GCP | L4 (g2-standard-4) | Autoscaling (Cloud Run) | Full spec, VPC-native, `africa-south1` |

---

## Docker Compose (Local Dev)

All services run locally via Docker Compose for development. CPU-only ML inference keeps the GPU requirement out of the dev loop.

| Service | Image / Build | Port | Depends On |
|---------|--------------|------|------------|
| `postgres` | `postgres:15` | `5432:5432` | -- |
| `redis` | `redis:7` | `6379:6379` | -- |
| `zitadel` | `ghcr.io/zitadel/zitadel` | `8080:8080` | `postgres` |
| `openfga` | `openfga/openfga` | `8081:8081` | `postgres` |
| `app-api` | Build from `./app-api` | `8000:8000` | `postgres`, `redis`, `zitadel`, `openfga` |
| `pipeline-api` | Build from `./pipeline-api` | `8001:8001` | `postgres`, `redis` |
| `worker` | Build from `./pipeline-api` | -- | `redis`, `postgres` |

The single `postgres` container hosts all six schemas (`core_data`, `identity`, `consent`, `vigour_pipeline`, `zitadel`, `openfga`) initialised by an entrypoint script or SQL init files mounted into `/docker-entrypoint-initdb.d/`.

For development, **ZITADEL Cloud** can be used instead of the self-hosted container to simplify the local stack. In that case, remove the `zitadel` service and point `app-api` at the ZITADEL Cloud endpoint via `ZITADEL_ISSUER_URL`.

---

## GCP Production Architecture

```mermaid
graph LR
    CLIENT[Clients<br/>Web / Mobile] --> CLB[Cloud Load Balancer]

    CLB --> APP[Application API<br/>Cloud Run<br/>autoscaling 0-N]
    CLB --> ZIT[ZITADEL<br/>Cloud Run / Dedicated VM]

    subgraph VPC["VPC — africa-south1 (Private Network)"]
        APP -->|Domain CRUD| APP_DB[("Cloud SQL<br/>core_data / identity / consent<br/>Private IP")]
        APP -->|Caching| REDIS[("Memorystore<br/>Redis<br/>Private IP")]
        APP -->|Signed URLs| GCS[("GCS<br/>vigour-videos<br/>africa-south1")]
        APP -->|Permission checks| FGA[OpenFGA<br/>Cloud Run]
        APP -->|Submit jobs, poll results| PIPE[Pipeline API<br/>Compute Engine]
        APP -->|Validate tokens| ZIT

        ZIT -->|zitadel schema| APP_DB
        FGA -->|openfga schema| APP_DB

        PIPE -->|Pipeline cache| PIPE_DB[("Cloud SQL<br/>vigour_pipeline schema<br/>Private IP")]
        PIPE -->|Task management| REDIS
    end

    subgraph GPU_REGION["Ephemeral GPU Region (Europe)"]
        CELERY[Celery Worker<br/>Ephemeral GPU VM<br/>g2-standard-4 / L4]
    end

    CELERY -->|Task queue| REDIS
    CELERY -->|Read/write video| GCS
    CELERY -->|Stage outputs| PIPE_DB
```

Key points:

- All application infrastructure is in `africa-south1` (Johannesburg).
- Only the Application API and ZITADEL are publicly reachable (via the load balancer).
- Pipeline API, OpenFGA, PostgreSQL, Redis, and GCS are internal to the VPC.
- The Pipeline API orchestrates jobs but does not require a GPU; it remains in `africa-south1`.
- Celery workers run on ephemeral GPU VMs in a European region (GPUs are not available in `africa-south1`). See [Ephemeral Cross-Region GPU Processing](#ephemeral-cross-region-gpu-processing).
- Celery workers read raw video from GCS, process in memory/tmpfs, write annotated video back to GCS, and persist stage outputs to the Pipeline DB.

---

## Database Strategy

A single Cloud SQL (PostgreSQL 15) instance in `africa-south1` hosts multiple logical databases or schemas, organised into three application layers plus infrastructure schemas:

| Database / Schema | Layer | Owner / Role | Purpose |
|-------------------|-------|-------------|---------|
| `core_data` | Layer 1 — Anonymised domain | `role_core_data` | Anonymised domain entities: schools (UUIDs only), students (UUIDs with `age_band` / `gender_category`), sessions, clips, results, `jurisdiction_config` |
| `identity` | Layer 2 — PII | `role_identity` | Student and school PII (names, contact details), user PII. All PII columns encrypted at rest using Cloud KMS keys. MVP uses a single KMS key; per-jurisdiction keys are Phase 2+. |
| `consent` | Layer 3 — Consent & audit | `role_consent` | Consent records, consent withdrawal events, audit trail for data subject access requests (DSARs) |
| `vigour_pipeline` | Infrastructure | `role_pipeline` | Pipeline data: detections, tracks, poses, OCR readings, calibration data, stage cache (existing POC schema) |
| `zitadel` | Infrastructure | `role_zitadel` | ZITADEL-managed auth tables (identity, orgs, sessions, keys) |
| `openfga` | Infrastructure | `role_openfga` | OpenFGA-managed authorization tuples and model definitions |

Each schema has a dedicated PostgreSQL role with access limited to its own tables. **No cross-schema read permissions are granted.** Application code must explicitly join data across layers via separate queries, enforcing the separation at the database level.

**Rationale for single instance**: The POC Terraform (`infra/main.tf`) already provisions a single `db-f1-micro` Cloud SQL instance. For the initial production deployment, a single instance (upgraded to a larger tier) keeps costs low and operational overhead minimal. The schema-level separation provides logical isolation.

**Alternative**: Separate Cloud SQL instances per concern (app, pipeline, auth). This increases isolation and enables independent scaling at the cost of higher spend and more operational overhead.

**Decision**: Single instance is the starting point. Split later if isolation, performance, or compliance demands it. This aligns with the system overview's position: "Application DB and Pipeline DB may be separate schemas within a single PostgreSQL instance or separate instances entirely."

---

## GCS Bucket Structure

```
vigour-videos/
  raw/{school_id}/{session_id}/{clip_id}.mp4
  annotated/{school_id}/{session_id}/{clip_id}_annotated.mp4
```

The path structure includes `school_id` to support per-school access auditing and future per-school lifecycle policies.

**Video flow** (aligned with [06-data-flow.md](./06-data-flow.md)):

1. Teacher uploads raw video to `vigour-videos/raw/...` via signed URL from Application API.
2. **Stage 0 — Metadata stripping**: Audio is stripped and GPS/device metadata (EXIF) is removed from the video file at ingestion before pipeline processing. This is implemented via FFmpeg. The video creation timestamp from EXIF may be preserved as a cross-check against the session record.
3. Celery worker downloads stripped video from GCS, processes it through the 8-stage pipeline on an ephemeral GPU VM.
4. Celery worker writes annotated video back to `vigour-videos/annotated/...`.
5. Clients request annotated video via signed URL from Application API.

**Lifecycle policies**:

| Object type | Retention | Notes |
|-------------|-----------|-------|
| Raw video | 0–90 days: GCS Standard (hot). 90+ days: GCS Nearline then Coldline (cold). Deleted when linked metrics are deleted or on consent withdrawal. | No fixed maximum retention — configurable per jurisdiction via `jurisdiction_config.video_max_retention_days`. |
| Annotated video | Same lifecycle as raw video — hot for 90 days, then cold. Deleted with linked metrics or on consent withdrawal. | Annotated video follows the same retention policy as its source raw video. |

**Access control**: All objects are private. Clients receive time-limited signed URLs from the Application API. No public access is enabled on any bucket.

**Transition from POC**: The POC Terraform provisions a single bucket (`${project}-vigour-poc`) with a 30-day delete lifecycle. Production uses `vigour-videos` with the retention policies above and removes `force_destroy`.

---

## Ephemeral Cross-Region GPU Processing

GPUs (L4, T4) are **not available in `africa-south1`**. Video processing therefore runs on ephemeral GPU VMs in a European region (e.g., `europe-west4`). The Pipeline API itself remains in `africa-south1` — it orchestrates jobs but does not perform GPU-intensive work. Only the Celery worker needs the GPU.

> **Note**: The specific GPU region is an infrastructure decision. ADR-017 documents the ephemeral processing pattern; the region choice is determined by GPU availability and pricing.

### Data flow

1. Raw video is stored permanently in GCS in `africa-south1`.
2. When a processing job starts, the Celery worker on the ephemeral GPU VM pulls the video from GCS to local tmpfs / memory.
3. Processing occurs entirely in memory or on tmpfs. No persistent local copy of the video is retained.
4. Results (annotated video, stage outputs) are written back to GCS (`africa-south1`) and the Pipeline DB.
5. On job completion (or failure), the local video copy is auto-purged from the ephemeral VM.

### Network controls

- GPU VM egress is restricted via firewall rules to **only** the originating GCS bucket and the application Cloud SQL instance. No other outbound traffic is permitted.
- The GPU VM has no public IP; egress to GCS uses Private Google Access or a Cloud NAT gateway scoped to the required endpoints.

### Audit logging

- Each cross-region data transfer (video pull from GCS, results push to GCS/DB) is audit-logged with job ID, timestamp, source region, destination region, and data size.
- GPU VM lifecycle events (creation, processing start/end, destruction) are logged for compliance traceability.

---

## Environment Variables

### Application API

| Variable | Example | Required | Description |
|----------|---------|----------|-------------|
| `APP_DATABASE_URL` | `postgresql://app:pass@localhost:5432/vigour` | Yes | Application DB connection string (schemas: `core_data`, `identity`, `consent`) |
| `REDIS_URL` | `redis://localhost:6379/0` | Yes | Redis for caching and session state |
| `ZITADEL_ISSUER_URL` | `https://auth.vigour.app` | Yes | ZITADEL OIDC issuer for JWT validation |
| `ZITADEL_CLIENT_ID` | `vigour-app-client` | Yes | OIDC client ID |
| `OPENFGA_API_URL` | `http://openfga:8081` | Yes | OpenFGA gRPC/HTTP endpoint |
| `OPENFGA_STORE_ID` | `01H...` | Yes | OpenFGA store identifier |
| `PIPELINE_API_URL` | `http://pipeline-api:8001` | Yes | Internal Pipeline API base URL |
| `GCS_VIDEO_BUCKET` | `vigour-videos` | Yes | GCS bucket for raw + annotated video |
| `GCP_PROJECT` | `vigour-prod` | Yes (GCP) | GCP project ID |
| `GOOGLE_APPLICATION_CREDENTIALS` | `/secrets/sa-key.json` | Yes (GCP) | Service account key path (not needed for Cloud Run with Workload Identity) |

### Pipeline API / Workers

| Variable | Example | Required | Description |
|----------|---------|----------|-------------|
| `PIPELINE_DATABASE_URL` | `postgresql://pipeline:pass@localhost:5432/vigour_pipeline` | Yes | Pipeline DB connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Yes | Redis for Celery broker and result backend |
| `GCS_VIDEO_BUCKET` | `vigour-videos` | Yes (GCP) | GCS bucket for video read/write |
| `UPLOAD_DIR` | `/tmp/vigour_uploads` | No | Temp video storage (local dev) |
| `OUTPUT_DIR` | `data/annotated` | No | Annotated video output (local dev) |
| `CONFIGS_DIR` | `configs/test_configs` | No | Test geometry configs |
| `CACHE_DIR` | `data/cache` | No | Pipeline cache root |
| `DEFAULT_FPS` | `15` | No | Default ingestion FPS |
| `DEVICE` | `cuda` | No | `cuda` or `cpu` |
| `ENABLE_POSE` | `1` | No | Global pose stage toggle |
| `ENABLE_OCR` | `1` | No | Global OCR stage toggle |
| `PIPELINE_FORCE_RERUN` | `0` | No | Bypass all caches |

### ZITADEL

| Variable | Example | Description |
|----------|---------|-------------|
| `ZITADEL_DATABASE_POSTGRES_HOST` | `postgres` | PostgreSQL host |
| `ZITADEL_DATABASE_POSTGRES_DATABASE` | `zitadel` | Database / schema name |
| `ZITADEL_EXTERNALDOMAIN` | `auth.vigour.app` | Public-facing domain |
| `ZITADEL_MASTERKEY` | `...` | Encryption master key (secret) |

### OpenFGA

| Variable | Example | Description |
|----------|---------|-------------|
| `OPENFGA_DATASTORE_ENGINE` | `postgres` | Storage backend |
| `OPENFGA_DATASTORE_URI` | `postgresql://openfga:pass@postgres:5432/openfga` | Connection string |

---

## POC to Production Migration

The POC Terraform (`infra/main.tf`) provisions minimal resources. The production deployment extends this:

| Concern | POC | Production |
|---------|-----|------------|
| **Cloud SQL** | `db-f1-micro`, public IP (`0.0.0.0/0`) | `db-custom-2-7680` or larger, private IP only, SSL required |
| **GCS** | Single bucket, 30-day delete, `force_destroy = true` | `vigour-videos` bucket, tiered retention, `force_destroy = false` |
| **Redis** | `BASIC` tier, 1 GB | `STANDARD_HA` tier for failover |
| **GPU VM** | Public IP, default network | Private IP, custom VPC, no external access |
| **Application API** | Not provisioned | Cloud Run with VPC connector, autoscaling 0-N |
| **ZITADEL** | Not provisioned | Cloud Run or dedicated VM (see open questions) |
| **OpenFGA** | Not provisioned | Cloud Run |
| **Load Balancer** | Not provisioned | Cloud HTTPS Load Balancer with managed SSL cert |
| **Networking** | Default VPC, public IPs | Custom VPC, private service access, Cloud NAT for egress |

---

## Scaling Considerations

| Component | Scaling Model | Notes |
|-----------|--------------|-------|
| **Application API** | Horizontal, stateless | Cloud Run auto-scales 0 to N instances based on request volume |
| **Pipeline API** | Vertical, GPU-bound | One job at a time per GPU; excess jobs queue in Redis/Celery |
| **Celery Workers** | Horizontal (add GPU VMs) | Celery distributes jobs across workers; add VMs as processing demand grows |
| **ZITADEL** | Single instance initially | Lightweight at initial scale; scale if auth traffic warrants it |
| **OpenFGA** | Single instance initially | Authorization checks are fast cached lookups |
| **PostgreSQL** | Managed (Cloud SQL) | Vertical scaling by instance tier; add read replicas if needed |
| **Redis** | Managed (Memorystore) | Scale tier as needed; used for Celery broker, task state, and short-lived caching |

The GPU is the primary bottleneck. Each L4 processes one video clip at a time across the 8-stage pipeline. If a school uploads 30 clips in a session and each takes ~60 seconds, the queue drains in ~30 minutes on a single GPU. Adding a second GPU VM halves that.

---

## Monitoring & Observability

### Structured Logging

- Cloud Logging aggregates logs from all services (Cloud Run, Compute Engine, Cloud SQL).
- Application API emits structured JSON logs with a **correlation ID** per request.
- When the Application API calls the Pipeline API, it forwards the correlation ID in an `X-Correlation-ID` header. The Pipeline API and Celery workers include this ID in their own log entries, enabling end-to-end request tracing across the two-tier API boundary.
- Pipeline API logs per-stage timing and status for each job.

### Metrics (Cloud Monitoring)

- CPU, memory, and request latency for the Application API (Cloud Run metrics).
- GPU utilisation, GPU memory, and Celery job queue depth for the Pipeline VM.
- Database connections, query latency, and replication lag (if replicas are added).
- Redis memory usage and command rates.
- OpenFGA check latency (p50, p99) and error rate.
- ZITADEL authentication success/failure rates.

### Compliance Audit Logging

Beyond operational metrics, the system maintains compliance-specific logs that are retained separately and are not subject to standard log rotation:

- **Consent events**: consent granted, withdrawn, or modified, with timestamp, subject, and actor.
- **DSAR actions**: data subject access requests received, fulfilled, or denied.
- **Data deletions**: records and video files deleted (including reason — e.g., consent withdrawal, retention expiry).
- **Video access**: all access to video objects in GCS, especially cold storage (Nearline/Coldline) retrieval events.
- **Cross-region data transfers**: every video pull from `africa-south1` to the ephemeral GPU region, logged with job ID, data size, and timestamps.

These logs support POPIA compliance audits and must be queryable independently of operational logging.

### Alerting

- Pipeline job failure rate exceeds threshold.
- Authentication failure spikes (potential brute force) -- aligns with rate limiting in [03-authentication.md](./03-authentication.md).
- Application API error rate (5xx) exceeds threshold.
- GPU VM unresponsive or out of memory.
- Cloud SQL connection pool exhaustion.
- Redis memory utilisation above 80%.

---

## Cost Model (Estimates)

All estimates are for `africa-south1` unless noted. GPU costs assume `europe-west4` ephemeral VMs.

### MVP Pilot (Phase 1 — Option A: single production environment)

| Resource | Spec | ~Monthly USD |
|----------|------|-------------|
| Cloud SQL (PostgreSQL 15) | `db-custom-2-7680`, 20 GB SSD | $70–90 |
| Memorystore (Redis) | BASIC 1 GB | ~$35 |
| Cloud Run (App API) | Min 0, avg 1 instance | $5–20 |
| Cloud Run (ZITADEL) | 1 always-on instance | $15–30 |
| Cloud Run (OpenFGA) | Min 0 | $5–10 |
| Compute Engine (Pipeline API) | e2-small, always-on | ~$15 |
| GPU VM (Celery worker) | g2-standard-4 + L4, ephemeral | ~$1.50/hr when running |
| GCS | Minimal at pilot scale | $1–5 |
| Load Balancer + managed SSL | — | ~$20 |
| **Base total (excl. GPU)** | | **~$170–210/mo** |
| **GPU** (e.g. 2 hrs/day avg) | | **+~$90/mo** |
| **Estimated MVP total** | | **~$260–300/mo** |

### Scaling Estimates

| Scale | Schools | GPU hrs/mo (est.) | Storage | Approx. total/mo |
|-------|---------|-------------------|---------|-------------------|
| Pilot | 1–5 | 20–40 | < 50 GB | $260–350 |
| Early growth | 10–30 | 60–150 | 50–200 GB | $350–550 |
| Scale | 100+ | 300+ | 500 GB+ | $800+ (add GPU VMs, scale Cloud SQL) |

> These are rough estimates based on March 2026 GCP pricing. Actual costs depend on GPU utilisation patterns, video volume, and egress. A detailed cost model should be built once pilot usage data is available.

---

## Open Questions

| # | Question | Context | Status |
|---|----------|---------|--------|
| 1 | Cloud Run vs GKE for the Application API? | Cloud Run is simpler and cheaper at low scale. GKE offers more control if the service mesh grows. | Open |
| 2 | Self-hosted ZITADEL vs ZITADEL Cloud? | Self-hosted in `africa-south1`. See ADR-013. Staff identity data (email, name) is PII that must be resident in-region for POPIA compliance. | Resolved |
| 3 | CDN for annotated video delivery? | Cloud CDN in front of GCS could reduce latency for repeat views. Cost vs. benefit depends on access patterns. | Open |
| 4 | Estimated monthly cost at 10 / 100 / 1,000 schools? | Rough estimates added above. Refine with real pilot usage data. | Partially resolved |
| 5 | Environment strategy? | Phase 1 (Option A): single production + local dev. Phase 2 (Option B): add ephemeral staging when paying clients are on the platform. | Resolved |

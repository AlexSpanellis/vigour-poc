# Technology Decisions (Architecture Decision Records)

This document captures every significant technology decision for the Vigour Platform. Each ADR records the context, alternatives evaluated, rationale, and consequences of the decision. ADRs are numbered sequentially and are append-only -- decisions are superseded, not deleted.

---

## ADR-001: ZITADEL for Authentication

**Status**: Accepted
**Date**: 2025-03-19

**Context**: The Vigour platform requires an OIDC-compliant identity provider that supports multi-tenant isolation (one org per school), passwordless login (magic link / email code), SSO federation (Google Workspace / Microsoft 365), contract-based onboarding (no self-signup), and role claims embedded in JWTs. The platform handles minor students' PII under POPIA, so data residency and control over the identity layer matter. The team is small (1-2 developers) and cannot afford to build or maintain a custom auth system.

**Decision**: Use ZITADEL as the OIDC provider for all authentication.

**Alternatives Considered**:

| Alternative | Pros | Cons |
|---|---|---|
| **Auth0** | Mature, excellent SDKs (including Expo), magic links built-in, Organizations feature for multi-tenancy, HIPAA/SOC2 compliance | Expensive at scale -- pricing jumps quickly past free tier ($150+/month for B2B with SSO). Vendor lock-in. Data hosted outside South Africa (POPIA concern for minors' data). No self-hosting option. |
| **Keycloak** | Battle-tested, self-hostable, full OIDC/SAML, Red Hat / CNCF backing, free forever | Magic links not native (requires custom SPI or extension). UI is dated and clunky. Heavy Java stack -- resource-hungry for a small deployment. Complex initial setup. |
| **SuperTokens** | Open-source, self-hostable, passwordless built-in, simple developer experience | Weaker multi-tenancy story. Smaller community and ecosystem. Less mature than Keycloak or ZITADEL. Limited SSO federation options. |
| **Custom (JWT + email codes)** | Full control, no dependencies, zero licence cost | Enormous surface area to get right: token signing, refresh flows, rate limiting, brute force protection, session management, MFA. Ongoing maintenance burden. Security risk from a small team building auth from scratch. |

**Rationale**:
- **Multi-tenancy is first-class**: ZITADEL Organizations map directly to schools -- one org per school, with built-in isolation. Auth0 has this too (Organizations feature), but at a higher price tier.
- **Passwordless out-of-box**: Magic links, email codes, and passkeys are native features. Keycloak requires custom SPIs for this.
- **OIDC standards-compliant**: Supports Google/Microsoft SSO federation for schools that use these providers. Works with `expo-auth-session` (PKCE) and `react-oidc-context` without custom SDK work.
- **Self-hostable**: Keeps identity data within our infrastructure (important for POPIA compliance with minors' data). Auth0 has no self-hosting option.
- **Cost**: Free to self-host. Auth0 would cost $150-800+/month once real schools are onboarded with SSO requirements.
- **Lightweight**: Written in Go, single binary. Far less resource-hungry than Keycloak's Java stack for a small deployment.
- **Growing ecosystem**: Active development, good documentation, CNCF-adjacent. Newer than Keycloak but maturing rapidly.

**Consequences**:
- Positive: No per-MAU costs. Full control over identity data and configuration. Passwordless and SSO work without extensions.
- Positive: ZITADEL Organizations provide tenant isolation at the identity layer, matching the platform's multi-tenant model.
- Negative: Smaller community than Auth0 or Keycloak -- fewer Stack Overflow answers, fewer third-party integrations.
- Negative: Self-hosting means we own uptime, backups, and upgrades for the identity provider.
- Negative: No official ZITADEL Expo SDK -- integration uses standard `expo-auth-session` with PKCE, which works but requires manual configuration.

**References**: [03-authentication.md](./03-authentication.md)
---

## ADR-002: OpenFGA for Authorization

**Status**: Accepted
**Date**: 2025-03-19

**Context**: The platform has a deep permission hierarchy: platform > school > class > student > session > result. Teachers see only their classes, coaches see results but cannot approve them, school heads see everything at their school. Students transfer between schools and their results must follow them while access changes instantly. Row-level security in Postgres was considered but the nested multi-tenant hierarchy makes RLS policies brittle and hard to evolve. The authorization system must support relationship-based checks ("can this teacher view this result?") resolved by traversing the object graph.

**Decision**: Use OpenFGA for all authorization checks, called from the Application API on every request. No permission logic in SQL.

**Alternatives Considered**:

| Alternative | Pros | Cons |
|---|---|---|
| **SpiceDB** | Stronger Zanzibar fidelity, better consistency guarantees ("new enemy" problem handling), more storage backends (CockroachDB, Spanner), mature and battle-tested | Heavier operational footprint. gRPC-first API (less familiar for the team). Consistency guarantees beyond what this platform needs -- school permission changes are not real-time-critical. |
| **Casbin** | Embeddable library (no separate service), supports multiple access control models (RBAC, ABAC, ACL), lightweight | Not relationship-based -- cannot natively model "teacher of a class in a school can view results for sessions in that class." Would require mapping the hierarchy into flat policies. No graph traversal. |
| **OPA (Open Policy Agent)** | Powerful policy language (Rego), widely adopted for infrastructure/API policies, CNCF graduated | Policy-based, not relationship-based. Rego is a new language for the team. Modelling the school > class > student > result hierarchy in Rego policies would be complex and fragile. Better suited for "is this request allowed given these attributes" than "does this user have a relationship to this object." |
| **Postgres RLS** | No additional service. Enforcement at the database layer -- even direct DB access is protected. Familiar SQL syntax. | Multi-tenant hierarchies make RLS policies deeply nested and brittle. Student transfers require reworking policies or maintaining shadow tables. SQL queries become polluted with permission predicates. Hard to audit "why was this denied?" No clear relationship graph to inspect. |

**Rationale**:
- **Relationship-based model fits the domain**: The permission structure is a graph -- user belongs to school, school contains classes, classes have students, sessions produce results. OpenFGA's Zanzibar model traverses this graph naturally. The DSL reads like the domain: `can_view: teacher or school_head from school`.
- **Student transfers are trivial**: Delete old tuples, write new ones. Old school loses access instantly. No cascade logic, no policy rewrites.
- **SQL stays clean**: Queries carry no permission predicates. The API asks OpenFGA "allowed or denied?" then runs a simple `SELECT`.
- **SpiceDB's consistency edge is unnecessary**: OpenFGA's eventual consistency is acceptable here. Permission changes (student transfers, teacher reassignments) are not time-critical -- a few seconds of propagation delay is fine.
- **Better tooling for the team**: OpenFGA has a visual playground, clear documentation, and a Python SDK (`openfga-sdk`). The DSL is more approachable than SpiceDB's schema language for a small team.
- **CNCF incubating**: Strong governance and open-source commitment. Backed by Okta/Auth0 but not locked to their ecosystem.

**Consequences**:
- Positive: Clean separation -- Postgres stores facts, OpenFGA guards access. Each system does one job.
- Positive: Permission changes (transfers, role changes) are tuple writes -- no schema migrations, no SQL changes.
- Positive: Auditability -- the relationship graph is inspectable. "Why can this user see this result?" is answerable by tracing tuples.
- Negative: Additional service to deploy, monitor, and maintain.
- Negative: Every API request incurs an OpenFGA check (sub-millisecond for cached evaluations, but still an extra network hop).
- Negative: Tuple management must be kept in sync with domain events -- creating a class must also write the OpenFGA tuple. If the tuple write fails, permissions are wrong.

**References**: [04-authorization.md](./04-authorization.md)
---

## ADR-003: FastAPI for Application API

**Status**: Accepted
**Date**: 2025-03-19

**Context**: The Application API is the public-facing service handling authentication middleware, OpenFGA permission checks, domain CRUD, upload orchestration (signed URL generation), and result ingestion from the pipeline. It must integrate with ZITADEL (JWT validation), OpenFGA (permission checks), PostgreSQL, Redis, GCS, and the existing Pipeline API (also FastAPI). The existing CV pipeline POC is already written in Python with FastAPI.

**Decision**: Use FastAPI (Python) for the Application API.

**Alternatives Considered**:

| Alternative | Pros | Cons |
|---|---|---|
| **Django + DRF** | Mature ORM, admin panel, large ecosystem, battle-tested for CRUD-heavy apps | Heavier framework with opinions that don't align (e.g., Django's built-in auth vs ZITADEL). Synchronous by default (async support is bolted on). Admin panel is not needed -- admin operations go through the API. |
| **Express / NestJS (Node.js)** | Large ecosystem, TypeScript for type safety, good async I/O, many auth libraries | Language split -- the pipeline is Python. Two runtime ecosystems means two dependency stacks, two Docker images with different base layers, and context-switching for a small team. No SDK advantage for OpenFGA (Python SDK exists). |
| **Go (net/http / Gin / Echo)** | Excellent performance, single binary deployment, strong concurrency primitives | Same language-split problem as Node.js but worse -- Go has a steeper learning curve for the team. OpenFGA has a Go SDK but the team's expertise is Python. |

**Rationale**:
- **Same language as the pipeline**: Both the Application API and Pipeline API are FastAPI/Python. One language across the entire backend means shared tooling, shared Docker base images, and no context-switching.
- **Async-native**: FastAPI is built on Starlette/ASGI with native `async/await`. This matters for the Application API's pattern of making multiple outbound calls per request (ZITADEL JWT validation, OpenFGA checks, Pipeline API calls, database queries).
- **Auto-generated OpenAPI spec**: FastAPI generates an OpenAPI schema from type hints. This feeds directly into the auto-generated TypeScript client shared across all frontend applications (see [05-client-applications.md](./05-client-applications.md)).
- **Ecosystem fit**: Python SDKs exist for OpenFGA (`openfga-sdk`), ZITADEL, GCS (`google-cloud-storage`), and all other integration points.
- **Team expertise**: The team knows Python. Shipping matters more than theoretical performance gains from Go or Node.js.
- **Performance is adequate**: The Application API is I/O-bound (database, Redis, GCS, external services), not CPU-bound. FastAPI's async model handles this well. The CPU-bound work (CV processing) runs on the pipeline, not here.

**Consequences**:
- Positive: Single language stack across the entire backend. Shared tooling, linting, testing, and CI/CD patterns.
- Positive: OpenAPI auto-generation enables type-safe frontend clients with zero manual spec maintenance.
- Positive: Rich Python ecosystem for data manipulation and integration libraries.
- Negative: Python is slower than Go or compiled languages for CPU-bound work. Not an issue here (I/O-bound service), but worth noting.
- Negative: FastAPI's ecosystem is younger than Django's -- fewer batteries included (no ORM, no admin, no migrations tool). SQLAlchemy + Alembic fill the gap but require more setup.

**References**: [02-api-architecture.md](./02-api-architecture.md), [08-pipeline-integration.md](./08-pipeline-integration.md)

---

## ADR-004: Celery + Redis for Task Queue

**Status**: Accepted
**Date**: 2025-03-19

**Context**: The CV pipeline processes video through 8 sequential stages (Ingest, Detect, Track, Pose, OCR, Calibrate, Extract, Output), each GPU-bound. Processing a single clip takes 30-120 seconds. A class session might produce 1-30 clips. Processing must be asynchronous -- the teacher uploads a video and polls for results. The existing POC already uses Celery with Redis as the broker and result backend. Workers run on GPU VMs, one job at a time per GPU.

**Decision**: Use Celery with Redis as the task broker and result backend for pipeline job processing.

**Alternatives Considered**:

| Alternative | Pros | Cons |
|---|---|---|
| **Google Cloud Tasks** | Fully managed, no broker to maintain, integrates with Cloud Run | Cannot target GPU VMs directly -- designed for HTTP endpoint targets. Would require wrapping the GPU worker as an HTTP service, adding complexity. No task state introspection (stage-level progress). Vendor lock-in. |
| **Temporal** | Durable workflows, automatic retries with backoff, workflow versioning, excellent observability | Heavy infrastructure for a single-purpose queue. Overkill for "submit video, process 8 stages, return results." Learning curve for the team. Additional service to deploy and maintain. |
| **Direct processing (synchronous)** | Simplest architecture -- no queue, no broker, no worker process | Blocks the API during processing (30-120 seconds). Cannot scale workers independently. No retry mechanism. No job state tracking. Completely unsuitable for production. |
| **RQ (Redis Queue)** | Simpler than Celery, Python-native, uses Redis | Less mature, fewer features (no task chains, no canvas, no rate limiting). Celery is already implemented in the POC. Switching gains nothing. |

**Rationale**:
- **Already implemented**: The POC uses Celery + Redis. The pipeline worker, task definitions, and stage-level `update_state()` calls are already written and working. Switching to a different queue system means rewriting working code for no functional gain.
- **Redis is already provisioned**: Redis (Memorystore) is used for the Celery broker, task state, and application-level caching. One service serves multiple purposes.
- **Stage-level progress**: Celery workers call `self.update_state()` with per-stage metadata as they progress through the 8 pipeline stages. This data is stored in Redis and will power the stage-by-stage progress display in the Teacher App.
- **GPU worker model**: Celery's concurrency model (one task at a time per worker with `--concurrency=1`) matches the GPU constraint -- one video clip processed at a time per GPU. Adding capacity means adding GPU VMs with Celery workers; Celery distributes jobs automatically.
- **Operational simplicity**: Redis is a managed service (Memorystore). Celery workers are processes on the GPU VM. No additional infrastructure beyond what already exists.

**Consequences**:
- Positive: Zero migration effort -- the POC's task queue carries forward as-is.
- Positive: Stage-level progress tracking is built into the existing worker implementation.
- Positive: Horizontal scaling is straightforward -- add GPU VMs, Celery distributes jobs.
- Negative: Redis as a broker is not as durable as a dedicated message queue (RabbitMQ, SQS). If Redis crashes, in-flight task metadata is lost. Acceptable for this use case -- the video is safe in GCS and jobs can be resubmitted.
- Negative: Celery's complexity (canvas, chains, groups) is mostly unused -- we use it as a simple task queue. The framework is heavier than needed.

**References**: [08-pipeline-integration.md](./08-pipeline-integration.md), [07-infrastructure.md](./07-infrastructure.md)

---

## ADR-005: PostgreSQL for Data Storage

**Status**: Accepted
**Date**: 2025-03-19

**Context**: The platform stores structured, relational data: schools, users, students, classes, bib assignments, test sessions, clips, and results. Relationships between entities are central to the domain -- a result belongs to a clip, which belongs to a session, which belongs to a class at a school. The pipeline also stores structured data: detections, tracks, poses, OCR readings, calibration data. Additionally, ZITADEL and OpenFGA both need a PostgreSQL-compatible backend. The POC already provisions a Cloud SQL (PostgreSQL) instance via Terraform.

**Decision**: Use PostgreSQL for all persistent data storage.

**Alternatives Considered**:

| Alternative | Pros | Cons |
|---|---|---|
| **MongoDB** | Flexible schema, good for JSON-heavy data (pipeline raw_data), horizontal scaling built-in | The domain is fundamentally relational (school > class > student > result). MongoDB's document model would require denormalization or `$lookup` aggregations that Postgres handles natively with JOINs. ZITADEL and OpenFGA both require Postgres -- adding MongoDB means running two database systems. |
| **CockroachDB** | Distributed SQL, horizontal scaling, strong consistency across regions | Overkill for current scale (single-region, single-digit schools initially). Higher operational complexity. Managed CockroachDB is expensive. The platform does not need multi-region writes or horizontal SQL scaling yet. |
| **MySQL / MariaDB** | Mature, widely supported, lower resource usage in some configurations | ZITADEL and OpenFGA both support Postgres natively (OpenFGA also supports MySQL, but ZITADEL does not). Using MySQL would require running both MySQL and Postgres, or losing ZITADEL compatibility. PostgreSQL's JSONB support is superior for storing pipeline `raw_data`. |

**Rationale**:
- **The domain is relational**: Schools contain classes, classes contain students, sessions produce results linked to students via bib assignments. SQL with foreign keys, JOINs, and constraints is the natural fit.
- **ZITADEL and OpenFGA both use Postgres**: Running a single database engine simplifies operations. Both services store their data in Postgres schemas alongside the application and pipeline schemas.
- **JSONB for pipeline data**: The `raw_data` field on Results and various pipeline artifacts store semi-structured JSON. PostgreSQL's JSONB type with indexing handles this without needing a separate document store.
- **Cloud SQL (managed)**: GCP's managed PostgreSQL service handles backups, patching, high availability, and scaling. The team does not need to manage database infrastructure.
- **Proven at scale**: PostgreSQL handles the expected data volumes comfortably. Even at 1,000 schools with 30 sessions/week, the row counts are well within single-instance PostgreSQL capacity.
- **POC continuity**: The existing Terraform already provisions Cloud SQL with PostgreSQL.

**Consequences**:
- Positive: Single database engine for all six schemas (core_data, identity, consent, vigour_pipeline, ZITADEL, OpenFGA). Simplified operations, monitoring, and backup strategy.
- Positive: Rich SQL capabilities -- window functions for analytics, CTEs for complex reporting queries, JSONB for semi-structured data.
- Positive: Mature ecosystem -- SQLAlchemy, Alembic, psycopg2/asyncpg, pgAdmin.
- Negative: Vertical scaling ceiling eventually. If the platform reaches tens of thousands of schools, read replicas and sharding strategies would be needed. This is a distant concern.
- Negative: Single database engine means a Postgres-specific outage affects everything. Mitigated by Cloud SQL's managed HA.

**References**: [01-domain-model.md](./01-domain-model.md), [07-infrastructure.md](./07-infrastructure.md)

---

## ADR-006: Single PostgreSQL Instance with Multi-Schema Isolation

**Status**: Accepted
**Date**: 2025-03-19

**Context**: The platform has four distinct data domains: application data (schools, users, results), pipeline data (detections, tracks, poses), ZITADEL identity data, and OpenFGA authorization tuples. Each domain has different owners and access patterns. The question is whether to run separate PostgreSQL instances or co-locate them in a single instance with schema-level isolation.

**Decision**: Use a single Cloud SQL PostgreSQL instance with six separate schemas organised into privacy layers, each accessed by a dedicated database role with no cross-schema read permissions:

| Schema | Privacy Layer | Contents |
|---|---|---|
| `core_data` | Layer 1 — Anonymised Core Data | Schools, classes, sessions, results, bib assignments. No names, no identity links. |
| `identity` | Layer 2 — Identity | Student names, dates of birth, parent contacts, teacher profiles. Links to `core_data` via pseudonymous UUIDs. |
| `consent` | Layer 3 — Consent & Audit | Consent records, consent withdrawal events, data subject access requests, audit logs. |
| `vigour_pipeline` | Internal | Detections, tracks, poses, OCR readings, calibration data. |
| `zitadel` | Infrastructure | ZITADEL identity provider data (managed by ZITADEL). |
| `openfga` | Infrastructure | OpenFGA authorization tuples (managed by OpenFGA). |

Each of `core_data`, `identity`, and `consent` has its own database role. No role can read across these three schemas — this enforces structural data minimisation at the database level.

**Alternatives Considered**:

| Alternative | Pros | Cons |
|---|---|---|
| **Separate Cloud SQL instances per concern** | Maximum isolation -- independent scaling, independent failures, independent backup schedules. Security boundary at the network level. | 4x the cost for managed instances ($50-200+/month each for production-tier instances). 4x the operational overhead for monitoring, patching, connection management. Far exceeds the isolation needs at current scale. |
| **Single schema (all tables in one schema)** | Simplest to set up. No cross-schema complexity. | No logical isolation. Application code could accidentally query pipeline tables. ZITADEL and OpenFGA tables mixed with application tables. Makes future separation harder. Violates the two-tier API boundary. |
| **Two instances (app+auth vs pipeline)** | Separates the pipeline's data (which may have different scaling needs due to GPU batch processing) from the application/auth data | 2x cost. The pipeline DB is small and low-traffic -- the GPU is the bottleneck, not the database. Premature optimisation. |

**Rationale**:
- **Cost**: A single `db-custom-2-7680` Cloud SQL instance costs ~$50-70/month. Six instances would cost 6x that. For a platform starting with single-digit schools, this cost difference matters.
- **Operational simplicity**: One instance to monitor, one backup schedule, one set of connection strings to manage, one Cloud SQL proxy.
- **Privacy-by-design through structural separation**: The three application schemas (`core_data`, `identity`, `consent`) enforce data minimisation at the database level. A service querying fitness results (`core_data`) cannot accidentally join to student names (`identity`) or consent records (`consent`). This is not just logical isolation — it is a privacy architecture: even a compromised database credential for one layer cannot access another layer's data.
- **Logical isolation is sufficient at the infrastructure level**: Each schema has a dedicated PostgreSQL role. The Application API's database user cannot access pipeline tables, and vice versa. This prevents accidental cross-boundary queries without the overhead of separate instances.
- **Future-proof**: If isolation, performance, or compliance demands change, migrating a schema to its own instance is a `pg_dump` / `pg_restore` operation. The application code only needs a connection string change.
- **The POC already does this**: The existing Terraform provisions a single Cloud SQL instance. Extending it with additional schemas is the lowest-friction path.

**Consequences**:
- Positive: Lowest cost at initial scale. Single point of management.
- Positive: Privacy-layered schema isolation enforces structural data minimisation — no database role can read across the `core_data`, `identity`, and `consent` boundaries. This goes beyond access control; it is a privacy architecture that limits blast radius of credential compromise.
- Positive: Easy to split later -- each schema is already self-contained.
- Negative: Shared resource pool -- a runaway query in one schema (e.g., a pipeline cache table scan) can affect performance for all schemas. Mitigated by proper indexing and connection pooling.
- Negative: Single point of failure -- if Cloud SQL goes down, all six schemas are affected. Mitigated by Cloud SQL's managed HA and automatic failover.
- Negative: Shared backup/restore -- you cannot independently restore one schema without affecting others (without using logical backups per schema).
- Negative: Application API must use multiple database connections (one per privacy-layer role) and explicitly manage which connection is used for which query. This adds code complexity but enforces the privacy boundary in application code, not just database configuration.

**References**: [07-infrastructure.md](./07-infrastructure.md), [02-api-architecture.md](./02-api-architecture.md)

---

## ADR-007: Google Cloud Platform for Hosting

**Status**: Accepted
**Date**: 2026-03-20 (revised -- original 2025-03-19 decision was based on incomplete analysis)

**Context**: The platform requires GPU compute for the CV pipeline (NVIDIA L4 or equivalent), object storage for video files (4K/60fps, potentially gigabytes per session), a managed relational database, managed Redis, a serverless container deployment target for the Application API, and container hosting for ZITADEL and OpenFGA. The existing POC is deployed on GCP with Terraform provisioning a GPU VM (g2-standard-4 with L4), Cloud SQL, Cloud Storage, and Memorystore (Redis). However, the team has experience with both GCP and AWS, the POC Terraform can be rewritten from scratch, and both clouds now have South African regions (GCP `africa-south1` Johannesburg, launched January 2024; AWS `af-south-1` Cape Town, launched 2020). This ADR records a deliberate cloud choice, not a default inherited from the POC.

**Decision**: Use Google Cloud Platform for all hosting, with application-layer infrastructure in `africa-south1` (Johannesburg) for POPIA compliance and GPU workloads in a designated European GPU processing region (the specific region is an infrastructure decision documented in [07-infrastructure.md](./07-infrastructure.md)) until GPU instances become available in Africa.

**Alternatives Considered**:

| Alternative | Pros | Cons |
|---|---|---|
| **AWS** | Largest cloud. Cape Town region (af-south-1) since 2020. Cheaper managed Postgres (db.t4g.medium ~$53/mo vs Cloud SQL ~$103/mo). 100 GB/mo free egress. 1 TB/mo free CloudFront CDN. AWS EdStart programme designed for EdTech. Broader service catalogue. | GPU instances in af-south-1 are limited to G4 (NVIDIA T4, 16 GB VRAM) -- no G5 (A10G) or G6 (L4). GPU VMs still need a European region. G5.xlarge on-demand ~$1.01/hr vs GCP g2-standard-4 ~$0.71/hr (30% premium). No true scale-to-zero for containers (Fargate always runs; App Runner pauses but still bills). |
| **Azure** | Strong in education sector. Azure AD integration for school SSO. NC-series GPU VMs. South Africa North region (Johannesburg). | Developer experience less polished. Weaker serverless container story (Container Apps is newer, less mature than Cloud Run). No team expertise. GPU pricing not competitive. |
| **Self-hosted / on-premise** | Full control. No cloud costs. Data stays in South Africa. | GPU hardware procurement and maintenance. No managed database, Redis, or object storage. Uptime and scaling are entirely the team's responsibility. Catastrophic for a small team. |
| **Hybrid (GCP + Hetzner for GPU)** | Hetzner GPU servers are significantly cheaper (~$2/hr for A100) | Cross-provider networking complexity. Split infrastructure harder to manage. No managed services. Signed URLs still tied to one cloud's storage. |

### Cost Comparison (MVP, 5-10 schools, ~160 GPU-hours/month)

| Component | GCP | AWS | Notes |
|---|---|---|---|
| GPU VM (L4, spot, 160 hrs/mo) | ~$35-45 | ~$48-64 | GCP g2-standard-4 spot ~$0.21-0.28/hr; AWS g5.xlarge spot ~$0.30-0.40/hr. Both in EU regions. |
| Serverless API (~100K req/mo) | **$0** | ~$10 | Cloud Run always-free tier covers this. App Runner has no free tier. |
| Managed PostgreSQL | ~$103 | ~$53 | Cloud SQL db-custom-2-7680 vs RDS db.t4g.medium (4 GB RAM, burstable). Like-for-like (8 GB) is ~$120 on AWS. |
| Managed Redis (1 GB) | ~$16 | ~$12 | Memorystore Basic vs ElastiCache cache.t4g.micro. |
| Object storage (50 GB + 50 GB egress) | ~$7 | ~$1 | AWS has 100 GB/mo free egress across all services. |
| ZITADEL + OpenFGA containers | ~$35 | ~$40 | Cloud Run min-instances vs Fargate tasks. |
| CDN / Load Balancer | ~$5 | **$0** | Cloud Run includes free LB. AWS CloudFront has 1 TB/mo free. |
| **Monthly total** | **~$200-210** | **~$165-180** | AWS ~$25-40/mo cheaper at MVP scale. |

At scale, GPU compute dominates spend. A single L4 running full-time: GCP ~$516/mo vs AWS ~$734/mo. **GCP's 30% GPU cost advantage grows as usage increases** -- the crossover where GCP becomes cheaper overall is approximately 400-500 GPU-hours/month (~25 hrs/week, roughly 10-15 schools processing daily).

### Free Tier Comparison

| Service | GCP Always Free | AWS Free Tier |
|---|---|---|
| Serverless containers | Cloud Run: 2M requests, 50 CPU-hrs, 100 GB-hrs/mo | None (no Fargate/App Runner free tier) |
| Object storage | 5 GB Standard | 5 GB Standard + **100 GB/mo free egress** |
| Managed Postgres | None | 750 hrs/mo db.t2.micro (12 months only, legacy accounts) |
| Managed Redis | None | None |
| CDN | None (Cloud CDN is paid) | **1 TB/mo free CloudFront** |
| Compute (non-GPU) | 1 e2-micro VM | 750 hrs/mo t2.micro (12 months only) |
| GPU | None | None |

GCP's free tier advantage is concentrated in Cloud Run (serverless containers). AWS's advantage is in egress and CDN. Neither offers free managed Postgres or Redis long-term.

### Startup and Education Credits

| Programme | Credits | Relevance |
|---|---|---|
| **Google for Startups Accelerator: Africa** | Up to $350K cloud credits + R1M cash funding (equity-free) | Directly targets African startups. Next cohort April-June 2026. Highly relevant. |
| **GCP Startup Cloud Programme** | $2K (pre-seed) to $100K (funded) | Standard application. |
| **AWS EdStart** | Up to $100K in credits + technical support | Specifically designed for EdTech startups. Vigour qualifies. |
| **AWS Activate** | Up to $100K in credits | General startup programme. |

Both clouds have strong programmes. GCP's Africa Accelerator is a standout opportunity.

**Rationale**:
- **GPU cost is the dominant scaling factor**: The CV pipeline is the platform's core differentiator and its largest cost driver. GCP's L4 GPU (g2-standard-4) is ~30% cheaper than AWS's equivalent at both on-demand and spot pricing. At 10+ schools processing daily, this saving exceeds the AWS advantages on Postgres and egress. The platform should optimise for the cost that scales with usage, not the fixed costs that stay flat.
- **Cloud Run's scale-to-zero is a genuine MVP advantage**: The Application API, ZITADEL, and OpenFGA can all run on Cloud Run. During evenings, weekends, and school holidays (the majority of hours), these scale to zero and cost nothing. AWS has no equivalent -- Fargate tasks always run, App Runner pauses but still bills. For a platform with highly predictable, school-hours-only traffic, this matters.
- **Johannesburg region covers POPIA**: GCP's `africa-south1` (Johannesburg) launched January 2024 with Cloud SQL, Cloud Storage, Memorystore, and Cloud Run. Application data (student PII, identity data, results) can be hosted in South Africa. GPU workloads run in a designated European GPU processing region. Video IS personal data — it contains identifiable children. The legal basis for cross-region transfer is that processing is ephemeral and transient (video is pulled, processed in memory/tmpfs, local copy auto-purged on completion), not that the video is anonymised. See ADR-017 (Ephemeral Cross-Region GPU Processing) for details. This approach satisfies the spirit of POPIA data residency requirements for minors' data.
- **Low lock-in**: The stack is standard containers (Docker), standard Postgres, standard Redis, and standard object storage. The only GCP-specific integration points are Terraform resources, signed URL generation (server-side, abstracted behind the Application API), and event notifications (GCS Pub/Sub for upload-triggers-pipeline). Application code is cloud-agnostic. Switching to AWS would mean rewriting Terraform and the upload trigger plumbing -- significant work but not an architectural change.
- **Managed services for a small team**: Cloud SQL, Memorystore, Cloud Storage, and Cloud Run are all managed. The team cannot afford to operate databases, caches, or container orchestration manually.
- **POC continuity is a bonus, not the reason**: The existing Terraform provisions GCP resources and carries forward. This saves time but was not the deciding factor -- the team is willing and able to rewrite Terraform for either cloud.

**Consequences**:
- Positive: Cheapest GPU compute among major clouds. Cost advantage grows with scale.
- Positive: Cloud Run scale-to-zero eliminates off-hours spend for the API, auth, and authz services.
- Positive: South African region for POPIA-sensitive data. No regulatory uncertainty about data residency for minors' PII.
- Positive: Existing POC infrastructure carries forward, saving initial setup time.
- Negative: GCP's managed Postgres (Cloud SQL) is ~$50/mo more expensive than AWS RDS at the smallest tier. At MVP scale this is the single largest cost disadvantage. If cost pressure is severe, consider a smaller Cloud SQL instance or self-hosting Postgres on a VM initially.
- Negative: No free egress or CDN tier. AWS offers 100 GB/mo free egress and 1 TB/mo free CloudFront. For a video-upload-heavy platform, egress costs could grow. Mitigated by direct-to-GCS uploads (egress is download, not upload) and Cloud CDN caching for static SPA assets.
- Negative: GPU instances are not available in `africa-south1`. GPU workloads run in a European region. Cross-region latency for video pull is acceptable because pipeline processing is fully asynchronous — the teacher uploads video and polls for results; there are no synchronous API calls that depend on GPU-region round-trip time.
- Negative: Vendor lock-in at the Terraform and event-trigger layer. Switching to AWS requires rewriting infrastructure code and the upload-to-pipeline trigger (GCS Pub/Sub → S3 EventBridge). Application code is unaffected.

**Decision to revisit if**:
- AWS launches L4/A10G GPU instances in `af-south-1` (Cape Town), which would give AWS both latency and POPIA advantages for GPU workloads.
- GCP's Cloud SQL pricing becomes uncompetitive at scale (10+ schools), in which case self-hosting Postgres on Compute Engine is an option.
- The team is accepted into AWS EdStart with significant credits that offset the GPU cost difference.
- GCP launches GPU instances in `africa-south1`, which would consolidate all workloads in one region.

**References**: [07-infrastructure.md](./07-infrastructure.md)

---

## ADR-008: Cloud Run for Application API

**Status**: Accepted
**Date**: 2025-03-19

**Context**: The Application API is a stateless FastAPI service that handles HTTP requests from web and mobile clients. It needs to scale with request volume (potentially bursty -- teachers uploading at the same time during school hours), scale to zero during off-hours to save cost, and deploy without cluster management overhead. The team is small and cannot justify the operational cost of managing Kubernetes.

**Decision**: Deploy the Application API on Cloud Run.

**Alternatives Considered**:

| Alternative | Pros | Cons |
|---|---|---|
| **GKE (Google Kubernetes Engine)** | Full Kubernetes control. Service mesh, sidecar injection, custom networking, multi-service orchestration. Supports GPU workloads in the same cluster. | Massive operational overhead for a single stateless API. Cluster management, node pools, autoscaler tuning, RBAC, cert management. Minimum cost ~$70/month for the control plane alone, plus node costs. Overkill for one API service. |
| **Cloud Functions (2nd gen)** | True serverless -- no container management at all. Pay per invocation. | Cold start latency (up to several seconds for Python). 60-minute request timeout limits. Cannot run background processes. Less control over runtime environment. FastAPI does not run natively on Cloud Functions without adapters. |
| **Compute Engine (VM)** | Full control. Fixed cost. No cold starts. Can co-locate with other services. | Manual scaling -- must manage instance groups, health checks, and autoscaling policies. Always-on cost even during off-hours. Patching and maintenance are the team's responsibility. |

**Rationale**:
- **Operational simplicity**: Deploy via `gcloud run deploy` or a CI/CD pipeline pushing a Docker image. No cluster management, no node pools, no kubectl.
- **Scale to zero**: During off-hours (evenings, weekends, school holidays), the service scales to zero instances and costs nothing. School usage is highly predictable -- weekday mornings during PE lessons.
- **Auto-scaling**: Cloud Run scales horizontally based on request concurrency. When 50 teachers upload simultaneously during PE hour, Cloud Run spins up instances automatically. When traffic drops, it scales down.
- **VPC Connector**: Cloud Run can connect to the private VPC via a Serverless VPC Access connector, reaching PostgreSQL, Redis, OpenFGA, and the Pipeline API on private IPs.
- **Cost**: Pay per request-second. At low scale (single-digit schools), this is dramatically cheaper than a dedicated VM or GKE cluster. Even at moderate scale, Cloud Run is cost-competitive.
- **Container-based**: The Application API is deployed as a standard Docker container. If Cloud Run ever becomes insufficient, the same container can run on GKE, Compute Engine, or any other Docker host with zero code changes.

**Consequences**:
- Positive: Near-zero operational overhead for deployment and scaling.
- Positive: Cost-efficient at low and moderate scale. Scale-to-zero eliminates off-hours cost.
- Positive: Same Docker container runs locally, on Cloud Run, or on any other platform. No lock-in to Cloud Run's runtime.
- Negative: Cold start latency (~1-3 seconds for a Python container) when scaling from zero. Mitigated by configuring a minimum instance count of 1 during school hours.
- Negative: Request timeout of 60 minutes (configurable). Not an issue for API requests but limits any long-running background work. Background work belongs in Celery anyway.
- Negative: No persistent local filesystem. All state must be in PostgreSQL, Redis, or GCS. This is already the case for the Application API's stateless design.

**References**: [07-infrastructure.md](./07-infrastructure.md)

---

## ADR-009: Expo / React Native for Teacher App

**Status**: Accepted
**Date**: 2025-03-19

**Context**: The Teacher App is the primary operational tool -- teachers use it in school halls and on fields to set up sessions, assign bibs, record video (4K/60fps), upload to cloud storage, and review results. It must run on both iOS and Android. It needs camera access, secure token storage, offline support for session setup and bib assignment, and a queued upload mechanism for poor connectivity. The team is small (1-2 developers) and cannot maintain separate iOS and Android codebases.

**Decision**: Use Expo (React Native) for the Teacher App.

**Alternatives Considered**:

| Alternative | Pros | Cons |
|---|---|---|
| **Flutter** | Excellent cross-platform performance. Strong widget library. Single codebase for iOS + Android. Growing ecosystem. | Dart is a new language for the team (which is JavaScript/TypeScript-focused). Fewer third-party libraries than React Native's npm ecosystem. ZITADEL integration would require more custom work (no `expo-auth-session` equivalent as mature). Camera libraries exist but are less battle-tested than Expo's. |
| **Native iOS + Android** | Best performance. Full platform API access. Best camera/video control. | Two codebases, two languages (Swift + Kotlin), two CI pipelines. Impossible to maintain with a 1-2 person team. Development time doubles. |
| **PWA (Progressive Web App)** | Single codebase. No app store. Works on any device with a browser. | Cannot access camera at 4K/60fps reliably across devices. No secure keychain storage for tokens. Limited offline capability. No push notifications on iOS. Background upload is unreliable. Fundamentally unsuitable for a video-capture-centric application. |

**Rationale**:
- **Team expertise**: The team writes JavaScript/TypeScript. React Native / Expo is the lowest-friction path to cross-platform mobile.
- **Expo ecosystem**: `expo-camera` for video recording, `expo-secure-store` for encrypted token storage, `expo-auth-session` for ZITADEL OIDC (PKCE flow), `expo-file-system` for local video management, and `expo-background-fetch` for upload queue processing. These are production-grade, well-documented libraries.
- **Single codebase**: One codebase produces both iOS and Android apps. Critical for a small team.
- **Offline support**: React Query / TanStack Query (already planned for state management) provides offline mutation queuing. Combined with `expo-file-system` for local video storage, the offline session setup and upload queue requirements are achievable.
- **Code sharing**: React Native and React web apps share the same component model. A shared TypeScript API client (auto-generated from the FastAPI OpenAPI spec) works across mobile and web clients.
- **Expo Application Services (EAS)**: Managed build and submission pipeline. `eas build` and `eas submit` handle iOS and Android builds in the cloud without needing macOS or Android Studio locally.

**Consequences**:
- Positive: Single JavaScript/TypeScript codebase for iOS and Android. Shared API client with web dashboards.
- Positive: Expo's managed workflow simplifies builds, updates, and app store submission.
- Positive: Rich ecosystem of camera, auth, and storage libraries purpose-built for the use cases.
- Negative: React Native's camera performance may not match native. 4K/60fps recording needs thorough device testing, especially on lower-end Android devices common in South African schools.
- Negative: Expo's managed workflow limits access to some native APIs. If custom native modules are needed (e.g., advanced camera control), ejecting to a bare workflow adds complexity.
- Negative: JavaScript bridge overhead. For video recording, this is mitigated by `expo-camera`'s native implementation, but frame-level processing (if needed for pre-flight checks) may require native modules.

**References**: [05-client-applications.md](./05-client-applications.md), [03-authentication.md](./03-authentication.md)

---

## ADR-010: React SPA for Web Dashboards

**Status**: Accepted
**Date**: 2025-03-19

**Context**: Two web dashboards serve different roles: Coach Dashboard (class leaderboards, student detail, exports) and School Head Dashboard (school-wide metrics, grade breakdowns, at-risk alerts). Both are read-heavy, data-visualisation-focused applications with tables and charts. They share a common design system and component library. Authentication uses `react-oidc-context` with ZITADEL OIDC.

**Decision**: Build all web dashboards as React SPAs (Single Page Applications), likely using Vite as the build tool, with a shared component library.

**Alternatives Considered**:

| Alternative | Pros | Cons |
|---|---|---|
| **Next.js** | Server-side rendering for SEO and initial load performance. API routes for BFF pattern. Image optimisation. File-based routing. | SEO is irrelevant -- these are authenticated dashboards, not public pages. SSR adds server infrastructure (Node.js runtime) for no benefit. API routes would duplicate the FastAPI Application API. Next.js's opinions (app router, server components) add complexity without value for an internal dashboard. |
| **Svelte / SvelteKit** | Smaller bundle size. Less boilerplate. Excellent performance. Growing ecosystem. | New framework for the team. Smaller ecosystem than React -- fewer charting libraries, fewer UI component kits. No code sharing with the Expo / React Native mobile apps. |
| **Server-rendered (Django templates, HTMX)** | No client-side framework. Simple deployment. Works on low-bandwidth connections. | Limited interactivity for data-heavy dashboards (sorting, filtering, drill-down). Poor fit for real-time polling (pipeline status). No code sharing with mobile. Ties the frontend to the Python backend. |

**Rationale**:
- **Code sharing with mobile**: React Native (Expo) and React web share the same component model, the same TypeScript API client (auto-generated from OpenAPI), and the same state management library (TanStack Query). Developers move between mobile and web without switching paradigms.
- **Ecosystem for data visualisation**: React has the richest charting ecosystem -- recharts, nivo, victory, visx. The dashboards are primarily tables and charts.
- **SPA is the right model**: These are authenticated, internal tools. No SEO requirement. No public content. The user logs in, the SPA loads, and all subsequent navigation is client-side. Server-side rendering adds complexity with no benefit.
- **`react-oidc-context`**: ZITADEL's recommended React integration works seamlessly in an SPA context with `httpOnly` secure cookies.
- **Vite over Create React App**: Vite offers faster builds, HMR, and is the modern standard for React SPAs. No opinion lock-in -- it is just a build tool.
- **Shared codebase potential**: Coach Dashboard and School Head Dashboard could be the same application with role-based view switching, further reducing code duplication.

**Consequences**:
- Positive: Maximum code sharing across all frontend surfaces (mobile and web).
- Positive: Rich ecosystem for the specific needs (charts, tables, data export).
- Positive: Simple deployment -- static assets served from GCS or Cloud CDN. No server runtime needed for the frontend.
- Negative: Initial load requires downloading the JavaScript bundle. Mitigated by code splitting and lazy loading.
- Negative: Client-side rendering means content is not visible to search engines. Irrelevant for authenticated dashboards.
- Negative: Three dashboards sharing a codebase could lead to bloat if not managed carefully (tree-shaking and lazy routes help).

**References**: [05-client-applications.md](./05-client-applications.md)

---

## ADR-011: Direct-to-GCS Upload with Signed URLs

**Status**: Accepted
**Date**: 2025-03-19

**Context**: Teachers record fitness test videos at 4K/60fps. A single clip can be hundreds of megabytes to several gigabytes. These videos must be uploaded from the Teacher App (mobile) to cloud storage for pipeline processing. South African schools may have limited and unreliable internet connectivity. The upload mechanism must be efficient, resumable (or at least retryable), and must not burden the Application API with video bytes.

**Decision**: The client uploads video directly to Google Cloud Storage using time-limited signed URLs generated by the Application API. The API never touches video bytes. A Clip record (task handle) is created before the upload begins (Option B -- task before upload).

**Alternatives Considered**:

| Alternative | Pros | Cons |
|---|---|---|
| **API proxy upload (multipart POST to Application API)** | Simpler client code -- just POST the file. API handles storage. | The Application API becomes a bandwidth bottleneck. Every byte of every video passes through the API, doubling egress and latency. Cloud Run's request size limits (32 MB default, 32 GB max) and timeout constraints make this fragile for large files. Horizontal scaling the API would be needed for bandwidth, not request count. |
| **GCS resumable uploads (via signed URL)** | Supports resuming interrupted uploads. Ideal for poor connectivity. Chunks are individually acknowledged. | More complex client implementation. Requires managing upload sessions, chunk tracking, and resume logic. The Expo/React Native ecosystem has less mature support for GCS resumable uploads than simple PUT requests. |
| **tus protocol (resumable upload standard)** | Open standard for resumable uploads. Client libraries exist for JavaScript/React Native. Server-agnostic. | Requires a tus server (additional infrastructure). GCS does not natively speak tus. Would need a proxy service or adapter. Additional service to deploy and maintain. |

**Rationale**:
- **No video bytes through the API**: The Application API is a lightweight request-routing service. Passing gigabytes of video through it would require scaling for bandwidth rather than request volume, fundamentally changing its resource profile. Direct-to-GCS eliminates this entirely.
- **Signed URLs are secure**: The Application API generates a time-limited (e.g., 15-minute) signed URL scoped to a specific GCS path. The client can only upload to the designated path within the time window. No GCS credentials are exposed to the client.
- **Task-before-upload (Option B)**: The Application API creates a Clip record (`status=uploading`) and returns both `clip_id` and the signed URL in a single response. This ensures the client always has a task handle before uploading, orphaned uploads are trackable (stuck in `uploading` status), and every state is recoverable.
- **Simple client implementation**: A PUT request to the signed URL is all that is needed. Expo's `fetch` or `expo-file-system` upload methods handle this natively.
- **Resumable uploads deferred**: For MVP, a simple PUT with retry-on-failure is sufficient. If connectivity proves too unreliable, GCS resumable uploads can be added later -- the signed URL approach is compatible with both simple and resumable uploads.

**Consequences**:
- Positive: Application API stays lightweight. No bandwidth scaling concerns.
- Positive: Direct client-to-GCS upload is fast -- GCS is optimised for large object ingestion.
- Positive: Clip record created before upload provides a reliable task handle and enables orphan detection.
- Negative: If an upload fails partway, the entire file must be re-uploaded (no resume). Acceptable for MVP; resumable uploads can be added.
- Negative: The client must handle the two-step flow (request signed URL, then upload). Slightly more complex than a single POST.
- Negative: Signed URLs expire. If a teacher's upload is interrupted and they retry after the URL expires, they must request a new URL from the API.


**References**: [02-api-architecture.md](./02-api-architecture.md), [08-pipeline-integration.md](./08-pipeline-integration.md), [05-client-applications.md](./05-client-applications.md)

---

## ADR-012: Two-Tier API Architecture

**Status**: Accepted
**Date**: 2025-03-19

**Context**: The platform has two distinct concerns: (1) a public-facing application layer handling identity, permissions, multi-tenancy, domain CRUD, and upload orchestration, and (2) an internal CV pipeline that processes video through 8 stages and returns raw results keyed by bib numbers. The pipeline was built independently as a standalone FastAPI service and has no concept of users, schools, or permissions. The application layer needs to wrap the pipeline with domain logic -- mapping bib numbers to students, enforcing permissions, and orchestrating uploads.

**Decision**: Use a two-tier API architecture. The Application API is the public-facing service that all clients talk to. The Pipeline API is an internal service that only the Application API calls. They are separate services with separate codebases, databases, and deployment units.

**Alternatives Considered**:

| Alternative | Pros | Cons |
|---|---|---|
| **Single API (merge pipeline into Application API)** | One service to deploy, monitor, and maintain. No inter-service communication overhead. | Violates separation of concerns. The pipeline is GPU-bound, CPU-intensive code; the Application API is I/O-bound request routing. Merging them means scaling GPU and API together (expensive). Any change to permission logic risks breaking the pipeline. The pipeline team would need to work in the same codebase as the application team. |
| **BFF pattern (Backend for Frontend)** | A dedicated backend per client (Teacher BFF, Coach BFF, etc.) that aggregates calls to underlying services | Massive overhead for a small team. 3-5 BFF services plus the Pipeline API. Duplicated logic across BFFs. Only justified when clients have radically different data needs -- here, all clients talk to the same domain model. |
| **GraphQL gateway** | Flexible querying for dashboards. Clients request exactly the data they need. Reduces over-fetching. | Additional complexity (schema definition, resolvers, N+1 query problems). The dashboards can be served efficiently by purpose-built REST endpoints. GraphQL shines when clients have unpredictable query patterns -- here, the query patterns are known and finite. Adds a learning curve for the team. |

**Rationale**:
- **Pipeline stays isolated**: The CV pipeline is a standalone system with its own expertise domain. It should not know about users, schools, or permissions. The two-tier boundary ensures the pipeline team can iterate on computer vision without touching application logic, and vice versa.
- **Independent scaling**: The Application API scales horizontally on Cloud Run (I/O-bound). The Pipeline API scales by adding GPU VMs (compute-bound). These are fundamentally different scaling dimensions that should not be coupled.
- **Clear integration contract**: The Application API calls the Pipeline API via REST (`POST /upload`, `GET /results/{job_id}`). The contract is narrow and well-defined. Changes to either side of the boundary are independent as long as the contract holds.
- **BFF is overkill**: All clients (Teacher App, Coach Web, School Head Web) interact with the same domain model through the same Application API. Role-based views are handled by OpenFGA permission checks, not separate backends.
- **GraphQL deferred**: REST endpoints designed for known use cases are simpler to build, cache, and secure. If dashboard query patterns become complex enough to justify GraphQL, it can be added as a layer on top of the Application API later.

**Consequences**:
- Positive: Clean separation of concerns. Application logic and CV pipeline evolve independently.
- Positive: Independent scaling. Application API and Pipeline API scale along different dimensions (request volume vs GPU compute).
- Positive: The pipeline team can work on their service without understanding ZITADEL, OpenFGA, or the domain model.
- Negative: Inter-service communication adds latency (HTTP call from Application API to Pipeline API). Acceptable -- these calls are infrequent (job submission and status polling).
- Negative: Two services to deploy, monitor, and troubleshoot. Correlation IDs in logs mitigate debugging difficulty.
- Negative: Data mapping between pipeline output (bib numbers) and application entities (students) is the Application API's responsibility. This is additional code, but it is inherently application logic.

**References**: [02-api-architecture.md](./02-api-architecture.md), [08-pipeline-integration.md](./08-pipeline-integration.md), [00-system-overview.md](./00-system-overview.md)

---

## ADR-013: Self-Hosted ZITADEL

**Status**: Accepted
**Date**: 2025-03-19

**Context**: ZITADEL can be deployed as a self-hosted instance (Docker/Kubernetes) or used as ZITADEL Cloud (managed SaaS). The platform handles personal data of minor students under POPIA (South Africa's data protection law). Data residency, cost control, and independence from third-party SaaS availability are considerations. The team is small and operational overhead matters.

**Decision**: Self-host ZITADEL on the platform's GCP infrastructure.

**Alternatives Considered**:

| Alternative | Pros | Cons |
|---|---|---|
| **ZITADEL Cloud (managed SaaS)** | Zero ops -- ZITADEL handles uptime, backups, upgrades. Faster to start. Free tier for development. | Data hosted outside South Africa (POPIA concern for student identity data). Monthly cost scales with MAUs. Dependency on third-party SaaS availability -- if ZITADEL Cloud has an outage, no one can log in. Less control over configuration and customisation. |
| **Managed auth service (Auth0, Cognito)** | Mature managed services with guaranteed SLAs. | See ADR-001 for why Auth0 was rejected. All managed services share the POPIA data residency concern and vendor lock-in risk. |

**Rationale**:
- **POPIA data residency**: The platform stores identity data for school staff who manage minor students' records. Hosting identity data on a third-party SaaS with servers outside South Africa creates regulatory uncertainty under POPIA. Self-hosting keeps identity data within the platform's controlled GCP infrastructure.
- **Cost predictability**: Self-hosted ZITADEL has zero per-MAU cost. The only cost is the compute (Cloud Run instance or small VM -- ~$10-30/month). ZITADEL Cloud would cost more as the platform scales.
- **No external dependency for authentication**: If ZITADEL Cloud has an outage, the entire platform is locked out. Self-hosting means authentication availability is tied to the platform's own infrastructure, which the team controls.
- **Full configuration control**: Self-hosting allows custom branding, login page customisation, email template control, and fine-tuning of token lifetimes, session policies, and security settings.
- **ZITADEL is lightweight**: Written in Go, single binary, backed by PostgreSQL (already provisioned). Running it is not operationally burdensome -- it is comparable to running any other containerised service.

**Consequences**:
- Positive: Identity data stays within the platform's infrastructure. POPIA compliance is cleaner.
- Positive: No per-MAU cost. Predictable infrastructure spend.
- Positive: No external dependency for the authentication critical path.
- Negative: The team owns ZITADEL's uptime. If it crashes, no one can log in. Mitigated by Cloud Run's auto-restart and health checks, or a dedicated VM with systemd supervision.
- Negative: The team is responsible for ZITADEL upgrades. Must track releases and apply security patches. Mitigated by Docker image pinning and staged rollouts.
- Negative: Initial setup is more work than signing up for ZITADEL Cloud. ZITADEL Cloud can still be used for local development to simplify the dev stack.

**References**: [03-authentication.md](./03-authentication.md), [07-infrastructure.md](./07-infrastructure.md)

---

## ADR-014: Polling for Pipeline Status

**Status**: Accepted
**Date**: 2025-03-19

**Context**: After a teacher uploads a video and the pipeline begins processing, the Teacher App needs to display progress. Processing takes 30-120 seconds across 8 pipeline stages. The client needs to know: (a) is processing still running, and (b) ideally, which stage is currently executing. The existing Pipeline API exposes `GET /results/{job_id}` which returns a top-level status (`pending`, `processing`, `complete`, `failed`).

**Decision**: Use polling for pipeline status in the MVP. The Teacher App polls the Application API at a fixed interval (e.g., every 5 seconds), which in turn polls the Pipeline API. WebSocket or Server-Sent Events are deferred to a future enhancement.

**Alternatives Considered**:

| Alternative | Pros | Cons |
|---|---|---|
| **WebSocket** | Real-time, bidirectional. Near-instant stage-level updates. No wasted requests. | Requires WebSocket infrastructure in the Application API (connection management, heartbeats, reconnection logic). Cloud Run supports WebSockets but with constraints (idle timeout). Significant additional complexity for a feature used during a 30-120 second window. The pipeline does not currently emit events -- stage-level data is in Redis via Celery `update_state()`, not pushed to consumers. |
| **Server-Sent Events (SSE)** | Simpler than WebSocket (unidirectional). Works over standard HTTP. Native browser support. | Same infrastructure concern as WebSocket -- the Application API must maintain long-lived connections. Cloud Run charges for connection duration. The pipeline does not push events. SSE requires the Application API to poll Redis internally and stream updates, adding complexity without eliminating the polling pattern. |
| **Webhooks (pipeline calls back)** | Pipeline notifies Application API on completion. No polling required. | Only provides completion notification, not stage-level progress. The pipeline currently has no callback mechanism -- adding one requires pipeline code changes. Does not solve the client-to-API communication problem (client still needs to know when it is done). |

**Rationale**:
- **Simplest implementation**: Polling requires zero additional infrastructure. The client calls a GET endpoint on a timer. The Application API calls the Pipeline API. Both are standard HTTP requests. Works today with existing code.
- **Processing is short-lived**: 30-120 seconds is a brief window. Polling every 5 seconds means 6-24 requests per clip -- negligible load. The overhead of those extra requests is far less than the complexity of WebSocket/SSE infrastructure.
- **Cloud Run compatibility**: Polling is naturally stateless. WebSocket and SSE connections would require sticky sessions or connection affinity, which adds Cloud Run configuration complexity.
- **Pipeline does not push events**: The Celery worker calls `self.update_state()` which writes to Redis, but nothing subscribes to those updates. Implementing WebSocket or SSE would require building a pub/sub layer between Redis and the Application API. Polling simply reads the current state.
- **Stage-level progress can be added incrementally**: The first enhancement is a `GET /status/{job_id}` endpoint on the Pipeline API that exposes per-stage progress (reading from Celery's Redis state). This improves the UX within the polling model without requiring WebSocket infrastructure.

**Consequences**:
- Positive: Zero additional infrastructure. Works with existing Pipeline API endpoints.
- Positive: Stateless -- compatible with Cloud Run's scaling model.
- Positive: Simple to implement, test, and debug.
- Negative: Latency equal to the polling interval (up to 5 seconds) between a state change and the client seeing it. Acceptable for a teacher watching a progress screen.
- Negative: Wasted requests -- most poll responses return the same status. At 5-second intervals for 60 seconds, that is 12 requests per clip, of which ~11 return "still processing." Negligible at current scale.
- Negative: Does not scale elegantly if many teachers poll simultaneously for many clips. At high scale, event-driven (WebSocket/SSE) would be more efficient. This is a future concern.

**References**: [08-pipeline-integration.md](./08-pipeline-integration.md), [05-client-applications.md](./05-client-applications.md)

---

## ADR-015: UUID for Student Identity

**Status**: Accepted
**Date**: 2025-03-19

**Context**: Students are the central entity whose results must persist across time and across schools. A student who transfers from School A to School B should retain all historical results. The identity key must be stable, unique, and not tied to any single school. Students are minors -- they do not have email addresses or national IDs that can reliably serve as identifiers. Students are created by teachers, not by self-registration.

**Decision**: Use system-generated UUIDs as the primary and permanent identifier for students. Students are identified by `Student.id` (UUID), not by school admission numbers, national IDs, or any other external identifier.

**Alternatives Considered**:

| Alternative | Pros | Cons |
|---|---|---|
| **School admission numbers** | Familiar to teachers. Already exists in school systems. Easy to communicate. | Changes when a student transfers schools. Not unique across schools (two schools could both have admission number "12345"). Would break the link between a student and their historical results on transfer. |
| **South African national ID number** | Globally unique. Permanent. Government-issued. | Not all primary school students have ID numbers (issued at 16, or earlier by application). Collecting and storing national IDs for minors creates significant POPIA liability. Parents may refuse to provide them. Not available at the point of student creation (teacher enrolling a student during a PE session). |
| **Email address** | Unique (if personal). Familiar. | Primary school students typically do not have personal email addresses. School-issued emails change on transfer. Creates a dependency on email infrastructure. |
| **Composite key (school_id + admission_number)** | Unique within the system at a point in time. No additional infrastructure. | Breaks on transfer -- the student gets a new composite key at the new school. Historical results would need re-keying. Fundamentally incompatible with portable student records. |

**Rationale**:
- **Stability across transfers**: The UUID is generated once when a teacher creates a student record. It never changes, regardless of which school the student attends. All results are permanently linked to this UUID.
- **No external dependency**: UUIDs are generated by the system. No reliance on national ID infrastructure, email providers, or school administrative systems. A teacher can enrol a student with just a name and date of birth.
- **POPIA minimisation**: Not collecting national IDs for minors reduces the platform's PII exposure. The UUID is a pseudonymous identifier that only has meaning within the Vigour platform.
- **Uniqueness guarantee**: UUIDv4 is collision-proof for practical purposes. No coordination needed between schools.
- **Transfer mechanics**: When a student transfers, the `Student` record's `school_id` is updated and OpenFGA tuples are rewritten. The UUID stays the same. Old school loses access (tuples deleted), new school gains access (tuples written). All historical `Result` records remain linked to the UUID.

**Consequences**:
- Positive: Student identity is permanent and portable. Results travel with the student forever.
- Positive: No PII (national ID, email) required for identity. Reduces POPIA compliance surface.
- Positive: Transfer is a simple update -- change `school_id`, rewrite OpenFGA tuples. No data migration or re-keying.
- Negative: UUIDs are not human-readable. Teachers cannot identify a student by their UUID -- they use name and bib number. The UUID is a system-level concept, not a user-facing one.
- Negative: Duplicate student risk. If a student is created at School A and then created again (as a new record) at School B instead of being transferred, they get two UUIDs and their historical results are split. Mitigation requires a deduplication mechanism (match by name + date of birth + previous school) during the transfer workflow.
- Negative: No cross-platform identity. If the student exists in another school management system, there is no way to link the Vigour UUID to their external record without an additional mapping table.

---

---

## ADR-017: Ephemeral Cross-Region GPU Processing

**Status**: Accepted
**Date**: 2026-03-23

**Context**: The CV pipeline requires NVIDIA L4 GPUs for video processing (detection, tracking, pose estimation). GCP does not offer GPU instances in `africa-south1` (Johannesburg). Video is personal data — it contains identifiable children. POPIA requires data residency for PII. The platform needs GPU processing for the CV pipeline but cannot store video outside South Africa.

**Decision**: Use ephemeral GPU VMs in a designated European GPU processing region (the specific region is an infrastructure decision documented in [07-infrastructure.md](./07-infrastructure.md)). Video is pulled from GCS `africa-south1`, processed in memory/tmpfs, fitness metrics are written to the Pipeline DB, and the local video copy is auto-purged on job completion. No persistent video storage occurs outside `africa-south1`.

**Alternatives Considered**:

| Alternative | Pros | Cons |
|---|---|---|
| **Wait for GPU availability in africa-south1** | Full data residency compliance. No cross-region transfer. | No timeline from GCP. Blocks the entire platform indefinitely. |
| **CPU-only processing in africa-south1** | Data stays in South Africa. No cross-region concerns. | Pipeline stages (SAM2, YOLOv8, ViTPose) require GPU for acceptable performance. CPU processing would take 10-100x longer, making the platform unusable for real-time feedback to teachers. |
| **Hetzner GPU servers in South Africa** | South African data residency. Cheaper GPU pricing. | No managed services. Cross-provider networking complexity. Signed URLs tied to GCS. Split infrastructure for a small team. |
| **AWS af-south-1 GPU instances** | South African region. Data residency solved. | Only G4 (NVIDIA T4, 16 GB VRAM) available — no L4. GPU pricing ~30% higher than GCP. Would require full cloud migration. |

**Rationale**:
- **Only viable path given GPU availability**: No major cloud provider offers L4-class GPUs in South Africa. Ephemeral cross-region processing is the only way to ship the product.
- **Ephemeral processing satisfies the spirit of data residency**: Video is not "stored" in Europe. It is pulled into memory/tmpfs, processed, and the local copy is auto-purged. The processing is transient — measured in seconds to minutes, not hours or days. No video persists on the GPU VM's disk after job completion.
- **Audit logging of every transfer**: Every cross-region video pull is audit-logged with job ID, video hash, source bucket, processing region, start time, end time, and purge confirmation. This creates an auditable trail for POPIA compliance.
- **Network controls restrict GPU VM egress**: The GPU VM can only communicate with GCS (to pull/push video) and the Pipeline DB (to write stage outputs and results). No other egress is permitted. The VM cannot exfiltrate video to any other destination.
- **Auto-purge is enforced, not optional**: The Celery worker's `finally` block purges local video files. A secondary cron job on the GPU VM purges any files older than 1 hour as a safety net. Tmpfs storage is wiped on VM restart.

**Consequences**:
- Positive: Unblocks GPU processing without waiting for GCP africa-south1 GPU availability.
- Positive: Ephemeral processing model limits the privacy exposure window to the duration of processing (seconds to minutes).
- Positive: Audit trail provides evidence of compliance for regulators.
- Negative: Cross-region latency for video pull from africa-south1 to the designated European GPU processing region. Acceptable — the pipeline is fully asynchronous (teacher uploads, polls for results). Video transfer time adds to total processing time but does not affect user experience.
- Negative: Requires explicit data processing agreements documenting the ephemeral cross-region processing model, retention limits, and auto-purge guarantees.
- Negative: Auto-purge must be verified and monitored. A failure in the purge mechanism would leave video on the GPU VM, violating the ephemeral processing guarantee. Monitoring and alerting on purge failures is mandatory.
- Negative: Audit logging of every cross-region transfer adds operational overhead and storage requirements for audit logs.

**Decision to revisit if**:
- GCP launches GPU instances in `africa-south1`, which would eliminate the need for cross-region processing entirely.
- A South African GPU hosting provider offers managed infrastructure compatible with the pipeline's requirements.

**References**: [07-infrastructure.md](./07-infrastructure.md), [08-pipeline-integration.md](./08-pipeline-integration.md)

---

## ADR-018: Video Metadata Stripping at Ingestion

**Status**: Accepted
**Date**: 2026-03-23

**Context**: Video files captured on mobile devices contain EXIF metadata (GPS coordinates, device serial number, device model) and an audio track. GPS reveals the precise location where the video was recorded. Audio contains voiceprints (biometric data under COPPA 2025 rules) and incidental conversations, which are a privacy risk when handling recordings of minor children. Neither GPS coordinates nor audio is needed for fitness metric extraction — the CV pipeline operates on visual frames only.

**Decision**: Strip the audio track and GPS/device metadata from video files at ingestion (Stage 0), before pipeline processing. Implemented via FFmpeg (`-an` to remove audio, `-map_metadata -1` to strip metadata). The video creation timestamp may be preserved as a cross-check against the session timestamp.

**Alternatives Considered**:

| Alternative | Pros | Cons |
|---|---|---|
| **Strip nothing — process raw video** | Simplest. No additional processing step. | GPS, audio, and device metadata persist through the pipeline and into storage. Audio is a biometric liability. GPS is redundant (school location is already recorded via session records). Violates data minimisation principle. |
| **Strip metadata but keep audio** | Removes GPS/device data. Audio might be useful for future features (e.g., whistle detection for timing). | Voiceprints are biometric under COPPA 2025. Incidental conversations are a privacy risk. The CV pipeline does not use audio. Keeping it "just in case" contradicts privacy-by-design. |
| **Strip at pipeline processing (later stage)** | Stripping happens closer to the processing code. | Metadata and audio persist in GCS between upload and processing — a window where raw data is stored unnecessarily. Stripping at ingestion closes this window. |

**Rationale**:
- **GPS is redundant**: Traceability is maintained through session records — `school_id`, `teacher_id`, `session_timestamp`. GPS coordinates add no value and create a precise location tracking risk.
- **Audio is a liability**: Voiceprints are classified as biometric data under COPPA 2025 rules. Incidental conversations between children are a privacy risk. The CV pipeline processes visual frames only — audio is never used.
- **Stripping at ingestion prevents downstream exposure**: By stripping at Stage 0 (before any pipeline processing), no downstream system — pipeline workers, GPU VMs, logging, error reports — ever sees GPS, device metadata, or audio. This is data minimisation enforced at the earliest possible point.
- **FFmpeg is lightweight and proven**: FFmpeg's stream copy mode (`-c copy -an -map_metadata -1`) re-muxes without re-encoding, so the processing overhead is minimal (seconds, not minutes). The video quality is unchanged.
- **Smaller file sizes**: Removing the audio track reduces file size, which reduces storage costs and cross-region transfer time (relevant for ADR-017 ephemeral GPU processing).

**Consequences**:
- Positive: Reduced privacy surface — no GPS, no device identifiers, no audio in stored or processed video.
- Positive: Smaller file sizes without audio, reducing storage and transfer costs.
- Positive: Data minimisation enforced at the earliest point in the pipeline. Downstream systems cannot accidentally log or expose metadata they never receive.
- Negative: FFmpeg adds a processing step before pipeline submission. For a 1 GB video file, stream-copy re-muxing takes seconds — acceptable overhead.
- Negative: Audio is permanently removed. If a future feature requires audio (unlikely for fitness testing), it cannot be recovered from processed files. The original upload could be retained briefly in a quarantine bucket if a grace period is desired, but this conflicts with the minimisation principle.
- Negative: Video creation timestamp preservation requires selective metadata handling rather than blanket stripping. The FFmpeg command must be carefully constructed to strip all metadata except the creation timestamp.

**References**: [08-pipeline-integration.md](./08-pipeline-integration.md), [02-api-architecture.md](./02-api-architecture.md)


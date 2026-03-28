# Vigour

Vigour automates physical fitness assessments for South African schools. A teacher records video of learners performing fitness tests, uploads it, and the CV pipeline extracts performance data automatically. Results flow through to students, coaches, and school heads — each with a role-appropriate view.

## Supported Fitness Tests

| Test | Attribute | Metric | Unit |
|------|-----------|--------|------|
| Vertical Jump | Explosiveness | Jump height | cm |
| 5m Sprint | Speed | Time | seconds |
| Shuttle Run | Fitness | Distance per 15s set | metres |
| Cone Drill | Agility | Completion time | seconds |
| Single-Leg Balance | Balance | Hold duration | seconds |

## Repository Structure

```
vigour/
├── api/                # Application API (FastAPI) — auth, permissions, domain logic
├── pipeline/           # CV pipeline — video processing, metric extraction
├── apps/
│   ├── teacher/        # Teacher App (Expo / React Native) — recording, results
│   └── web/            # Web platform (React SPA) — dashboards, admin
├── pipeline-poc/       # Original proof-of-concept pipeline (reference)
├── models/             # ML model weights (LFS-tracked)
├── infra/              # Terraform, deployment configs
└── docs/
    └── architecture/   # System architecture documentation
```

## Architecture

The platform uses a two-tier API design:

- **Application API** — public-facing service handling identity (ZITADEL), authorization (OpenFGA), multi-tenancy, domain CRUD, upload orchestration, and result ingestion.
- **Pipeline API** — internal service for CV processing. Receives video, runs 8-stage pipeline (Ingest, Detect, Track, Pose, OCR, Calibrate, Extract, Output), returns structured results keyed by bib number.

Clients never talk to the pipeline directly. The Application API wraps the pipeline with domain logic — mapping bib numbers to students, enforcing permissions, and orchestrating uploads via signed GCS URLs.

See [docs/architecture/](docs/architecture/) for the full architecture documentation, including domain model, data flow, authentication, authorization, and infrastructure decisions.

## Pipeline POC

The original proof-of-concept pipeline is preserved in `pipeline-poc/` for reference. See [pipeline-poc/README.md](pipeline-poc/README.md) for setup and usage instructions.

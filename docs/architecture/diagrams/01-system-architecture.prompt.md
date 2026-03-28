# 01 - System Architecture

**Tool**: `gemini --yolo "/diagram '...'"`
**Generated**: 2026-03-24

## Prompt

```
Vigour Platform System Architecture diagram with 6 layers:

Client Layer: Teacher App (Expo / React Native), Learner App (future), Coach Dashboard (React SPA), School Head Dashboard (React SPA)

Auth & Consent Layer: ZITADEL OIDC, OpenFGA permissions, Consent Module

Application API: FastAPI - Tier 1 core (UUID-only, core_data schema), Tier 2 identity-aware (enriches with identity schema), consent middleware

CV Pipeline: Pipeline API (africa-south1), Ephemeral GPU Workers (European region, auto-purge after processing)

Storage: Application DB PostgreSQL (3 schemas: core_data, identity, consent), Pipeline DB PostgreSQL, GCS africa-south1, Redis

Data Residency: All persistent storage in africa-south1. GPU processing ephemeral in European region with auto-purge.

Show connections between layers. Modern clean style with color-coded layers. Annotate data residency regions.
```

## Regenerate

```bash
cd docs/architecture/diagrams
GEMINI_API_KEY="$NANOBANANA_GEMINI_API_KEY" gemini --yolo "/diagram 'Vigour Platform System Architecture diagram with 6 layers:

Client Layer: Teacher App (Expo / React Native), Learner App (future), Coach Dashboard (React SPA), School Head Dashboard (React SPA)

Auth & Consent Layer: ZITADEL OIDC, OpenFGA permissions, Consent Module

Application API: FastAPI - Tier 1 core (UUID-only, core_data schema), Tier 2 identity-aware (enriches with identity schema), consent middleware

CV Pipeline: Pipeline API (africa-south1), Ephemeral GPU Workers (European region, auto-purge after processing)

Storage: Application DB PostgreSQL (3 schemas: core_data, identity, consent), Pipeline DB PostgreSQL, GCS africa-south1, Redis

Data Residency: All persistent storage in africa-south1. GPU processing ephemeral in European region with auto-purge.

Show connections between layers. Modern clean style with color-coded layers. Annotate data residency regions.'"
```

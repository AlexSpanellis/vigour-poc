# 04 - API Module Map

**Tool**: `gemini --yolo "/diagram '...'"`
**Generated**: 2026-03-24

## Prompt

```
API Module Map for Vigour Platform Application API. Show the Application API as a large container with route groups organised by tier:

MIDDLEWARE CHAIN (shown as sequential pipeline at top):
JWT Validation → User Context Extraction → OpenFGA Permission Check → Consent Check → Route Handler

TIER 1 - CORE API (UUID-only, core_data schema):
- Sessions (/sessions) - TestSession lifecycle - teacher
- Clips (/sessions/{id}/clips) - Video upload orchestration, signed URLs - teacher
- Results (/sessions/{id}/results) - Pipeline results, review, approve/reject - teacher
- Schools (/schools) - CRUD, contract-based onboarding - super_admin
- Classes (/schools/{id}/classes) - Class management, student membership - school_head, teacher
- BibAssignments (/sessions/{id}/bib-assignments) - Assign bibs to students - teacher

TIER 2 - IDENTITY-AWARE API (enriches with identity schema):
- Student Profiles (/students/{id}/profile) - Historical results with identity - teacher, coach, school_head
- Reporting (/reports) - Aggregated views with identity enrichment - coach, school_head

CONSENT ROUTES:
- Consent Status (/consent/{student_id}/status) - Check consent state
- Record Consent (/consent) - Record new consent
- Withdraw Consent (/consent/{id}/withdraw) - Withdraw existing consent
- Audit Trail (/consent/audit) - Consent audit log

AUTH MODULE:
- Auth (/auth) - Login callbacks, token refresh, logout, delegates to ZITADEL

ADMIN MODULE:
- Admin (/admin) - System admin, onboarding, platform config - super_admin

Show external connections from Application API to: ZITADEL (OIDC token validation), OpenFGA (permission checks), Consent Module (consent verification), Application DB PostgreSQL (3 schemas), Pipeline API (job submission), GCS (signed URLs), Redis (caching)

INTERNAL PIPELINE API (separate service, africa-south1):
- POST /upload, GET /results/{job_id}, GET /annotated/{job_id}, GET /health, cache management endpoints

Modern clean style, group modules by tier with color coding. Show middleware chain as a horizontal pipeline.
```

## Regenerate

```bash
cd docs/architecture/diagrams
GEMINI_API_KEY="$NANOBANANA_GEMINI_API_KEY" gemini --yolo "/diagram 'API Module Map for Vigour Platform Application API. Show the Application API as a large container with route groups organised by tier:

MIDDLEWARE CHAIN (shown as sequential pipeline at top):
JWT Validation → User Context Extraction → OpenFGA Permission Check → Consent Check → Route Handler

TIER 1 - CORE API (UUID-only, core_data schema):
- Sessions (/sessions) - TestSession lifecycle - teacher
- Clips (/sessions/{id}/clips) - Video upload orchestration, signed URLs - teacher
- Results (/sessions/{id}/results) - Pipeline results, review, approve/reject - teacher
- Schools (/schools) - CRUD, contract-based onboarding - super_admin
- Classes (/schools/{id}/classes) - Class management, student membership - school_head, teacher
- BibAssignments (/sessions/{id}/bib-assignments) - Assign bibs to students - teacher

TIER 2 - IDENTITY-AWARE API (enriches with identity schema):
- Student Profiles (/students/{id}/profile) - Historical results with identity - teacher, coach, school_head
- Reporting (/reports) - Aggregated views with identity enrichment - coach, school_head

CONSENT ROUTES:
- Consent Status (/consent/{student_id}/status) - Check consent state
- Record Consent (/consent) - Record new consent
- Withdraw Consent (/consent/{id}/withdraw) - Withdraw existing consent
- Audit Trail (/consent/audit) - Consent audit log

AUTH MODULE:
- Auth (/auth) - Login callbacks, token refresh, logout, delegates to ZITADEL

ADMIN MODULE:
- Admin (/admin) - System admin, onboarding, platform config - super_admin

Show external connections from Application API to: ZITADEL (OIDC token validation), OpenFGA (permission checks), Consent Module (consent verification), Application DB PostgreSQL (3 schemas), Pipeline API (job submission), GCS (signed URLs), Redis (caching)

INTERNAL PIPELINE API (separate service, africa-south1):
- POST /upload, GET /results/{job_id}, GET /annotated/{job_id}, GET /health, cache management endpoints

Modern clean style, group modules by tier with color coding. Show middleware chain as a horizontal pipeline.'"
```

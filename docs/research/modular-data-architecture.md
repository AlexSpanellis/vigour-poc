# Modular Data Architecture: Privacy by Default, Identity by Module

**Research Date:** March 2026
**Status:** Architectural research — not a final design
**Context:** Vigour is a CV-based fitness testing platform that will deploy internationally. This document proposes a layered, jurisdiction-agnostic data architecture that separates anonymised performance data from personally identifiable information, enabling deployment in any country without modifying the core system.

**Deployment priority:** SA MVP first, UK expansion second. This document presents the complete framework but marks each recommendation by phase: **MVP** (SA launch), **Phase 2** (UK/EU expansion), or **Phase 3+** (aspirational/future scale).

**Disclaimer:** This document is architectural research and exploration. It does not constitute a final technical design or legal advice. All regulatory interpretations should be validated by qualified legal counsel in each target jurisdiction before implementation.

---

## Table of Contents

1. [Core Architecture Principle](#1-core-architecture-principle)
2. [Layered Data Architecture](#2-layered-data-architecture)
3. [Country Module Design](#3-country-module-design)
4. [Video Data Strategy](#4-video-data-strategy)
5. [Cross-Border Data Flow](#5-cross-border-data-flow)
6. [Technical Implementation Considerations](#6-technical-implementation-considerations)
7. [Building the Layered Schema](#7-building-the-layered-schema)
8. [References and Related Documents](#8-references-and-related-documents)
9. [Appendix A: US Jurisdiction Module](#appendix-a-us-jurisdiction-module)

---

## 1. Core Architecture Principle

### "Privacy by Default, Identity by Module"

The fundamental design principle is that Vigour's core system operates entirely on anonymised, pseudonymised data. It knows nothing about who a student is — only what they did. Identity is bolted on at the edges, through pluggable modules that vary by jurisdiction.

```
┌──────────────────────────────────────────────────────────┐
│                    VIGOUR CORE SYSTEM                     │
│                                                          │
│   Knows: UUID-1234 scored 8.2 on the beep test           │
│   Does NOT know: UUID-1234 is Thabo Mokoena, ID 0412...  │
│                                                          │
│   This system is identical in every country.              │
└──────────────────────────────────────────────────────────┘
         │                              │
    ┌────▼────┐                    ┌────▼────┐
    │ SA      │                    │ UK      │
    │ Identity│                    │ Identity│
    │ Module  │                    │ Module  │
    │         │                    │         │
    │ LURITS, │                    │ UPN,    │
    │ SA ID,  │                    │ Name,   │
    │ POPIA   │                    │ UK GDPR │
    │ consent │                    │ consent │
    └─────────┘                    └─────────┘
```

### Design Tenets

1. **The core system must be deployable in any jurisdiction without modification.** No country-specific logic in the core data layer. No PII in the core database. No consent logic embedded in the pipeline.

2. **PII is always external to the core.** Student names, national IDs, school enrollment numbers — all of it lives in jurisdiction-specific modules that connect to the core via a clean interface.

3. **The system must work with zero PII.** A school could deploy Vigour with no identity module at all — students would be tracked as anonymous UUIDs, and results would be reported at aggregate level. This is the baseline.

4. **Identity modules are additive, not integral.** Each deployment adds exactly the identity layer it needs, constrained by that jurisdiction's regulations. The core never reaches into the identity module; the identity module wraps the core.

5. **Data minimisation is structural, not policy.** It is architecturally impossible for the core system to access PII, not just against policy. The separation is enforced at the database, encryption, and API level.

### Why This Matters for International Expansion

Vigour cannot predict which country will be its next market. Building a POPIA-specific system that must be re-engineered for the UK, then re-engineered again for the US, then again for the UAE, is unsustainable. By making the core jurisdiction-agnostic, Vigour can enter a new market by building only a new identity/consent module — the core system, the CV pipeline, the scoring engine, and the analytics layer remain untouched.

---

## 2. Layered Data Architecture

> **Implementation note:** The 5-layer model is presented as a complete framework. For the SA MVP and UK expansion (2 jurisdictions), the implementation is simpler: the layers map to PostgreSQL schemas within a single Cloud SQL instance, with a `jurisdiction_config` table driving per-jurisdiction behaviour. The full module framework (YAML configs, module loading, per-jurisdiction key management) is **Phase 3+** work for when additional jurisdictions are added.

The architecture is organised into five layers, each with distinct data ownership, access controls, and retention characteristics.

```
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 4: Reporting & Analytics                                  │
│ Aggregated data, k-anonymity guarantees, public-facing          │
├─────────────────────────────────────────────────────────────────┤
│ LAYER 3: Consent & Compliance Module (Pluggable)                │
│ Consent records, audit trails, DSAR handling                    │
├─────────────────────────────────────────────────────────────────┤
│ LAYER 2: Identity Module (Pluggable)                            │
│ UUID ↔ external identity mapping, PII storage                   │
├─────────────────────────────────────────────────────────────────┤
│ LAYER 1: Anonymised Core Data                                   │
│ UUIDs, fitness scores, metrics, session metadata                │
├─────────────────────────────────────────────────────────────────┤
│ LAYER 0: Ephemeral Processing                                   │
│ Video ingestion, CV/ML pipeline, metric extraction              │
└─────────────────────────────────────────────────────────────────┘
```

---

### Layer 0: Ephemeral Processing Layer

**Purpose:** Ingest video, run the CV/ML pipeline, extract performance metrics, and discard raw data.

#### What Happens Here

1. Video is captured at the school (cameras recording fitness tests)
2. Video is transmitted to the processing environment (edge or cloud — see Section 4)
3. **Pre-processing (**MVP**):** Strip audio track and device-identifying metadata (GPS coordinates, device serial number, device model) from video EXIF/metadata at ingestion using FFmpeg before any further processing. This is a Stage 0 operation before the existing 8-stage pipeline. Audio contains voiceprints (biometric under COPPA 2025) and incidental conversations. GPS and device metadata are personal information and a privacy liability — traceability is maintained through the session record in the application layer (school_id UUID, teacher_id, upload timestamp, test_type), not through embedded file metadata. Video creation timestamp from EXIF may optionally be preserved as a cross-check against the session timestamp. Neither audio nor device-identifying metadata is needed for fitness metric extraction.
4. The CV pipeline processes the video:
   - Object detection (SAM2 / tracking models)
   - Pose estimation
   - Motion analysis
   - Performance metric extraction (lap counts, rep counts, distances, times)
5. Extracted metrics are written to Layer 1 as anonymised data points
6. Raw video enters the retention/deletion decision path

#### Data in This Layer

| Data | Nature | Sensitivity |
|------|--------|-------------|
| Raw video | Biometric (faces, body shape, movement) | Very High |
| Intermediate CV outputs (bounding boxes, pose skeletons) | Derived, potentially re-identifiable | High |
| Model inference logs | Technical | Low-Medium |
| Extracted metrics (final output) | Anonymised performance data | Low (moves to Layer 1) |

#### Video Retention Policy

This is the most consequential decision in the architecture and must be configurable per jurisdiction. Three modes:

**Mode A: Immediate Delete**
- Video is processed in memory or temporary storage
- Deleted immediately after metric extraction
- Lowest regulatory burden
- No ability to re-process, audit, or resolve disputes

**Mode B: Retain with Linked Metrics**
- Video retained for the lifecycle of the linked metrics — the video is the source of truth for the scores it produces
- 0–90 days: hot storage (GCS Standard) for active access — teacher review, re-processing, dispute resolution
- 90 days onwards: cold storage (GCS Nearline, then Coldline) with restricted access, audit-logged retrieval only for disputes, re-processing, or quality assurance
- Deleted when linked metrics are deleted, or on consent withdrawal
- On consent withdrawal with Layer 2 identity deletion, the video becomes unlinked (no way to associate it with an individual), reducing privacy risk of continued storage
- No fixed maximum retention period by default — configurable per jurisdiction via `video_max_retention_days` (NULL = retain with metrics)
- Retained video must be encrypted at rest and access-controlled

**Mode C: Archival with Anonymisation**
- Video is anonymised (face blurring, body outline replacement) and then archived
- Original video is deleted after anonymisation
- Useful for model training, research, quality assurance
- Anonymised video has reduced (but not zero) regulatory burden
- See Section 4 for a deeper analysis of anonymisation sufficiency

**The default should be Mode B (retain with linked metrics).** The video is the evidence chain for the metrics — if a parent disputes a score, the source video is needed. Pipeline improvements require re-processing original video. Quality assurance requires comparing pipeline output against source. Deleting video while retaining metrics removes the evidence chain. Privacy risk is mitigated by cold storage with restricted access after 90 days, audit logging, and the identity-unlinking mechanism on consent withdrawal. Mode A (immediate delete) should be available as an option for privacy-sensitive deployments where regulatory requirements demand it.

#### Edge vs Cloud Processing

| Factor | Edge (on-premises at school) | Cloud |
|--------|------------------------------|-------|
| Data residency | Video never leaves school premises | Video transmitted to cloud provider |
| Latency | Real-time processing possible | Depends on upload bandwidth |
| Hardware cost | GPU/compute at each site | Shared infrastructure, lower per-unit cost |
| Regulatory simplicity | Stronger position — data stays local | Must satisfy data transfer rules |
| Maintenance | Physical hardware at each school | Centralised, easier to update |
| Scalability | Limited by on-site hardware | Elastic |
| Security surface | Physical security of school | Cloud provider security |

**Recommendation:** Cloud processing is the only viable path for the SA MVP and near-term deployments. Edge processing is a long-term aspiration, not a near-term plan. The realities of the SA public school environment make on-premises GPU processing impractical:

- **Unreliable power:** South Africa has experienced years of load-shedding. Schools cannot guarantee continuous power for GPU hardware.
- **Limited internet bandwidth:** Many schools have constrained connectivity, but cloud processing requires only video upload (which can be queued), not real-time on-premises GPU compute.
- **No IT staff:** Public schools do not have IT personnel to maintain GPU hardware, update models, or troubleshoot processing failures.
- **No GPU budget:** A GPU-capable device at each school is a cost that public school budgets cannot absorb.

Edge processing becomes relevant for well-resourced international deployments (e.g., private UK schools with IT infrastructure) or jurisdictions that legally prohibit cloud video processing. It should be positioned as a future deployment option, not a near-term architecture requirement. **Phase 3+.**

The ephemeral nature of Layer 0 remains the key regulatory advantage — whether processing happens in the cloud or at the edge, the goal is the same: extract metrics and minimise the retention of raw biometric video.

---

### Layer 1: Anonymised Core Data Layer

**Purpose:** Store all fitness performance data using internal UUIDs only. This is the jurisdiction-agnostic heart of the system.

#### What Lives Here

| Data | Example | Notes |
|------|---------|-------|
| Internal UUID | `a3f7c2d1-8e4b-4a9f-b6c3-2d1e0f9a8b7c` | System-generated, no external meaning |
| Test type | `beep_test`, `sit_and_reach`, `push_ups` | Enumerated |
| Performance metrics | `{ "laps": 8, "level": 4, "shuttle": 6 }` | Structured per test type |
| Derived scores | `{ "vo2_max_estimate": 38.2 }` | Calculated from metrics |
| Session ID | UUID linking to session metadata | Groups tests done together |
| Session metadata | Date, time, test conditions, school UUID | School identified by UUID, not name |
| Group UUID | UUID for the cohort/class | No class name, grade, or other identifying metadata |
| Assessor UUID | UUID of the person administering the test | Assessor identity in Layer 2 |
| Timestamps | ISO 8601 | When the test was performed |
| Device/camera metadata | Camera ID, firmware version, processing model version | For reproducibility |

#### What Does NOT Live Here

| Data | Where It Lives Instead |
|------|----------------------|
| Student name | Layer 2 (Identity Module) |
| National ID / learner number | Layer 2 (Identity Module) |
| School name / address | Layer 2 (Identity Module) |
| Date of birth | Layer 2 (Identity Module) — see note below |
| Gender | Layer 2 (Identity Module) — see note below |
| Grade / year group | Layer 2 (Identity Module) |
| Parent/guardian contact | Layer 2 (Identity Module) |
| Consent records | Layer 3 (Consent Module) |
| Photos / thumbnails | Not stored at all, or Layer 0 ephemeral only |

**Note on date of birth and gender:** These are needed for fitness score interpretation (normative tables are age- and gender-stratified). Two options:

- **Option A (Recommended):** Store only age-band and gender-category in Layer 1 (e.g., `age_band: "12-13"`, `gender_category: "M"`). These are less identifying than exact date of birth and specific gender.
- **Option B:** Store exact DOB and gender in Layer 1 for precision. This increases re-identification risk, especially for small groups. If this path is taken, these fields must be considered quasi-identifiers for k-anonymity analysis.

#### Ensuring Non-Re-Identifiability

The question: can Layer 1 data alone re-identify a student?

**Risks:**
- **Small schools/classes:** If a school has 15 students and only one 13-year-old boy, his beep test score in Layer 1 combined with public knowledge of the school could re-identify him.
- **Unique performance:** An exceptional score (e.g., Level 14 on the beep test) at a specific school on a specific date could be identifying if the school is known.
- **Temporal patterns:** Test dates combined with school schedules could narrow identification.

**Mitigations:**
- **Do not store school-identifying information in Layer 1.** The school UUID in Layer 1 maps to a school identity in Layer 2. Without Layer 2 access, you cannot determine which school the data belongs to.
- **Generalise timestamps.** Store date only, not precise time, unless precision is required for the test.
- **Use age bands, not exact DOB.**
- **k-anonymity analysis** at the reporting layer (Layer 4) — see below.
- **Access controls** on Layer 1 should be strict even though it contains no PII. The combination of Layer 1 data with external knowledge could enable re-identification; this is a structural risk of any pseudonymised dataset.

#### k-Anonymity Considerations

k-anonymity requires that every combination of quasi-identifiers in the dataset matches at least k individuals. For Layer 1:

Quasi-identifiers in Layer 1: school UUID + age band + gender category + test date

- A class of 30 with roughly equal gender split and multiple age bands might have groups as small as 3-5.
- A small rural school (50 students total) could have age/gender groups of 1-2.

**Structural mitigation:** Layer 1 does not contain school names or locations, so the school UUID is meaningless to an attacker without Layer 2 access. k-anonymity is most critical at Layer 4 (reporting), where data is combined with school identity for output.

---

### Layer 2: Identity Module (Pluggable)

**Purpose:** Map internal UUIDs to real-world identities. This is the only place PII exists. Each jurisdiction gets its own module configuration.

#### Architecture

```
┌──────────────────────────────────────┐
│        IDENTITY MODULE (per jurisdiction)       │
│                                      │
│  ┌──────────┐    ┌────────────────┐  │
│  │ UUID     │    │ Identity       │  │
│  │ Mapping  │◄──►│ Fields         │  │
│  │ Table    │    │ (configurable) │  │
│  └──────────┘    └────────────────┘  │
│                                      │
│  ┌──────────────────────────────┐    │
│  │ Encryption Boundary          │    │
│  │ (separate keys from Layer 1) │    │
│  └──────────────────────────────┘    │
│                                      │
│  ┌──────────────────────────────┐    │
│  │ Access Control Layer         │    │
│  │ (separate from Layer 1)      │    │
│  └──────────────────────────────┘    │
└──────────────────────────────────────┘
```

#### The Mapping Table

The simplest and most critical piece: a table that maps internal UUIDs to external identifiers.

```
internal_uuid (PK)  →  external_id_type  →  external_id_value (encrypted)
─────────────────────────────────────────────────────────────────────────
a3f7c2d1-...        │  LURITS             │  [encrypted: 800123456789]
a3f7c2d1-...        │  SCHOOL_NUMBER      │  [encrypted: GRD7-042]
b8e2f1a9-...        │  UPN                │  [encrypted: H801200001001]
```

A student can have multiple external identifiers (one row per identifier type). The mapping table supports:
- One-to-many: one internal UUID maps to multiple external IDs
- Configurable ID types per jurisdiction
- All external ID values encrypted at rest with jurisdiction-specific keys
- The mapping table lives in a separate database/schema from Layer 1

#### Additional PII Fields

Beyond the mapping table, the identity module stores:

| Field | Description | Encrypted |
|-------|-------------|-----------|
| `student_name` | Full name or name components | Yes |
| `date_of_birth` | Exact DOB (Layer 1 stores only age band) | Yes |
| `gender` | As reported, may include options beyond M/F | Yes |
| `grade_or_year` | Grade 7, Year 8, etc. | Yes |
| `school_name` | Human-readable school name | Yes |
| `school_address` | Physical address | Yes |
| `parent_guardian_name` | Contact person | Yes |
| `parent_guardian_contact` | Email, phone | Yes |
| `additional_fields` | JSON — jurisdiction-specific (see Section 3) | Yes |

#### Interface Between Layer 1 and Layer 2

**Critical design constraint:** Layer 1 must never call Layer 2. The data flow is unidirectional for queries:

```
Layer 2 can read Layer 1 (to associate results with identities)
Layer 1 CANNOT read Layer 2 (the core system never sees PII)
```

In practice, this means:

- **When a test is performed:** The identity module assigns (or retrieves) an internal UUID for the student, passes the UUID to the core system, and the core records metrics against that UUID. The core never knows the student's name.

- **When results are reported:** The reporting layer (Layer 4) or the identity module queries Layer 1 for results by UUID, then enriches them with identity information from Layer 2 before presenting to the end user (teacher, parent, administrator).

- **API design:** The core API accepts and returns UUIDs only. A separate identity-aware API layer wraps the core API and performs enrichment. See Section 6 for details.

```
Teacher requests:  "Show me Thabo Mokoena's beep test results"
                         │
                         ▼
              ┌─────────────────────┐
              │ Identity-Aware API  │  Looks up "Thabo Mokoena" → UUID
              │ (Layer 2 access)    │  in the identity module
              └──────────┬──────────┘
                         │ Requests results for UUID
                         ▼
              ┌─────────────────────┐
              │ Core API            │  Returns metrics for UUID
              │ (Layer 1 access)    │  No PII in request or response
              └──────────┬──────────┘
                         │
                         ▼
              Identity-Aware API enriches with name, returns to teacher
```

#### Bib Assignment: A Boundary-Crossing Concern

The unidirectional data flow rule (Layer 1 cannot read Layer 2) creates a tension with bib assignment. In the domain model design (see [01-domain-model.md](../architecture/01-domain-model.md)), the `BibAssignment` table maps `session_id` + `bib_number` + `student_id`, and the pipeline will use this mapping during result ingestion to resolve OCR-detected bib numbers to student UUIDs.

This mapping must be available to the pipeline processing flow, which operates at the Layer 1 level. The resolution:

- **Bib-to-UUID mapping lives in Layer 1.** The `BibAssignment` record contains only `session_id`, `bib_number`, and an internal `student_uuid`. None of these are PII — the UUID is an opaque internal identifier with no external meaning. This allows the pipeline result ingestion process to resolve bibs to UUIDs without crossing into Layer 2.

- **Bib-to-name mapping is a Layer 2 concern.** When a teacher views the bib assignment screen ("Bib 7 = Thabo Mokoena"), the identity-aware API (Tier 2) enriches the Layer 1 bib-to-UUID mapping with student names from Layer 2. The teacher sees names; the core system sees UUIDs.

- **Bib assignment creation crosses layers.** When a teacher assigns bibs, the Tier 2 API resolves the student name to a UUID (Layer 2 lookup), then writes the bib-to-UUID mapping to Layer 1. This is an acceptable write-direction crossing — Layer 2 writes to Layer 1 (which is permitted), not Layer 1 reading from Layer 2.

This pattern preserves the unidirectional data flow while keeping bib resolution functional during pipeline processing.

#### Identity Module Interface (**MVP**)

The identity module exposes a minimal interface that is consistent across jurisdictions. SA implementation resolves LURITS numbers. UK implementation resolves UPNs. The interface is the same.

```python
class IdentityModule(Protocol):
    def resolve_student(self, internal_id: UUID) -> StudentIdentity | None: ...
    def create_mapping(self, internal_id: UUID, external_id: str, id_type: str) -> None: ...
    def delete_mapping(self, internal_id: UUID) -> None: ...
    def search_by_external_id(self, external_id: str, id_type: str) -> UUID | None: ...
```

#### Separate Storage, Separate Controls

Layer 2 must be physically or logically separated from Layer 1:

| Separation Aspect | Requirement |
|-------------------|-------------|
| Database | Separate database or schema with separate credentials |
| Encryption keys | Different key hierarchy from Layer 1 |
| Access controls | Separate RBAC policies; most system components have no Layer 2 access |
| Backups | Separate backup schedule and storage |
| Audit logging | All reads and writes logged independently |
| Retention | Independent retention policy (may differ from Layer 1) |
| Deletion | Deleting a student's Layer 2 record does not affect Layer 1 |

**Deletion semantics:** When a student's identity is deleted (consent withdrawal, right to erasure), the Layer 2 record is destroyed. The Layer 1 data remains as orphaned anonymous records — they are genuinely anonymous at that point, as no mapping exists. This preserves aggregate statistics while honoring the right to be forgotten.

#### Relationship to ZITADEL and OpenFGA

The existing architecture uses ZITADEL for authentication and OpenFGA for authorization. These systems interact with the layered model as follows:

- **ZITADEL handles staff identity (Layer 2 data).** Teacher/staff accounts — email, name, organization membership — are managed by ZITADEL. This is PII and sits within the Layer 2 boundary. ZITADEL continues to serve as the OIDC provider for all user (staff) authentication. The Layer 2 identity module does not replace ZITADEL for staff; it complements ZITADEL by handling student identity mapping, which ZITADEL does not cover.

- **Students are NOT ZITADEL users.** Students are domain entities in the application database, not authenticated accounts. They have no ZITADEL user record. The Layer 2 identity module owns the student-to-PII mapping (UUID to name, DOB, external IDs). This is a separate concern from ZITADEL's user management.

- **OpenFGA enforces access control across both layers.** OpenFGA's relationship-based authorization model (see [04-authorization.md](../architecture/04-authorization.md)) determines who can see whose results. The permission graph (user -> school -> class -> student -> result) spans both Layer 1 (results, sessions) and Layer 2 (student identity). OpenFGA does not store PII — it stores relationships between UUIDs. It continues to operate exactly as designed, enforcing access control regardless of which layer the data resides in.

- **Summary:** ZITADEL stays for user (staff) authentication. The Layer 2 identity module handles student identity mapping. OpenFGA continues to enforce access control across both layers. No existing system is replaced — the layered model adds structure to where data lives, not to how authentication or authorization work.

---

### Layer 3: Consent & Compliance Module (Pluggable)

**Purpose:** Record, manage, and enforce consent and compliance requirements. Like Layer 2, this is jurisdiction-specific.

#### Consent Data Model

```
consent_record:
  consent_id:         UUID
  student_uuid:       UUID (internal, links to Layer 1/2)
  consenting_party:   encrypted (parent name, guardian name)
  consenting_party_role: PARENT | LEGAL_GUARDIAN | STUDENT (if of age)
  consent_type:       VIDEO_CAPTURE | METRIC_PROCESSING | IDENTITY_STORAGE |
                      DATA_SHARING | REPORTING | MODEL_TRAINING
  consent_status:     GRANTED | WITHDRAWN | EXPIRED
  granted_at:         timestamp
  withdrawn_at:       timestamp (nullable)
  expires_at:         timestamp (nullable)
  consent_method:     DIGITAL_FORM | PAPER_FORM | VERBAL_RECORDED
  consent_evidence:   reference to stored consent form / recording
  jurisdiction:       SA | GB | US_CA | US_NY | ...
  consent_version:    version of the consent form used
  ip_address:         for digital consent (encrypted)
  metadata:           JSON (jurisdiction-specific fields)
```

#### Consent Types (Granular)

A key design decision: consent should be granular, not all-or-nothing. A parent should be able to consent to some processing and not others.

| Consent Type | What It Covers | Can Be Separated? |
|--------------|----------------|-------------------|
| `VIDEO_CAPTURE` | Recording the student on camera | Yes |
| `METRIC_PROCESSING` | Extracting fitness metrics from video | Yes (but requires VIDEO_CAPTURE) |
| `IDENTITY_STORAGE` | Storing student identity in Layer 2 | Yes |
| `DATA_SHARING` | Sharing data with third parties (ministry, researchers) | Yes |
| `REPORTING` | Including student in school/class reports | Yes |
| `MODEL_TRAINING` | Using anonymised/blurred video for ML model improvement | Yes |
| `LONG_TERM_RETENTION` | Retaining data beyond the default period | Yes |

**Minimum viable consent:** `VIDEO_CAPTURE` + `METRIC_PROCESSING`. Without these, the student cannot participate. All others are optional and additive.

**Paper consent alternative (**MVP** — SA deployment):** A paper consent alternative is required. Paper consent forms are digitised by the school administrator via the admin interface (manual entry of consent record with an upload of the signed form as an attachment). The consent record is timestamped and marked as `source: paper`.

#### Consent Withdrawal Handling

When consent is withdrawn, the system must execute a cascade of actions:

```
Consent Withdrawn for VIDEO_CAPTURE:
  → Delete any retained video for this student (Layer 0)
  → Withdraw all dependent consents (METRIC_PROCESSING, MODEL_TRAINING)
  → Flag student for exclusion from future captures

Consent Withdrawn for IDENTITY_STORAGE:
  → Delete Layer 2 record for this student
  → Layer 1 data becomes orphaned (truly anonymous)
  → Notify school admin that student results are no longer linked

Consent Withdrawn for ALL:
  → Execute all of the above
  → Delete Layer 1 data for this student's UUID
  → Delete Layer 3 consent records (after retaining for audit per jurisdiction)
  → Generate deletion confirmation certificate
```

#### Data Subject Access Requests (DSARs)

When a parent or student (if of age) requests access to their data, the system must:

1. Authenticate the requester (verify parent/guardian relationship)
2. Query Layer 2 for the student's UUID
3. Query Layer 1 for all data associated with that UUID
4. Query Layer 0 for any retained video
5. Query Layer 3 for all consent records
6. Compile a human-readable export
7. Deliver within the jurisdiction's required timeframe (e.g., 30 days under POPIA, 30 days under UK GDPR)

**The DSAR handler must have read access to all layers.** This is one of the few cross-layer access patterns, and it should be implemented as a privileged, audited process — not a general API capability.

#### Audit Trail

Every consent event and compliance action must be logged:

```
audit_log:
  event_id:      UUID
  timestamp:     ISO 8601
  actor:         who performed the action (system, admin, parent)
  action:        CONSENT_GRANTED | CONSENT_WITHDRAWN | DSAR_RECEIVED |
                 DSAR_FULFILLED | DATA_DELETED | BREACH_DETECTED | ...
  target_uuid:   student UUID affected
  details:       JSON (action-specific metadata)
  jurisdiction:  which module handled this
```

Audit logs must be append-only and tamper-evident. Retention period for audit logs must meet the longest applicable jurisdiction requirement (which may be longer than data retention).

---

### Layer 4: Reporting & Analytics Layer

**Purpose:** Produce aggregated insights for schools, districts, and national bodies while preserving privacy through k-anonymity guarantees.

#### Aggregation Hierarchy

```
Individual (Layer 1 + Layer 2) → requires identity module access
    ▼
Class / Group (Layer 1 + Layer 2) → requires identity module for grouping
    ▼
School (Layer 1 + school UUID mapping) → school identity from Layer 2
    ▼
District / Region (Layer 1 aggregated) → may not need Layer 2 at all
    ▼
National (Layer 1 aggregated) → definitely no Layer 2 needed
```

#### k-Anonymity Requirements

At each reporting level, the minimum group size before results are reported:

| Reporting Level | Minimum Group Size | Rationale |
|----------------|-------------------|-----------|
| Individual | 1 (requires authenticated, authorised user) | Parent viewing their child's results |
| Class / Group | 5 | Below 5, individual results may be inferable |
| School | 10 | Some small schools may have very small cohorts |
| District | 20 | Standard statistical practice |
| National | No minimum | Already sufficiently aggregated |

**Suppression rule:** If a group falls below the minimum size, the report either omits the group or merges it with adjacent groups (e.g., combine Grade 7 and Grade 8 at a small school).

#### How Layer 4 Accesses Data

Two paths, depending on the report type:

**Path A: Anonymous aggregate reports (district, national)**
- Query Layer 1 directly
- Aggregate by test type, age band, gender category
- No Layer 2 access needed
- No PII in the query or the result
- These reports can flow freely across borders (see Section 5)

**Path B: Identified reports (individual, class, school)**
- Query Layer 2 to determine which UUIDs belong to the target group
- Query Layer 1 for those UUIDs' metrics
- Enrich with identity data from Layer 2
- Access controlled by role: teacher sees their class, principal sees their school, parent sees their child
- These reports contain PII and are subject to jurisdiction-specific rules

```
District Report (Path A):
  SELECT age_band, gender_category, AVG(beep_test_level)
  FROM layer1.test_results
  WHERE school_uuid IN (SELECT uuid FROM layer1.schools WHERE district_uuid = ?)
  GROUP BY age_band, gender_category
  HAVING COUNT(*) >= 20

  → No PII touched. Layer 2 not involved.

Class Report (Path B):
  1. Layer 2: Get UUIDs for students in Class 7A at Springfield Primary
  2. Layer 1: Get test results for those UUIDs
  3. Layer 2: Get student names for those UUIDs
  4. Combine and present: "Thabo - Level 8, Aisha - Level 6, ..."
```

---

## 3. Country Module Design

Each country or jurisdiction requires a module that configures Layers 2 and 3 for local requirements. The module is a configuration bundle plus any jurisdiction-specific code (e.g., for identity verification APIs).

### MVP: Jurisdiction Config Table

For MVP (SA launch) and Phase 2 (UK expansion), jurisdiction configuration is stored in a database table rather than a YAML module framework. The YAML configs below remain as documentation of what each jurisdiction needs, but the runtime implementation is this table.

```sql
CREATE TABLE jurisdiction_config (
    id UUID PRIMARY KEY,
    code VARCHAR(10) NOT NULL UNIQUE,  -- 'ZA', 'GB', 'EU'
    name VARCHAR(100) NOT NULL,
    consent_age_threshold INTEGER NOT NULL DEFAULT 18,
    default_privacy_level VARCHAR(20) NOT NULL DEFAULT 'high',
    video_hot_storage_days INTEGER NOT NULL DEFAULT 90,  -- days in hot storage (GCS Standard) before transition to cold storage (GCS Nearline/Coldline)
    video_max_retention_days INTEGER DEFAULT NULL,  -- NULL = retain for duration of linked metrics; set to a value to enforce jurisdiction-specific maximum
    metrics_retention_years INTEGER NOT NULL DEFAULT 7,
    profiling_enabled_by_default BOOLEAN NOT NULL DEFAULT false,
    result_sharing_default VARCHAR(20) NOT NULL DEFAULT 'private',
    identity_id_types JSONB NOT NULL,  -- ['LURITS'] for ZA, ['UPN'] for GB
    requires_dpia BOOLEAN NOT NULL DEFAULT false,
    requires_explicit_consent BOOLEAN NOT NULL DEFAULT false,  -- Article 9
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Feature toggles (**MVP**):** Feature toggles are stored in the `jurisdiction_config` table and applied at the application layer. The application reads the active jurisdiction's config at request time and gates features accordingly (profiling, sharing, privacy defaults). For MVP, this is simple conditional logic — no feature flag service needed.

### Module Configuration Schema (**Phase 3+**)

The full YAML module configuration schema below is the target for when additional jurisdictions are added beyond SA and UK. For MVP and Phase 2, the `jurisdiction_config` table above is sufficient.

```yaml
jurisdiction_module:
  jurisdiction_code: "ZA"       # ISO 3166-1 alpha-2
  jurisdiction_name: "South Africa"
  effective_date: "2026-06-01"

  identity:
    accepted_id_types:
      - type: "LURITS"
        required: false
        validation_pattern: "^[0-9]{13}$"
        sensitivity: "medium"
      - type: "SA_ID"
        required: false
        validation_pattern: "^[0-9]{13}$"
        sensitivity: "high"
        requires_prior_authorisation: true
      - type: "SCHOOL_NUMBER"
        required: false
        validation_pattern: null  # school-defined format
        sensitivity: "low"

    required_fields:
      - student_name
      - date_of_birth
      - grade
    optional_fields:
      - gender
      - parent_guardian_name
      - parent_guardian_contact

  consent:
    age_of_data_consent: 18       # POPIA: all under 18 are children
    parental_consent_required: true
    parental_verification_method: "SELF_DECLARATION"  # or ID_VERIFICATION, DIGITAL_SIGNATURE
    consent_form_template: "za_consent_v1"
    granular_consent_types:
      - VIDEO_CAPTURE
      - METRIC_PROCESSING
      - IDENTITY_STORAGE
      - DATA_SHARING
      - REPORTING
      - LONG_TERM_RETENTION
      - MODEL_TRAINING
    minimum_consent_for_participation:
      - VIDEO_CAPTURE
      - METRIC_PROCESSING
    consent_withdrawal_period_days: 0  # immediate
    consent_renewal_required: true
    consent_renewal_period_months: 12

  data_residency:
    storage_region: "africa-south1"        # GCP region (Johannesburg)
    data_must_stay_in_country: true       # POPIA Section 72
    cross_border_transfer_allowed: true   # with adequate protections
    adequate_jurisdictions: ["EU", "GB", "CA"]  # recognised adequate
    transfer_mechanism: "SECTION_72_EXEMPTION"  # or SCC, BCR

  retention:
    video_retention_mode: "RETAIN_WITH_METRICS"
    video_hot_storage_days: 90          # Hot storage (GCS Standard), then cold storage (GCS Nearline/Coldline)
    video_max_retention_days: null      # null = retain for duration of linked metrics; set to a value for jurisdiction-specific maximum
    metrics_retention_years: 7          # aligned with school record retention
    identity_retention_years: 7
    consent_audit_retention_years: 10   # longer for compliance evidence
    anonymised_data_retention: "INDEFINITE"

  breach_notification:
    regulator_notification_required: true
    regulator_name: "Information Regulator"
    notification_deadline: "AS_SOON_AS_REASONABLY_POSSIBLE"
    notification_method: "E_PORTAL"       # Regulator's mandatory e-Portal
    data_subject_notification_required: true
    data_subject_notification_deadline: "AS_SOON_AS_REASONABLY_POSSIBLE"

  data_subject_rights:
    right_to_access: true
    right_to_rectification: true
    right_to_erasure: true
    right_to_data_portability: false     # not explicitly in POPIA
    access_request_deadline_days: 30
    erasure_request_deadline_days: 30

  video_handling:
    capture_allowed: true
    face_blurring_before_storage: true   # if video retained
    body_anonymisation_before_storage: false
    on_premises_processing_required: false
    cloud_processing_allowed: true
    cloud_provider_requirements:
      - "Data processing agreement required"
      - "Provider must have adequate security measures per POPIA S19"
```

### Comparative Module Configurations

#### South Africa (ZA) — POPIA

| Aspect | Configuration |
|--------|---------------|
| Primary legislation | POPIA (Act 4 of 2013) |
| Age of consent for data | 18 (no graduated consent) |
| Parental consent | Required for all under-18s, must be from "competent person" |
| Recommended ID type | LURITS number (see [POPIA research doc](./popia-student-identity.md)) |
| SA ID number | Optional, requires legal review on prior authorisation (POPIA S57-58) |
| Data residency | POPIA S72 restricts cross-border transfers; SA or "adequate" jurisdictions |
| Video retention | Retain with linked metrics: 90 days hot storage, then cold storage (GCS Nearline/Coldline), deleted when linked metrics are deleted or on consent withdrawal. No fixed maximum. Immediate delete available for privacy-sensitive deployments. Encrypted and access-controlled throughout. |
| Breach notification | Mandatory, to Information Regulator via e-Portal and to data subjects |
| Right to erasure | Yes |
| Special considerations | Information Regulator is aggressive on children's data; R5M fine precedent against DBE |

#### United Kingdom (GB) — UK GDPR + Data Protection Act 2018

| Aspect | Configuration |
|--------|---------------|
| Primary legislation | UK GDPR + Data Protection Act 2018 |
| Age of consent for data | 13 (UK sets the GDPR floor at 13) |
| Parental consent | Required for under-13s; 13-17 can consent in some contexts |
| Recommended ID type | UPN (Unique Pupil Number) — assigned by DfE |
| Data residency | Post-Brexit: UK adequacy decisions determine transfer destinations; EU has granted UK adequacy (currently valid, renewed periodically) |
| Video retention | DPIA required; retention must be justified and proportionate |
| Breach notification | 72 hours to ICO; data subjects notified if high risk |
| Right to erasure | Yes (Art 17) |
| Special considerations | ICO guidance on children's data is detailed (Age Appropriate Design Code / Children's Code); DPIA mandatory for systematic monitoring of children; DfE data sharing frameworks exist for approved EdTech providers |

Key UK differences from SA:
- The UPN is a well-established, lower-sensitivity identifier (similar to LURITS)
- The 13-year consent threshold changes the consent architecture significantly — a single school may have some students who can consent themselves and others who need parental consent
- The ICO's Children's Code imposes specific obligations on services "likely to be accessed by children"
- Data Protection Impact Assessments (DPIAs) are mandatory for processing children's data at scale

#### United States — Deferred

US module configuration is documented for reference in [Appendix A](#appendix-a-us-jurisdiction-module) but US deployment is deferred. The key architectural differences (FERPA contract-based consent model, BIPA biometric restrictions) are noted in [data-classification-and-regulation.md](./data-classification-and-regulation.md).

### Module Comparison Summary (SA **MVP** / UK **Phase 2**)

| Feature | South Africa (**MVP**) | United Kingdom (**Phase 2**) |
|---------|-------------|----------------|
| Age for self-consent | 18 | 13 |
| Parent consent model | Always required | Under-13 only |
| National student ID | LURITS | UPN |
| Data residency | SA or adequate | UK or adequate |
| Breach notification | Regulator + subjects | 72h to ICO |
| Biometric-specific law | POPIA S32 (biometric = special) | UK GDPR Art 9 |
| DPA/DPIA required | Not explicitly | Yes, mandatory for children at scale |
| Right to erasure | Yes | Yes |

US comparison is in [Appendix A](#appendix-a-us-jurisdiction-module).

---

## 4. Video Data Strategy

Video is the highest-risk data type in the Vigour system. It contains biometric information (face, body shape, gait), can identify individuals, and is subject to the strictest regulatory treatment in every jurisdiction.

### 4.1 Processing Modes

#### Mode 1: Ephemeral Processing (Recommended Default)

```
Camera → Video Stream → CV Pipeline → Metrics → Layer 1
                              │
                              └→ Video Deleted (immediately or within hours)
```

**Advantages:**
- Strongest privacy position — no persistent video storage
- Minimal regulatory burden — most regulations focus on stored data
- Lowest breach risk — you cannot leak what you do not have
- Simplest to explain to parents and regulators

**Disadvantages:**
- No ability to re-process if metrics are questioned
- No audit trail of the source material
- No data for model retraining (unless separately consented and handled)
- Disputes about scores cannot be verified against source footage

**Suitability:** This can become the default for mature deployments where the CV pipeline is reliable and re-processing is rarely needed. It is not appropriate as the default while the pipeline is still being refined — see Mode 2 below.

#### Mode 2: Retain with Linked Metrics

```
Camera → Video Stream → CV Pipeline → Metrics → Layer 1
                              │
                              └→ Encrypted Video → 90 days hot → Cold storage → Deleted with metrics
```

**Advantages:**
- Video is the evidence chain for the metrics — dispute resolution, re-processing, and quality assurance are always possible
- Pipeline improvements can be applied to original video
- Audit trail for the full lifecycle of the metrics
- Privacy risk reduces over time (cold storage, restricted access, audit logging)
- On consent withdrawal, identity unlinking makes the video effectively anonymous
- Configurable per jurisdiction — `video_max_retention_days` can enforce a maximum where required

**Disadvantages:**
- Retained video is a breach target (mitigated by cold storage, access controls, and audit logging)
- Requires encrypted storage with access controls
- Retention period must be justified per jurisdiction

**Suitability:** This is the default for all deployments. The video is the source of truth for the metrics — deleting video while retaining metrics removes the evidence chain. If a parent disputes a score, the source video is needed. Pipeline improvements require re-processing original video. Quality assurance requires comparing pipeline output against source. The 90-day hot-to-cold transition balances active access needs with storage cost and privacy posture. Jurisdictions that impose maximum retention periods can configure `video_max_retention_days` to enforce a cap.

#### Mode 3: Anonymised Archival

```
Camera → Video Stream → CV Pipeline → Metrics → Layer 1
                              │
                              ├→ Anonymisation Pipeline → Anonymised Video → Archive
                              │     (face blur, body outline, background removal)
                              │
                              └→ Original Video → Deleted
```

**Advantages:**
- Provides data for model training and quality assurance
- Reduced (but not zero) regulatory burden
- Useful for research and development

**Disadvantages:**
- Anonymisation is not guaranteed to be irreversible (gait, body shape, clothing can still identify)
- Adds processing complexity and cost
- Regulatory treatment of "anonymised" video varies by jurisdiction
- The EU/UK Article 29 Working Party has noted that anonymisation is a processing operation on personal data, and thus requires a lawful basis

#### 4.2 Face Blurring — Is It Sufficient?

Face blurring is necessary but may not be sufficient for full anonymisation:

**What face blurring addresses:**
- Direct facial identification
- Facial recognition system matching

**What face blurring does NOT address:**
- Body shape and build (identifying for people who know the student)
- Clothing (school uniforms reduce this, but accessories, shoes, etc. remain)
- Gait analysis (movement patterns are biometric identifiers)
- Contextual identification (if you know only 15 students were in the gym at that time)
- Hair (visible above/behind blur region)
- Skin tone (partially visible)

**Recommendation:** For video that must be retained, face blurring should be combined with:
- Body outline replacement (replace the full body with a skeleton or silhouette)
- Background removal or blurring (removes environmental context)
- Metadata stripping (GPS coordinates, device serial number, device model stripped at ingestion — traceability comes from the session record, not embedded file metadata)

Even with all of these, the video may not be legally "anonymous" in all jurisdictions. It should be treated as pseudonymised rather than anonymous, with appropriate controls.

### 4.3 Edge vs Cloud Processing — Regulatory Implications

| Scenario | Regulatory Position |
|----------|-------------------|
| Edge processing, video never leaves school | Strongest. No data transfer issues. School controls physical security. Vigour may argue it never "receives" the video — only the extracted metrics. |
| Edge processing, metrics sent to cloud | Strong. Only anonymised metrics leave the school. Metrics are not biometric data. Standard data processing agreement covers the cloud relationship. |
| Cloud processing, video uploaded to cloud in-country | Moderate. Video is transferred to Vigour's infrastructure. Data processing agreement required. Cloud provider must meet jurisdiction's security requirements. No cross-border issue if cloud region is in-country. |
| Cloud processing, video uploaded to cloud cross-border | Weakest. All cross-border data transfer rules apply to biometric data. May be prohibited in some jurisdictions. Requires explicit legal basis for transfer. |

**Recommendation:** For the initial product, prioritise in-country cloud processing. Edge processing is not feasible for the SA MVP (see Layer 0 discussion above). Cross-border video transfer should be avoided unless and until a specific jurisdiction's legal analysis confirms it is permissible. The existing infrastructure architecture hosts application data in `africa-south1` (Johannesburg) for POPIA compliance, with GPU workloads in the designated European GPU processing region (see [Infrastructure Architecture](../architecture/07-infrastructure.md)) — the video processed by the GPU pipeline does not contain PII linkable to students without the application database.

### 4.4 Ephemeral Cross-Region GPU Processing

The practical reality for the SA MVP is that GPU VMs are not available in `africa-south1`. The solution is an ephemeral cross-region processing pattern where video is permanently stored in-region but transiently processed on a GPU VM in the designated European GPU processing region (see [Infrastructure Architecture](../architecture/07-infrastructure.md)).

#### The Pattern

```
School → Video Upload → GCS (africa-south1) → GPU VM (EU GPU region) → Metrics → GCS (africa-south1)
                         [permanent storage]    [ephemeral only]                  [results stored here]
                                                [auto-purge after]
                                                [job completion]
```

**Key principle:** Video permanently resides in-region. It never permanently leaves the jurisdiction. The GPU VM in the processing region pulls video from GCS, processes it in memory or temporary storage, extracts metrics, and the local copy is purged on job completion. No persistent storage of video exists on the GPU VM.

#### Why This Satisfies Data Residency Requirements

This pattern draws a defensible distinction between persistent cross-border transfer (which regulations restrict) and transient cross-border processing (which is a weaker form of transfer):

1. **POPIA Section 72** restricts transfers of personal information to third parties in foreign jurisdictions, but transient processing with immediate deletion — where no data is stored at rest abroad — is a weaker form of transfer than persistent storage. The data controller (Vigour) retains control throughout, and the foreign processing is performed by the same data controller's infrastructure, not a third party.

2. **GDPR** similarly distinguishes between data at rest and data in transit/processing. Transient processing on infrastructure controlled by the data processor, with contractual guarantees of non-persistence, is a recognised pattern.

3. **GCP's data processing agreement** can be structured to specify that the GPU region only processes transiently and never persists video data. GCP Compute Engine ephemeral SSDs are wiped on VM stop, providing a hardware-level guarantee.

4. **Metrics flowing back to the local region** are numeric values (seconds, centimetres, counts) detached from identity, making them low-sensitivity data in transit. They carry no biometric content.

#### Why This Is Better Than Mode A (Immediate Delete Everywhere)

Mode A (Section 4.1) deletes video immediately after processing, which eliminates all cross-border concerns but sacrifices operational capability. The ephemeral cross-region pattern is superior because:

- **Video is retained in-region** for re-processing, dispute resolution, and debugging — the pipeline is still maturing and re-processing with improved models requires the original footage
- **Video never permanently leaves the region** — the cross-border exposure is limited to the transient processing window
- **Teachers can still review annotated video** stored in the local GCS bucket
- **The pipeline can re-process with improved models** without requiring schools to re-capture video

This is also the honest, defensible version of the claim in the infrastructure architecture that video is "anonymised" during cross-region processing. The video is not anonymised — it is transiently processed and then purged from the processing region. That is a stronger and more accurate position than claiming anonymisation, which (as Section 4.2 discusses) is difficult to guarantee for video.

#### Technical Implementation Requirements

1. **No persistent video on the GPU VM.** The GPU VM must never write video to persistent disk. Video should be streamed from GCS and processed in memory or on a tmpfs mount. If temporary local storage is required for performance, it must use ephemeral SSDs that are wiped on VM stop.

2. **Ephemeral SSD only.** Any temporary storage attached to the GPU VM must be ephemeral (local SSD), not persistent disk. GCP ephemeral local SSDs are cryptographically erased when the VM stops.

3. **Job completion purge hook.** On job completion (success or failure), a cleanup hook must verify that all temporary storage on the GPU VM is cleared. This should be logged.

4. **Audit trail.** Every cross-region processing job must log: video object processed, source region, processing region, processing start time, processing end time, purge confirmation time. This creates a verifiable record that video was processed in region X at time Y and purged at time Z.

5. **GCP data processing agreement.** The DPA with GCP must explicitly cover this pattern: video data is processed transiently in the GPU region with no persistent storage, and ephemeral storage is cryptographically erased on VM termination.

6. **Network-level controls.** The GPU VM should have no egress path for video data other than back to the originating GCS bucket (for annotated video) and to the application database (for metrics). Firewall rules should enforce this.

#### Per-Jurisdiction Flexibility

This pattern is not mandatory for all jurisdictions. The architecture supports three deployment modes for GPU processing:

| Mode | When to Use | Example |
|------|-------------|---------|
| **Ephemeral cross-region** | GPU VMs unavailable in the data region; jurisdiction permits transient processing abroad with contractual safeguards | SA: data in `africa-south1`, GPU in the designated European GPU processing region (see [Infrastructure Architecture](../architecture/07-infrastructure.md)) |
| **In-region GPU** | GPU VMs available in the data region, or jurisdiction prohibits even transient cross-border processing | UK: data and GPU both in a European region |
| **Edge processing** | Jurisdiction requires video to never leave school premises, and school has GPU hardware | Long-term option for well-resourced deployments |

The jurisdiction module (Section 3) should include a `gpu_processing_mode` configuration that selects the appropriate pattern. For jurisdictions that prohibit even transient cross-border processing, in-region GPU processing (when available) or edge processing (long-term) are the fallbacks.

### 4.5 Consent Separation: Video vs Metrics

Can consent for video capture be separated from consent for metric processing? Technically yes, practically nuanced:

**Scenario A: Parent consents to VIDEO_CAPTURE + METRIC_PROCESSING**
- Standard flow. Video captured, processed, metrics stored, video deleted.

**Scenario B: Parent consents to METRIC_PROCESSING but NOT VIDEO_CAPTURE**
- The student cannot be individually filmed. Options:
  - Student is excluded from camera-based testing
  - Student is tested manually (teacher records metrics by hand)
  - Student is in the field of view but the system does not track or extract their metrics (technically challenging)

**Scenario C: Parent consents to VIDEO_CAPTURE but NOT METRIC_PROCESSING**
- Unusual, but possible (parent is fine with filming for group activity but does not want individual performance metrics extracted). The system would need to capture video but filter out this student's data from the pipeline output.

**Recommendation:** For MVP, treat VIDEO_CAPTURE + METRIC_PROCESSING as a bundled minimum consent. Separate consent for LONG_TERM_RETENTION, IDENTITY_STORAGE, and MODEL_TRAINING. Over time, as the system matures, finer-grained separation can be implemented.

---

## 5. Cross-Border Data Flow

### 5.1 The Core Question

If Vigour HQ is in South Africa but processes data for a UK school, data flows across borders in at least one direction. The architecture must handle this.

### 5.2 Data Flow Scenarios

```
Scenario 1: Fully Local
┌──────────────────────────┐
│ UK School                │
│ ┌──────────────────────┐ │
│ │ Edge processing      │ │  Video processed locally
│ └──────────┬───────────┘ │
│            ▼             │
│ ┌──────────────────────┐ │
│ │ UK Cloud (Layer 1-4) │ │  All data stays in UK
│ └──────────────────────┘ │
└──────────────────────────┘
  Nothing crosses a border. Ideal from a regulatory perspective.
```

```
Scenario 2: Local PII, Central Analytics
┌──────────────────────────┐     ┌──────────────────────────┐
│ UK Deployment            │     │ Vigour Central (SA)      │
│ ┌──────────────────────┐ │     │ ┌──────────────────────┐ │
│ │ Layer 2 (PII)        │ │     │ │ Aggregate Analytics  │ │
│ │ Layer 3 (Consent)    │ │     │ │ (no PII)             │ │
│ │ Layer 1 (Core Data)  │ │     │ │ Model training       │ │
│ └──────────┬───────────┘ │     │ │ Product improvement  │ │
│            │             │     │ └──────────▲───────────┘ │
│            │  Anonymised │     │            │             │
│            │  aggregates │     │            │             │
│            └─────────────┼─────┼────────────┘             │
│                          │     │                          │
└──────────────────────────┘     └──────────────────────────┘
  PII stays in UK. Only anonymous aggregates flow to SA.
```

```
Scenario 3: Central Processing
┌──────────────────────────┐     ┌──────────────────────────┐
│ UK School                │     │ Vigour Central (SA)      │
│ ┌──────────────────────┐ │     │ ┌──────────────────────┐ │
│ │ Camera capture       │ │     │ │ All layers           │ │
│ └──────────┬───────────┘ │     │ │ Processing pipeline  │ │
│            │  Video or   │     │ └──────────────────────┘ │
│            │  metrics    │     │                          │
│            └─────────────┼─────┼──►                       │
│                          │     │                          │
└──────────────────────────┘     └──────────────────────────┘
  Video/data crosses from UK to SA. Requires full cross-border compliance.
```

```
Scenario 4: Ephemeral Cross-Region GPU Processing (SA MVP — Primary Pattern)
┌──────────────────────────┐     ┌──────────────────────────┐
│ SA School                │     │ GPU Region (EU)          │
│ ┌──────────────────────┐ │     │ ┌──────────────────────┐ │
│ │ Camera capture       │ │     │ │ GPU VM               │ │
│ └──────────┬───────────┘ │     │ │ - Streams video from │ │
│            │  Video      │     │ │   GCS africa-south1  │ │
│            ▼             │     │ │ - Processes in memory │ │
│ ┌──────────────────────┐ │     │ │ - Extracts metrics   │ │
│ │ GCS (africa-south1)  │◄┼─────┼─│ - Purges local copy  │ │
│ │ [permanent video     │ │     │ │ - Ephemeral SSD only │ │
│ │  + metrics storage]  │─┼─────┼─►                      │ │
│ │ Layer 1-4 in-region  │ │     │ └──────────────────────┘ │
│ └──────────────────────┘ │     │  No persistent storage   │
└──────────────────────────┘     └──────────────────────────┘
  Video permanently resides in africa-south1. GPU VM processes
  transiently and purges on job completion. Metrics flow back
  to africa-south1. See Section 4.4 for full details.
```

### 5.3 Regulatory Mechanisms for Cross-Border Transfer

| Mechanism | What It Is | When to Use |
|-----------|-----------|-------------|
| **Adequacy Decision** | Destination country has been assessed as providing adequate data protection | If SA is adequate in the eyes of the UK (or vice versa). Currently: UK has EU adequacy; SA does not have UK adequacy. |
| **Standard Contractual Clauses (SCCs)** | Pre-approved contractual terms that bind the data importer | When no adequacy decision exists. Vigour HQ and the local entity sign SCCs. |
| **Binding Corporate Rules (BCRs)** | Internal rules approved by a regulator for intra-group transfers | For large organisations with multiple entities. Expensive to obtain. Not practical for Vigour at current scale. |
| **Explicit Consent** | Data subject explicitly consents to the transfer | Possible but fragile — consent can be withdrawn. Not recommended as the primary mechanism. |
| **POPIA Section 72 Exemptions** | Allows transfer if subject consents, contract requires it, or recipient is in adequate jurisdiction | SA-specific. Permits transfer if adequate protections are in place. |

### 5.4 Recommended Approach

**Principle: PII stays local. Only anonymous data flows centrally. Video is permanently stored in-region and only transiently processed cross-region when in-region GPU is unavailable.**

- Layer 2 (Identity) and Layer 3 (Consent) are always deployed in the jurisdiction where the students are
- Layer 1 (Core Data) can be deployed locally or centrally, but if centrally, it must be treated as a cross-border transfer (even though it contains no direct PII, it contains pseudonymised data that is personal data in most frameworks)
- Layer 4 (Reporting) aggregate outputs at the district/national level can flow centrally with minimal regulatory burden, as they are genuinely anonymous if k-anonymity thresholds are met
- Video (Layer 0) is permanently stored in-region. Cross-region GPU processing is permitted only as transient, ephemeral processing with no persistent storage in the processing region (see Section 4.4). This is the primary pattern for the SA MVP, where GPU VMs are unavailable in `africa-south1`.

**Practical deployment model:**

| Layer | Deployment | Cross-Border? |
|-------|-----------|---------------|
| Layer 0 (Video storage) | In-country cloud (GCS in local region) | Never — video permanently resides in-region |
| Layer 0 (GPU processing) | Cross-region GPU VM (ephemeral only) | Transient only — no persistent storage, auto-purged on job completion (see Section 4.4) |
| Layer 1 (Core Data) | In-country cloud | No (preferred) |
| Layer 2 (Identity) | In-country cloud | Never |
| Layer 3 (Consent) | In-country cloud | Never |
| Layer 4 (Aggregates) | In-country + central | Yes, anonymised aggregates only |

**How video moves through the system (SA MVP):** A school uploads video to GCS in `africa-south1`. The video is stored there permanently (subject to the retention mode configured for the jurisdiction — see Section 4.1). When GPU processing is required, a GPU VM in the designated European GPU processing region (see [Infrastructure Architecture](../architecture/07-infrastructure.md)) streams the video from GCS, processes it in memory/tmpfs, extracts metrics, writes annotated video back to GCS in `africa-south1`, and purges all local copies. The GPU VM never writes video to persistent disk. Metrics (numeric values with no biometric content) are written to the application database in `africa-south1`. An audit log records the processing region, timestamps, and purge confirmation.

This is the honest, defensible version of cross-region video handling. The video is not "anonymised" before leaving the region — it is transiently processed and then purged from the processing region. This is a stronger and more accurate regulatory position than claiming anonymisation of video data (see Section 4.2 on why face blurring alone is insufficient).

This model means Vigour operates regional instances rather than a single global instance. See Section 6 for the technical implications.

---

## 6. Technical Implementation Considerations

### 6.1 Database Architecture

**Option A: Separate Databases per Layer** (**Phase 3+**)

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│ Layer 0 DB  │  │ Layer 1 DB  │  │ Layer 2 DB  │  │ Layer 3 DB  │
│ (ephemeral/ │  │ (core data) │  │ (PII)       │  │ (consent)   │
│  temp store)│  │             │  │             │  │             │
│             │  │ Credentials │  │ Credentials │  │ Credentials │
│             │  │ Set A       │  │ Set B       │  │ Set C       │
│             │  │             │  │             │  │             │
│             │  │ Encryption  │  │ Encryption  │  │ Encryption  │
│             │  │ Key Set 1   │  │ Key Set 2   │  │ Key Set 3   │
└─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘
```

**Advantages:** Strongest separation. A breach of one database does not expose others. Different backup, retention, and access policies per database. Easy to deploy Layer 2 and 3 in a different region from Layer 1.

**Disadvantages:** More infrastructure to manage. Cross-database queries are more complex. Higher operational cost.

**Option B: Separate Schemas, Same Database Engine** (**MVP**)

```
┌───────────────────────────────────────────────────┐
│                  Database Engine                   │
│                                                   │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐     │
│  │ Schema:   │  │ Schema:   │  │ Schema:   │     │
│  │ core_data │  │ identity  │  │ consent   │     │
│  │           │  │           │  │           │     │
│  │ Role: app │  │ Role:     │  │ Role:     │     │
│  │           │  │ id_admin  │  │ cmp_admin │     │
│  └───────────┘  └───────────┘  └───────────┘     │
│                                                   │
│  Row-level security + column encryption            │
└───────────────────────────────────────────────────┘
```

**Advantages:** Simpler infrastructure. Still provides logical separation via schemas and roles. Easier to manage.

**Disadvantages:** A database-level breach exposes all schemas. Separation is logical, not physical. Harder to deploy schemas in different regions.

**Recommendation: Progressive hardening.** The layered model is a logical architecture that can be progressively hardened as requirements demand. Physical separation is not required from day one.

- **MVP:** Schema separation within a single Cloud SQL instance (Option B). This aligns with the existing architecture decision (ADR-006: single Cloud SQL instance with schema separation using dedicated PostgreSQL roles and no cross-schema permissions). This provides logical isolation at minimal cost and operational overhead.
- **Phase 2:** Logical separation hardened with separate PostgreSQL roles, row-level audit logging on Layer 2 schemas, and explicit cross-schema access denial enforced at the database level. Still a single Cloud SQL instance.
- **Phase 3+:** Physical separation into separate database instances (Option A) when regulatory requirements demand it (e.g., a jurisdiction requires PII to be in a physically separate data store) or when scaling requirements justify the additional infrastructure cost.

The key insight is that the privacy boundary is enforced by the application architecture (separate API tiers, separate modules, separate credentials per schema) regardless of whether the databases are physically separated. Physical separation adds defence-in-depth but is not a prerequisite for the privacy guarantees.

### 6.2 Key Management

Key management should be implemented progressively, matching the platform's maturity and deployment footprint:

#### Single Cloud KMS Key (**MVP**)

```
Google Cloud KMS
  └── vigour-pii-key (Cloud KMS symmetric key)
        └── Application-level column encryption for PII fields in Layer 2
```

At MVP stage (single jurisdiction, single Cloud SQL instance), a single Cloud KMS key with application-level column encryption for PII fields is sufficient. This protects Layer 2 data (student names, DOB, external IDs) at rest while keeping operational complexity low. Cloud KMS handles key storage, access control, and automatic rotation.

#### Per-Jurisdiction Keys (**Phase 2**)

```
Google Cloud KMS
  ├── vigour-core-key (Layer 1 DEK)
  ├── vigour-za-identity-key (Layer 2 DEK — South Africa)
  ├── vigour-gb-identity-key (Layer 2 DEK — United Kingdom)
  ├── vigour-za-consent-key (Layer 3 DEK — South Africa)
  └── vigour-gb-consent-key (Layer 3 DEK — United Kingdom)
```

When operating in multiple jurisdictions, per-jurisdiction Cloud KMS keys allow independent key rotation, access policies, and — critically — cryptographic data destruction when a jurisdiction module is decommissioned.

#### Full Key Hierarchy with HSM (**Phase 3+**)

```
Master Key (HSM-protected, per deployment region)
  ├── Layer 1 Data Encryption Key (DEK)
  ├── Layer 2 Data Encryption Key (DEK) — jurisdiction-specific
  │     ├── ZA identity DEK
  │     ├── GB identity DEK
  │     └── US identity DEK
  ├── Layer 3 Data Encryption Key (DEK) — jurisdiction-specific
  └── Layer 0 Temporary Encryption Key (if video is retained)
```

At scale with multiple regions and strict regulatory requirements, HSM-backed master keys with a full key hierarchy provide the highest level of key protection. This is aspirational — the cost and complexity of HSM management is justified only when regulatory or enterprise customer requirements demand it.

**Key rotation:** All DEKs should be rotated on a regular schedule (e.g., annually). Cloud KMS supports automatic rotation. HSM-backed master keys should be rotated less frequently.

**Key destruction:** When a jurisdiction module is decommissioned, destroying the jurisdiction-specific DEKs renders all associated Layer 2 and 3 data unrecoverable. This is a feature, not a bug — it provides a cryptographic guarantee of data destruction.

### 6.3 API Design

The API is structured in two tiers:

**Tier 1: Core API (Layer 1 access only)**

```
POST   /api/v1/sessions                    # Create a test session
POST   /api/v1/sessions/{id}/results       # Submit test results for a UUID
GET    /api/v1/sessions/{id}/results       # Get results for a session
GET    /api/v1/results/{uuid}              # Get all results for a student UUID
GET    /api/v1/analytics/aggregate         # Get aggregate statistics

All requests and responses use internal UUIDs only.
No PII in any request or response.
```

**Tier 2: Identity-Aware API (wraps Tier 1, adds Layer 2/3 access)**

```
POST   /api/v1/students                    # Register a student (creates Layer 2 record, returns UUID)
GET    /api/v1/students/{id}/results       # Get results by external ID (resolves to UUID internally)
GET    /api/v1/classes/{id}/report         # Class report with student names
POST   /api/v1/consent                     # Record consent
DELETE /api/v1/students/{id}               # Right to erasure (deletes Layer 2, optionally Layer 1)
POST   /api/v1/dsar                        # Data subject access request

Requests may include PII (student name, external ID).
Responses include PII (enriched with identity data).
This API is jurisdiction-specific and access-controlled.
```

**Key design rule:** The Tier 1 API has no import or dependency on the identity module. It can be deployed and tested independently. The Tier 2 API imports both Tier 1 and the identity module.

**MVP implementation note:** For MVP, the two tiers would be implemented as a single FastAPI application with separate route groups and module boundaries — not two separate deployed services. Two separate Cloud Run services would double deployment cost and operational overhead (two Docker images, two sets of health checks, two scaling configurations, two sets of logs to monitor). The privacy boundary is enforced by Python module boundaries and dependency injection: the core routes import only the core data module, and the identity-aware routes import both. This achieves the same architectural separation without the infrastructure cost. Physical separation into two services is warranted only if independent scaling or stricter network-level isolation is required — which is unlikely before the platform operates in multiple jurisdictions.

```
┌──────────────────────────────────────────────────────────────┐
│                        Client (School App, Teacher Portal)    │
│                                                              │
│   "Show me Thabo's beep test results"                        │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│   TIER 2: Identity-Aware API                                 │
│   1. Look up "Thabo Mokoena" → UUID in Layer 2               │
│   2. Call Tier 1 API: GET /results/{uuid}                     │
│   3. Enrich response with student name from Layer 2           │
│   4. Check consent status in Layer 3                          │
│   5. Return enriched response to client                       │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│   TIER 1: Core API                                           │
│   Returns: { uuid: "a3f7...", beep_test_level: 8, ... }      │
│   No PII in input. No PII in output.                         │
└──────────────────────────────────────────────────────────────┘
```

### 6.4 Multi-Tenancy Model

Vigour serves multiple schools, potentially in multiple countries. Two models:

**Model A: Tenant per School**

Each school is a tenant. Data is partitioned by school UUID at Layer 1. Layer 2 and 3 are per-school within a jurisdiction module.

**Model B: Tenant per Jurisdiction**

Each country/jurisdiction is a tenant. Schools within a jurisdiction share infrastructure. Data is partitioned by jurisdiction at the top level, then by school within.

**Recommendation:** Model B (tenant per jurisdiction). Reasons:
- Aligns with the regulatory boundary (the jurisdiction module)
- Simplifies data residency (all data for a jurisdiction is in one region)
- Allows per-jurisdiction encryption keys and access policies
- Schools within a jurisdiction share the same consent and identity configuration
- A single jurisdiction can be spun up or down without affecting others

### 6.5 Deployment Topology

> **MVP** uses a single regional instance (`africa-south1`). **Phase 2** adds a European regional instance for UK/EU. **Phase 3+** adds Vigour Central Analytics.

```
Option A: Single Global Instance (NOT recommended)

┌────────────────────────────────────┐
│        Vigour Global               │
│   All countries, all data          │
│   Single deployment                │
└────────────────────────────────────┘

Problems: Cross-border data transfer for every jurisdiction.
          Single point of failure. Single breach exposes all.
          Data residency requirements cannot be met.
```

```
Option B: Regional Instances (Recommended)

┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐
│  Vigour Africa     │  │  Vigour Europe     │  │  Vigour Americas   │
│  (africa-south1)   │  │  (EU region)       │  │  (US region)       │
│                    │  │                    │  │                    │
│  SA module         │  │  UK module         │  │  US modules        │
│  [other Africa]    │  │  [other EU]        │  │  (per-state)       │
│                    │  │                    │  │                    │
│  Layer 0-3 local   │  │  Layer 0-3 local   │  │  Layer 0-3 local   │
└────────┬───────────┘  └────────┬───────────┘  └────────┬───────────┘
         │                       │                       │
         └───────────┬───────────┴───────────┬───────────┘
                     │                       │
              ┌──────▼───────────────────────▼──────┐
              │     Vigour Central Analytics        │
              │     (anonymised aggregates only)     │
              │     Model training, product metrics  │
              │     No PII                           │
              └─────────────────────────────────────┘
```

**Regional instances** run the full stack (Layer 0-3) within the jurisdiction's required geography. Multi-region deployment is **Phase 2** (UK needs a European deployment). Only anonymised, aggregated data (Layer 4 outputs) flows to Vigour Central for cross-regional analytics and model training. Vigour Central Analytics is **Phase 3+**.

### 6.6 Offline and On-Device Privacy

The existing architecture requires offline session setup and bib assignment on the Teacher App (see [00-system-overview.md](../architecture/00-system-overview.md) and [05-client-applications.md](../architecture/05-client-applications.md)). This introduces a device-level privacy concern that the server architecture alone does not solve.

**Layer 2 data must be available offline on the teacher's device.** When a teacher sets up a session at a school with poor or no connectivity, they need:
- Student names and bib assignments (Layer 2 data) for the session setup screen
- Class rosters (Layer 2 data) to assign bibs to students

This means PII is cached on-device during sessions. The following controls are required:

- **On-device encryption:** The offline cache must be encrypted using the device's secure storage (`expo-secure-store` on mobile, encrypted keychain).
- **Minimal data:** Only the data needed for the current session's class should be cached — not the entire school roster.
- **Sync and clear:** After the session is synced back to the server, the on-device PII cache should be cleared. Stale offline caches should expire after a configurable period (e.g., 24 hours).
- **Device loss:** If a device is lost or stolen, the encrypted cache protects the data. Remote wipe capability (via MDM or app-level token revocation) provides an additional safeguard.

This is a device-level privacy concern that must be addressed in the client application design, not just the server architecture.

### 6.7 Student Transfers in the Layered Model

The existing architecture handles student transfers using OpenFGA tuple writes (see [04-authorization.md](../architecture/04-authorization.md)). In the layered model, a transfer involves coordination across layers:

- **Layer 1 results stay.** Performance data (metrics, scores, session records) remains linked to the student's UUID. This data is anonymous and does not move — it is already jurisdiction-agnostic.
- **Layer 2 identity mapping moves.** The student's `school_id` is updated to the new school. The identity record (name, DOB, external IDs) remains in Layer 2 but is now associated with the new school.
- **OpenFGA tuples update.** The old school's class enrollment tuples are deleted, and new tuples are written for the new school's class. This grants the new school access and revokes the old school's access.
- **Historical results remain at the old school's sessions.** Results created under old test sessions still belong to those sessions. The new school sees only new results by default. Sharing historical results with the new school requires an explicit access grant (an OpenFGA tuple write).

This requires coordination across Layer 1 (school_id update), Layer 2 (identity association), and OpenFGA (tuple writes/deletes). The Application API must orchestrate this as a transactional operation — partial completion (e.g., tuples updated but school_id not) would leave the system in an inconsistent state.

### 6.8 Performance Considerations

The Tier 1 / Tier 2 API split adds a lookup step to every identity-enriched request. For a class report with 30 students, the flow is:

1. Layer 2 lookup: resolve class membership to a list of UUIDs
2. Layer 1 query: fetch results for those UUIDs
3. Layer 2 enrichment: fetch student names for those UUIDs
4. Combine and return

**With schema separation (MVP):** This is just joins or sequential queries across schemas within the same PostgreSQL instance. The overhead is minimal — sub-millisecond for the cross-schema aspect. This is the expected path for the foreseeable future.

**With physical separation (future):** If Layer 1 and Layer 2 are in separate database instances, steps 1-3 become multiple network round trips. At that point, a caching strategy becomes necessary — likely a short-TTL cache of UUID-to-name mappings in Redis, invalidated on student record changes. This is a future concern, not an MVP concern.

The key takeaway: the layered model does not impose meaningful performance overhead at MVP scale with schema separation. Performance becomes a design concern only if and when physical database separation is implemented.

---

## 7. Building the Layered Schema

### 7.1 Current State (POC)

The current Vigour POC is a complete 8-stage CV pipeline (Ingest, Detect, Track, Pose, OCR, Calibrate, Extract, Output) focused on proving the technology works — can the pipeline reliably extract fitness metrics from video? The pipeline is built and functional, but the application layer does not exist yet. What exists in the codebase today:

- **`pipeline/`** — the complete CV pipeline, orchestrated by Celery (`worker/celery_app.py`)
- **`pipeline/models.py`** — Python dataclasses (Detection, Track, Pose, CalibrationResult, TestResult) that define the pipeline's internal data types. These are NOT ORM models and do not map to database tables.
- **`api/main.py`** — a FastAPI application with 4 pipeline endpoints (upload, results, annotated video, health check). No authentication or authorization.
- **`db/schema.sql`** — 3 basic tables (`sessions`, `clips`, `results`) in the public schema. These are not currently written to by the pipeline, which uses in-memory caching.
- **`infra/main.tf`** — GCP infrastructure (Cloud SQL instance, GCS bucket, Redis, GPU VM)

What does NOT exist: no `vigour_app` schema, no domain model implementation (Schools, Users, Students, Classes, TestSessions, BibAssignments), no SQLAlchemy, no Alembic, no ORM, no migrations, no ZITADEL authentication, no OpenFGA authorization, no client applications. The domain model in [01-domain-model.md](../architecture/01-domain-model.md) is a design document describing what will be built, not what currently exists.

This is an advantage: we can build the layered, privacy-by-design schema from the start instead of retrofitting PII separation onto an existing data model.

### 7.2 Implementation Phases

#### Phase 1: Build the Layer 1 Schema (Core Data) with Privacy-by-Design from the Start

**Goal:** Build the anonymised core data model that will persist through all future phases. The existing 3 tables in `db/schema.sql` (`sessions`, `clips`, `results`) will be replaced by the new `core_data` schema.

**Actions:**
- Build the Layer 1 database schema (`core_data`): sessions, test results, metrics, internal UUIDs
- Connect the pipeline to write results to the `core_data` schema (currently the pipeline uses in-memory caching and does not persist to the database)
- Ensure no PII enters the Layer 1 schema (no student names, no school names — only UUIDs)
- Implement the Tier 1 Core API
- The pipeline's Python dataclasses (`pipeline/models.py`) define the pipeline's internal data types and do not need to change — they are not database models
- This is a pure engineering task with no regulatory dependency

**Deliverable:** A running system that processes video, extracts metrics, and stores them against anonymous UUIDs in the `core_data` schema.

#### Phase 2: Build the South Africa Identity Module

**Goal:** Implement the first jurisdiction module for South Africa — the home market and the first deployment target.

**Actions:**
- Implement Layer 2 (Identity) for South Africa:
  - UUID-to-identity mapping table
  - Support for LURITS number, school number, optional SA ID
  - Encrypted PII storage with separate keys
- Implement Layer 3 (Consent) for South Africa:
  - Parental consent flow (digital + paper)
  - Consent recording and withdrawal
  - POPIA-compliant consent forms
- Implement the Tier 2 Identity-Aware API
- Implement basic reporting (Layer 4) with k-anonymity checks
- Obtain legal review of the implementation

**Deliverable:** A POPIA-compliant system deployable in South African schools with full identity and consent management.

#### Phase 3: Generalise the Module Framework (**Phase 3+**)

**Goal:** Extract the South Africa module into a pluggable framework that can be replicated for other jurisdictions.

**Actions:**
- Extract the SA-specific code into a module that implements a generic jurisdiction interface
- Define the jurisdiction module configuration schema (as described in Section 3)
- Build the module loading/configuration infrastructure
- Document the process for creating a new jurisdiction module
- Implement per-jurisdiction key management
- Implement per-jurisdiction database separation

**Deliverable:** A module framework where adding a new country is a configuration + limited code task, not a re-architecture.

#### Phase 4: Second Jurisdiction (UK or US Pilot)

**Goal:** Validate the module framework by implementing a second jurisdiction.

**Actions:**
- Build the UK or US jurisdiction module
- Deploy in a regional instance
- Validate that the core system (Layer 1, Tier 1 API) required zero changes
- Validate cross-border data flow (anonymous aggregates to central)
- Iterate on the framework based on lessons learned

**Deliverable:** Vigour running in two jurisdictions simultaneously, proving the architecture.

#### Phase 5: Video Strategy Implementation

**Goal:** Implement the configurable video retention strategy.

**Actions:**
- Implement the three video retention modes (immediate delete, time-limited, anonymised archival)
- Build the video anonymisation pipeline (face blur, body outline replacement)
- Implement per-jurisdiction video handling configuration
- Evaluate edge processing feasibility and build edge deployment option if viable
- Implement consent separation for video vs metrics

**Deliverable:** Configurable video handling that meets each jurisdiction's requirements.

### 7.3 Building the Layered Schema

The domain model design (see [01-domain-model.md](../architecture/01-domain-model.md)) describes a `Student` entity with PII fields (`first_name`, `last_name`, `date_of_birth`, `grade`, `gender`) and a `School` entity with `name`, `district`, and `province`. These entities do not exist as database tables yet — the domain model document is a design reference, not an implementation. The only database tables that exist are 3 basic pipeline support tables in `db/schema.sql` (`sessions`, `clips`, `results`), which will be absorbed into the `core_data` schema.

Because we are building the schema from scratch, we can implement the privacy-layered design directly — splitting student data across Layer 1 and Layer 2 from the start, rather than having to separate PII out of an existing monolithic schema.

**What goes in Layer 1 (`core_data`) — the anonymised student record:**
- `id` (UUID) — the stable, lifelong anchor for all results
- `school_id` (UUID) — opaque reference, no school name
- `age_band` — derived from DOB, less identifying than exact date
- `gender_category` — derived, less identifying than raw gender field
- `created_at` — timestamp

**What goes in Layer 2 (`identity`) — PII stored separately with encryption:**
- `first_name`, `last_name` — direct PII, stored as the encrypted `student_name` field in the identity module
- `date_of_birth` — encrypted; used to derive `age_band` for Layer 1
- `grade` — stored as `grade_or_year` in Layer 2
- `gender` — Layer 2 stores the exact value; Layer 1 stores only the derived `gender_category` (e.g., "M", "F")

**What this means for the School entity:**
- `name`, `district`, `province` go in Layer 2
- Layer 1 stores only `id` (UUID) and structural metadata

**The pipeline's Python dataclasses** (`pipeline/models.py`) define the pipeline's internal data types (Detection, Track, Pose, CalibrationResult, TestResult). These are not database models — they are in-memory data structures used during CV processing. They do not need to change for the layered schema; the pipeline's output will be written to `core_data` tables via a persistence layer.

**The existing `db/schema.sql`** can be replaced entirely with the new layered schema. The 3 existing tables (`sessions`, `clips`, `results`) are not in use by the pipeline and contain no data that needs to be migrated.

#### Student Entity Design Specification

The `core_data.students` and `identity.student_identities` tables will be built as two separate schemas from the start:

**Layer 1 (`core_data.students`):**

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID, PK | Stable lifelong anchor |
| `age_band` | VARCHAR | Derived from DOB: '6-7', '8-9', '10-11', '12-13', '14-15', '16-17', '18+' |
| `gender_category` | VARCHAR | Derived: 'M', 'F', 'X' |
| `school_id` | UUID FK | School UUID, not school name |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

**Layer 2 (`identity.student_identities`):**

| Field | Type | Notes |
|-------|------|-------|
| `internal_id` | UUID FK | References `core_data.students.id` |
| `first_name` | VARCHAR (encrypted) | |
| `last_name` | VARCHAR (encrypted) | |
| `date_of_birth` | DATE (encrypted) | Full date, used to derive `age_band` |
| `grade` | VARCHAR | e.g., 'Grade 7' |
| `gender` | VARCHAR (encrypted) | Full value: 'Male', 'Female', 'Other' |
| `external_id` | VARCHAR (encrypted) | LURITS, UPN, etc. |
| `external_id_type` | VARCHAR | 'LURITS', 'UPN', 'SA_ID', etc. |

### 7.4 What to Build First

Priority order based on regulatory risk, business value, and technical dependency:

| Priority | Item | Rationale |
|----------|------|-----------|
| 1 | Layer 1 schema and Core API | Foundation for everything else; no regulatory dependency |
| 2 | SA Identity Module (Layer 2) | Required for the first paying deployment |
| 3 | SA Consent Module (Layer 3) | Required for POPIA compliance in SA |
| 4 | Basic Reporting (Layer 4) | Required for schools to use the product |
| 5 | Module framework generalisation | Required before second jurisdiction |
| 6 | Video retention configuration | Required for jurisdictions that mandate retention or deletion policies |
| 7 | Edge processing | Long-term aspiration; only required for well-resourced deployments or jurisdictions that prohibit cloud video processing |
| 8 | Cross-border data flow | Required when entering a second jurisdiction |

### 7.5 MVP vs Full Implementation

| Capability | MVP | Full |
|-----------|-----|------|
| Core data model | Yes — Layer 1 with UUIDs | Same |
| Identity module | SA only | Per-jurisdiction, pluggable |
| Consent management | Basic consent record | Granular consent types, withdrawal cascades, DSAR handling |
| Video retention | Retain with linked metrics — 90 days hot, then cold storage, deleted with metrics or on consent withdrawal | Configurable per jurisdiction (immediate delete to retain with metrics; `video_max_retention_days` for jurisdiction-imposed caps) |
| Reporting | Individual + class level | All levels with k-anonymity |
| Edge processing | No — cloud only (edge impractical for SA schools) | Configurable for well-resourced deployments |
| Cross-border flow | Not needed (SA only) | Regional instances + central analytics |
| Key management | Single Cloud KMS key with column encryption | Per-jurisdiction Cloud KMS keys; HSM at scale |
| Multi-tenancy | Single-tenant (SA) | Multi-jurisdiction |

---

## 8. References and Related Documents

### Internal Documents
- [POPIA Student Identity Research](./popia-student-identity.md) — Detailed analysis of SA ID number storage under POPIA, LURITS as an alternative identifier, and consent requirements for children's data in South Africa.

### Regulatory Frameworks Referenced
- **South Africa:** Protection of Personal Information Act (POPIA), 2013
- **United Kingdom:** UK GDPR + Data Protection Act 2018; ICO Age Appropriate Design Code (Children's Code)
- **United States:** FERPA (Family Educational Rights and Privacy Act); COPPA (Children's Online Privacy Protection Act); Illinois BIPA (Biometric Information Privacy Act); California CCPA/CPRA and SOPIPA; New York Ed Law 2-d
- **European Union:** GDPR (General Data Protection Regulation) — relevant as a reference framework and for EU adequacy decisions

### Privacy Engineering Concepts
- **k-anonymity:** Sweeney, L. (2002). "k-anonymity: a model for protecting privacy." Ensures that each record in a dataset is indistinguishable from at least k-1 other records with respect to quasi-identifiers.
- **Privacy by Design:** Cavoukian, A. (2009). Seven foundational principles. Embedded in GDPR Article 25 and reflected in POPIA's data minimisation requirements.
- **Pseudonymisation vs Anonymisation:** Article 29 Working Party, Opinion 05/2014 on Anonymisation Techniques. Key distinction: pseudonymised data is still personal data; anonymised data is not.

---

*This document is architectural research for the Vigour project. It does not constitute a final technical design or legal advice. All regulatory interpretations should be validated by qualified legal counsel in each target jurisdiction before implementation. The architecture described here is a starting point for discussion and will evolve as business requirements, technical constraints, and regulatory landscapes become clearer.*

---

## Appendix A: US Jurisdiction Module

US deployment is deferred. This appendix retains the US module configuration for reference.

#### United States — FERPA + State Laws

| Aspect | Configuration |
|--------|---------------|
| Primary legislation | FERPA (federal) + state laws (vary significantly) |
| Age of consent for data | 18 (FERPA) for education records; COPPA applies to under-13s for online services |
| Parental consent | FERPA: school/district can share with "school officials" with "legitimate educational interests" without individual parental consent; COPPA: verifiable parental consent for under-13s |
| Recommended ID type | State student ID or district-assigned number |
| Data residency | No federal data localisation requirement; some states (e.g., California) have specific rules |
| Video retention | No blanket federal rule; state-specific |
| Breach notification | State-by-state (all 50 states have breach notification laws, thresholds vary) |
| Right to erasure | FERPA: right to amend, not delete; CCPA/CPRA (California): right to delete |
| Special considerations | FERPA is the dominant framework but it is institution-centric (the school is the gatekeeper, not the individual); state Student Privacy Pledge; no single national standard |

Key US differences:
- **FERPA's "school official" exception** means that Vigour, as a service provider to the school, may process student education records without individual parental consent — if the school designates Vigour as a "school official" with a "legitimate educational interest" and appropriate contractual controls are in place. This is fundamentally different from POPIA's model.
- **No single national privacy law** — the compliance burden is multiplied by the number of states. California (CCPA/CPRA + SOPIPA), New York (Ed Law 2-d), Illinois (BIPA for biometric data), Colorado, Connecticut, Virginia all have distinct requirements.
- **Illinois BIPA is a critical risk:** If Vigour processes video to identify or track individuals using facial geometry or other biometric identifiers, BIPA requires informed written consent and has a private right of action (individuals can sue, not just regulators). This has produced massive class-action settlements (Facebook: $650M, TikTok: $92M). The video processing layer must be architected to avoid triggering BIPA — which means no facial recognition, no biometric templates, no persistent biometric identifiers.
- **The multi-state problem** argues strongly for the modular architecture: Vigour cannot build one US-wide configuration. It needs per-state sub-modules, or at minimum, must comply with the strictest applicable state law.

#### US Module Comparison

| Feature | United States |
|---------|---------------|
| Age for self-consent | 18 (FERPA) / 13 (COPPA) |
| Parent consent model | School-mediated (FERPA) |
| National student ID | No national ID; state/district |
| Data residency | No federal rule; state varies |
| Breach notification | State-by-state |
| Biometric-specific law | IL BIPA, TX CUBI, WA |
| DPA/DPIA required | No federal equivalent |
| Right to erasure | FERPA: amend only; CCPA: yes |

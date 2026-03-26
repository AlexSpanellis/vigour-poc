# Data Privacy and Architecture Decisions

**Date:** March 2026
**Status:** Active -- subject to legal review before implementation
**Disclaimer:** These architectural decisions are based on research and regulatory analysis. They do not constitute legal advice. Vigour must obtain formal legal opinions from qualified counsel in each target jurisdiction before implementation. Decisions may be revised as legal review, regulatory changes, or business requirements evolve.

---

## 1. Context

Vigour is a CV-based fitness testing platform for schools. A teacher records video of learners performing fitness tests, uploads it, and a computer vision pipeline extracts performance metrics automatically. The system handles video of minors, pose estimation data, student identity information, and fitness scores -- all of which carry regulatory obligations across every jurisdiction Vigour will operate in.

Five research documents inform these decisions. The [POPIA Student Identity](./popia-student-identity.md) document analyses the legal implications of storing South African student identifiers, concluding that LURITS numbers are the preferred primary identifier with SA ID numbers as an optional, higher-burden alternative. The [Data Classification and Regulatory Landscape](./data-classification-and-regulation.md) document maps every data type Vigour handles against ten jurisdictions, producing a risk heat map that identifies video and biometric-adjacent data as the highest-risk categories. The [Modular Data Architecture](./modular-data-architecture.md) document proposes a five-layer, jurisdiction-agnostic architecture that separates anonymised performance data from personally identifiable information. The [GDPR Article 9 analysis](./gdpr-article9-fitness-scores.md) concludes that fitness performance scores are health data under GDPR Article 9 / UK GDPR, requiring explicit consent and mandatory DPIA. The [UK AADC requirements](./uk-aadc-requirements.md) document assesses all 15 standards of the Age Appropriate Design Code and identifies high privacy defaults, profiling controls, and age-banded transparency as critical requirements for UK deployment.

These decisions translate that research into concrete architectural and compliance commitments for the Vigour platform.

### Deployment Priority

- **Phase 1: South Africa** — first market, POPIA compliance is the baseline.
- **Phase 2: United Kingdom and EU** — most likely second market, UK GDPR + Age Appropriate Design Code + GDPR compliance required.
- **Other territories** (US, India, UAE, Kenya, Nigeria, Brazil, Australia) — architecture supports them but they are not driving decisions. Compliance research exists (see [Data Classification and Regulatory Landscape](./data-classification-and-regulation.md)) but detailed planning is deferred.

The key principle: build the MVP with enough architectural flexibility for EU/UK expansion, but don't over-engineer for territories that may be years away.

---

## 2. Core Architectural Principle

**Decision: Privacy by default, identity by module.**

- The internal system operates on anonymised UUIDs only. The core data layer knows what a student did, never who they are.
- All PII lives in a separate, pluggable identity layer that varies by jurisdiction.
- The core data layer is jurisdiction-agnostic. No country-specific logic, no PII, no consent logic in the pipeline or core schema.
- Layer 1 (core) cannot read Layer 2 (identity). The data flow is unidirectional: Layer 2 wraps Layer 1, not the other way around.

**Implementation for MVP:** This is a LOGICAL separation implemented as schema separation within a single Cloud SQL instance. Separate PostgreSQL schemas (`core_data`, `identity`, `consent`) with dedicated database roles and no cross-schema permissions. Physical separation into separate database instances is deferred until regulatory or scaling pressure demands it.

**Relationship to what exists today:** The `vigour_app` schema does not exist yet — the domain model described in [01-domain-model.md](../architecture/01-domain-model.md) is a design, not an implementation. The only database artifact is `db/schema.sql`, which defines 3 basic pipeline support tables (`sessions`, `clips`, `results`) in the public schema; these are not currently written to by the pipeline (which uses in-memory caching). The privacy-layered schema design IS the application schema — we are building the right schema from the start, not refactoring an existing one. `core_data` will absorb the existing pipeline tables and add the anonymised domain model (students as UUIDs, test results, metrics). `identity` is a NEW schema for the Layer 2 identity mapping (student UUID to external identifiers, names, DOB). `consent` is a NEW schema for consent records and audit trails. ZITADEL (staff authentication) and OpenFGA (authorization) are planned but not yet deployed — their schemas will be added when those systems are implemented. This is an advantage: we can build privacy-by-design into every schema from day one instead of retrofitting PII separation onto an existing data model.

---

## 3. Data Classification Decisions

### Video Data

| Decision | Detail |
|----------|--------|
| **Video is personal data** | Video contains identifiable children. We do NOT claim it is "anonymised." |
| **Stored permanently in-region only** | Raw and annotated video reside in GCS in the local jurisdiction (`africa-south1` for SA). |
| **Audio stripped at ingestion** | Audio contains voiceprints (biometric under COPPA 2025) and incidental conversations. No audio is needed for fitness metric extraction. |
| **GPS/device metadata stripped at ingestion** | GPS coordinates, device serial number, and device model are stripped from video EXIF/metadata at ingestion. Traceability is maintained through the session record in the application layer (school_id UUID, teacher_id, upload timestamp, test_type), not through embedded file metadata — the GPS in the video file is redundant and a privacy liability. Video creation timestamp from EXIF may optionally be preserved as a cross-check against the session timestamp. |
| **GPU processing is ephemeral cross-region** | Video is pulled to the processing region, metrics extracted, local copy purged. Never permanently stored outside the region. |
| **Retention tied to linked metrics lifecycle** | Video is the source of truth for the metrics it produces — if metrics are retained for longitudinal tracking (7+ years), the video that proves those metrics must also be retained. **0–90 days:** Hot storage (GCS Standard) for active access — teacher review, re-processing, dispute resolution. **90 days onwards:** Cold storage (GCS Nearline, then Coldline) with restricted access, audit-logged retrieval only for disputes, re-processing, or quality assurance. **Deletion:** Video is deleted when the linked metrics are deleted, OR on consent withdrawal. On consent withdrawal, if Layer 2 identity is deleted, the video becomes unlinked (no way to associate it with an individual without the identity mapping), which reduces the privacy risk of continued storage. **No fixed maximum retention period** — retention is tied to the lifecycle of the linked metrics, not an arbitrary time limit. **Configurable per jurisdiction** — some jurisdictions may impose maximum retention periods; the `jurisdiction_config` table's `video_max_retention_days` field can be set to enforce this where required (set to NULL for "retain with metrics"). |
| **Annotated video follows raw video retention** | Teachers need to review annotated results. Annotated video stored in the local GCS bucket with the same retention lifecycle as raw video — hot storage for 90 days, then cold storage, deleted when linked metrics are deleted or on consent withdrawal. |
| **Bystander coverage** | Students without consent are excluded from video recording. The teacher is responsible for ensuring only consented students are in the recording area. For group tests (e.g., shuttle run with multiple students), the teacher must confirm all visible students have consent before starting recording. If a non-consented student is inadvertently captured, the video must be re-recorded without them, or the non-consented student must be operationally excluded from the recording frame. This is an operational procedure, not a technical control — documented in teacher training materials. Operational procedure -- owned by product/operations, not an engineering deliverable. Long-term, investigate automated detection and blurring of non-subject individuals. |
| **Annotated video is personal data** | Annotated video (with bounding boxes and overlays) is treated as personal data regardless of whether it has a different regulatory status than raw video. Same storage, access control, and retention rules apply. |

**Rationale:** The data classification research rates raw video of children as "Critical" sensitivity across all ten jurisdictions analysed. Ephemeral cross-region processing is the pragmatic path given GPU availability constraints, while permanent in-region storage satisfies data residency requirements.

### Student Identity Data

| Decision | Detail |
|----------|--------|
| **LURITS number is the primary external identifier for SA** | Nationally unique, persistent across schools, lower sensitivity than a national ID, less likely to require prior authorisation from the Information Regulator. |
| **SA ID numbers are NOT stored by default** | Optional only, with separate explicit parental consent and field-level encryption. Storing SA ID numbers triggers heightened POPIA obligations (S57-58 prior authorisation, breach severity, lifetime identifier risk). |
| **Internal UUIDs are the only identifier in the core data layer** | Layer 1 contains no external identifiers, no names, no dates of birth. |
| **Each jurisdiction gets a pluggable identity module** | The module maps internal UUIDs to local identifiers (LURITS for SA, UPN for UK, state/district IDs for US). Configurable per deployment. |

**Identity module interface:**

```python
class IdentityModule(Protocol):
    def resolve_student(self, internal_id: UUID) -> StudentIdentity | None: ...
    def create_mapping(self, internal_id: UUID, external_id: str, id_type: str) -> None: ...
    def delete_mapping(self, internal_id: UUID) -> None: ...
    def search_by_external_id(self, external_id: str, id_type: str) -> UUID | None: ...
```

SA implementation: `id_type='LURITS'`. UK implementation: `id_type='UPN'`.

**Rationale:** The POPIA research concludes that LURITS offers the best balance of interoperability and compliance cost. SA ID numbers carry disproportionate risk (lifetime identifier, identity theft exposure, potential prior authorisation requirement) for marginal matching benefit.

### Fitness Scores and Metrics

| Decision | Detail |
|----------|--------|
| **Stored in Layer 1 with UUIDs only** | No PII attached. Numeric values linked to opaque internal identifiers. |
| **Low sensitivity once detached from identity** | Sprint times, rep counts, and beep test levels are meaningless without knowing whose they are. |
| **Can be retained indefinitely** | Longitudinal tracking requires historical data. Identity (Layer 2) can be deleted independently -- Layer 1 data becomes truly anonymous at that point. |
| **Treated as GDPR Article 9 health data for UK/EU** | Fitness performance scores are special category data (health data) when linked to identity. The ICO explicitly classifies "athletic performance" as health data. Requires explicit consent and mandatory DPIA for UK/EU deployment. Layer 1 scores without Layer 2 identity are not health data. See [GDPR Article 9 analysis](./gdpr-article9-fitness-scores.md). |

### Biometric-Adjacent Data (Pose Estimation, Skeletal Keypoints)

| Decision | Detail |
|----------|--------|
| **Treat as potentially biometric in architecture** | Even though not all jurisdictions classify pose estimation as biometric, some do (COPPA 2025 explicitly lists gait patterns). Treating it as biometric everywhere avoids per-jurisdiction reclassification risk. |
| **Do not persist raw skeletal keypoint sequences** | Extract the fitness metric (time, count, distance), discard the keypoints. Raw pose data is intermediate processing output, not a stored artifact. |
| **Store derived metrics only** | Scores, times, counts -- not the skeletal sequences used to compute them. |

**Rationale:** Treat pose estimation data as potentially biometric because temporal accumulation of skeletal keypoint data creates increasingly identifying profiles (research shows 79-82% identification accuracy). This conservative position avoids reclassification risk across jurisdictions. The US context (COPPA 2025 explicitly listing gait patterns, BIPA per-scan damages) reinforces this decision but does not drive it.

### Consent Records

| Decision | Detail |
|----------|--------|
| **Append-only audit trail** | Consent events are never deleted. Withdrawal is recorded as a new event, not a deletion of the grant. |
| **Per-jurisdiction consent module** | Different age thresholds (13 UK, 16 GDPR default, 18 SA), different consent types, different parental verification methods. Configurable per deployment. |

---

## 4. Video Processing Architecture

**Decision: Ephemeral cross-region processing for SA launch.**

```
School → Video → GCS (africa-south1)  → GPU VM (designated EU region) → Metrics → GCS (africa-south1)
                  [permanent storage]    [ephemeral, auto-purge]                   [permanent storage]
```

> Specific GPU processing regions are defined in the [Infrastructure Architecture](../architecture/07-infrastructure.md).

**Note:** Ephemeral GPU processing requires pipeline modifications from the current POC behavior (which writes to persistent UPLOAD_DIR and OUTPUT_DIR). Adapting the pipeline for in-memory / tmpfs processing with auto-purge is a Phase 1 engineering task.

**Why this works legally:**

- Transient processing with immediate deletion is a weaker form of transfer than persistent storage abroad. The data controller (Vigour) retains control throughout. No data is stored at rest in the processing region.
- POPIA Section 72 restricts transfers to third parties in foreign jurisdictions. This is same-controller processing on Vigour's own infrastructure, not a third-party transfer.
- The EU (where the designated GPU processing region sits) has GDPR protections that are "substantially similar" to POPIA, strengthening the adequacy argument.
- GCP's data processing agreement provides contractual backing.

**Technical requirements:**

| Requirement | Implementation |
|-------------|----------------|
| No persistent video on GPU VM | Process in memory or tmpfs; ephemeral SSDs only |
| Auto-purge on job completion | Cleanup hook verifies all temporary storage cleared, success or failure |
| Audit logging | Every cross-region job logs: source region, processing region, start time, end time, purge confirmation |
| Network controls | GPU VM has no egress path for video except back to originating GCS bucket (annotated video) and application DB (metrics) |
| GCP DPA coverage | DPA explicitly covers transient processing with no persistent storage; ephemeral SSDs cryptographically erased on VM stop |

**Per-jurisdiction override:** If a jurisdiction prohibits even transient cross-border processing, in-region GPU processing is supported where GPU VMs are available. Edge processing is a long-term option for well-resourced deployments.

---

## 5. Consent Model Decisions

**Working assumption: Vigour is a responsible party (not just an operator)** for POPIA purposes. Vigour determines the means of processing (CV pipeline, scoring algorithms, data storage architecture) and retains data for its own purposes (product improvement, aggregate analytics). This means Vigour needs its own consent relationship with parents, not just a processing agreement with schools. Legal counsel must confirm this classification. If Vigour is instead classified as an operator, the consent flow changes: schools would obtain consent, and Vigour would process under a written operator agreement (POPIA S20-21).

| Decision | Detail |
|----------|--------|
| **Vigour implements its own consent flow** | We do NOT rely on the school's existing consent. Most school consent forms do not specifically mention third-party fitness testing providers or cover the specific processing Vigour performs. |
| **Consent is separate from school enrollment** | Voluntary, not bundled. A student's participation in required school activities cannot be conditioned on Vigour consent. |
| **Parental consent required for all under-18s in SA** | POPIA Section 35: consent must come from a "competent person" (parent or legal guardian under the Children's Act). No graduated consent for older teenagers. |
| **Consent module is configurable per jurisdiction** | Age thresholds vary: 13 (UK), 16 (GDPR default), 18 (SA/POPIA). A single school in the UK may have students who can consent themselves alongside students who need parental consent. |
| **Granular consent items** | Consent covers VIDEO_CAPTURE, METRIC_PROCESSING, IDENTITY_STORAGE, DATA_SHARING, REPORTING, and MODEL_TRAINING (deferred -- not collected in Phase 1) as separate items. Minimum viable consent for participation: VIDEO_CAPTURE + METRIC_PROCESSING + IDENTITY_STORAGE. |
| **Withdrawal triggers Layer 2 deletion** | Withdrawing IDENTITY_STORAGE consent deletes the Layer 2 record. Layer 1 metrics become orphaned -- truly anonymous with no mapping back to the individual. |

### SA Consent Flow

1. School admin creates a test session in Vigour
2. Vigour generates a consent request for each student in the class
3. School distributes consent links to parents (via school communication channels — email, SMS, WhatsApp, printed letter with QR code)
4. Parent opens consent form (web page, no app install required)
5. Form explains: what data is collected (video, metrics), why (fitness assessment), who sees it (teacher, student, parent if opted in), how long it's kept, rights (access, deletion, withdrawal)
6. Parent selects consent items: VIDEO_CAPTURE, METRIC_PROCESSING, IDENTITY_STORAGE (minimum required), DATA_SHARING and REPORTING (optional)
7. Parent submits — consent record created with timestamp, IP, consent items
8. **Paper alternative:** School admin enters consent manually in admin interface, uploads photo of signed form as attachment, record marked `source: paper`
9. **Withdrawal:** Parent contacts school or uses consent portal. Withdrawal processed within 5 business days. Layer 2 identity data deleted; Layer 1 metrics become anonymous.
10. Students without consent are excluded from video recording (teacher manages this operationally)

**Phase 1 scope note:** For SA MVP, this is a simple web form. No app integration. No identity verification beyond the school's distribution channel. MODEL_TRAINING consent item is deferred to Phase 2.

---

## 6. Cross-Border and Data Residency Decisions

| Decision | Detail |
|----------|--------|
| **PII (Layer 2) always stays in-region** | Student names, external identifiers, contact information never leave the jurisdiction. |
| **Core metrics (Layer 1) stay in-region** | Low-risk if they needed to move (no PII), but kept in-region as the default. |
| **Aggregated data (Layer 4) can flow to Vigour Central** | Tiered k-anonymity enforced: class/group level k>=5, school level k>=10, district/regional level k>=20, national level: no minimum -- already sufficiently aggregated. If a group falls below the threshold, suppress or merge with adjacent groups. Genuinely anonymous aggregate data is not personal data and can cross borders freely. |
| **Video never permanently leaves the region** | Permanent storage in local GCS only. Ephemeral cross-region GPU processing with auto-purge. |
| **GPU processing is ephemeral cross-region with contractual safeguards** | DPA with GCP covering transient processing, no persistent storage, cryptographic erasure. |
| **SA launch regions** | GCP `africa-south1` (Johannesburg) for all persistent data. Designated European GPU processing region for ephemeral processing (see [Infrastructure Architecture](../architecture/07-infrastructure.md)). |

---

## 7. Jurisdiction Deployment Strategy

**Decision: SA is the first deployment. POPIA compliance is the baseline.**

**Decision: The architecture is jurisdiction-agnostic at the core.** Each new country requires only a jurisdiction module (identity fields, consent flow, retention periods, video rules). The core system, CV pipeline, and scoring engine remain untouched.

### Tier 1 — Active Planning

| Jurisdiction | Framework | Phase | Status |
|--------------|-----------|-------|--------|
| **South Africa** | POPIA | Phase 1 | Launching. All Phase 1 decisions in this document are SA-specific. |
| **United Kingdom** | UK GDPR + Age Appropriate Design Code (AADC) | Phase 2 | Planned next. Identity module (UPN), consent age threshold (13), DPIA, and AADC compliance required. |

### Tier 2 — Architecture Supports, Planning Deferred

The modular architecture supports any jurisdiction, but detailed compliance planning for the following territories is deferred until business requirements demand it. EU/EEA is architecturally similar to the UK (GDPR-based) and the compliance research is complete, but it is not an active commitment — EU deployment is contingent on UK success.

| Category | Jurisdictions | Notes |
|----------|---------------|-------|
| **GDPR-aligned (post-UK)** | EU/EEA | Architecturally supported by UK module. Consent age thresholds vary by member state (default 16). Separate European GCS region. Deployment contingent on UK success. |
| **Moderate frameworks** | Kenya, Nigeria | GDPR-aligned. Manageable compliance effort with standard identity/consent modules. |
| **Stricter requirements** | Brazil, Australia, UAE | Stricter biometric classification, mandatory DPIAs, children's codes. Australia: Bunnings precedent on video biometrics, forthcoming Children's Online Privacy Code. UAE: 2025 Child Digital Safety Law. |
| **Highest complexity** | US (BIPA, COPPA, FERPA), India (DPDP) | US: BIPA per-scan damages, COPPA 2025 gait patterns, FERPA structuring, state patchwork. India: prohibition on tracking/behavioral monitoring of children. |

These Tier 2 jurisdictions are not driving current architectural decisions. See [Data Classification and Regulatory Landscape](./data-classification-and-regulation.md) for the full analysis.

---

## 8. Progressive Implementation Roadmap

### Phase 1: SA Launch

POPIA compliance is the target. The architectural foundations for EU/UK expansion are built now so they don't need to be reworked for Phase 2.

| Component | Implementation |
|-----------|----------------|
| Database separation | Schema separation within single Cloud SQL instance (`core_data`, `identity`, `consent` schemas with dedicated roles). This is the modular foundation — Layer 1 contains zero PII, Layer 2 is pluggable per jurisdiction. |
| Identity module | SA module: LURITS-first, optional SA ID with separate consent and encryption. The identity module interface is designed to be pluggable — LURITS is the SA implementation, but the interface supports swapping in UPN (UK) or other identifiers without changing the core data layer. |
| Consent management | Digital consent form distributed via school + paper alternative. Parental consent required for all under-18s (POPIA S35). Granular consent items (VIDEO_CAPTURE, METRIC_PROCESSING, IDENTITY_STORAGE, DATA_SHARING, REPORTING, MODEL_TRAINING) are implemented from day one — even if SA only uses a simple consent form, the data model supports the granularity EU/UK will need. |
| Phase 1 scope limits | Layer 4 (aggregated reporting) is limited to class-level and school-level views for teachers and school heads. District-level and national-level reporting is Phase 2+. The MODEL_TRAINING consent item is deferred — no student data is used for model training in Phase 1. The consent data model supports it for future use. |
| Video storage | GCS `africa-south1` for permanent storage. 0–90 days hot storage (GCS Standard), then cold storage (GCS Nearline/Coldline). Video retained for the duration of linked metrics — no fixed maximum. Retention configurable per jurisdiction via `jurisdiction_config.video_max_retention_days` (NULL = retain with metrics). |
| GPU processing | Ephemeral in designated European GPU processing region with auto-purge (see [Infrastructure Architecture](../architecture/07-infrastructure.md)) |
| Encryption | Single Cloud KMS key for PII column encryption in Layer 2 |
| Breach notification | Phase 1 implements a documented manual process. If a breach involving student personal data is detected: (1) Information Officer is notified immediately, (2) Information Officer assesses severity and scope, (3) if personal data was compromised: notify the Information Regulator via the eServices breach reporting portal as soon as reasonably possible (POPIA S22), (4) notify affected parents/guardians with: what data was compromised, when, what Vigour is doing about it, (5) document the breach, response, and lessons learned. Automated breach detection and response is Phase 3+. |
| Scoring engine | Outputs raw scores and percentiles only. Categorical labels ('below average', 'meets expectations', 'excellent') are applied in the presentation layer and are configurable per jurisdiction. This ensures the AADC 'detrimental use' requirement (Standard 5) can be addressed by changing presentation without modifying the data layer. For SA Phase 1, simple category labels may be used. For UK Phase 2, labels must be reviewed against the AADC best interests and detrimental use standards. |
| Access control | Teachers see results only for students in their assigned classes. School heads see results for all students in their school. Students see only their own results. Parents (if opted in) see only their child's results. Cross-school visibility is not available. This is enforced by OpenFGA relationship-based access control, not application logic. |
| Compliance | Information Officer registered with SA Information Regulator. PAIA Section 51 manual prepared and published (legal requirement before processing personal data). |
| Privacy assessment | Privacy Impact Assessment conducted as best practice (POPIA does not explicitly require one). |
| DSAR process | Manual Data Subject Access Request process handled by the Information Officer. The data model supports "find all data for student X" and "delete all PII for student X" operations from day one. |
| API structure | Single FastAPI application with separate route groups (Tier 1 core, Tier 2 identity-aware). Module boundary enforced in code, not infrastructure. |

### Phase 2: UK/EU Deployment

UK is the likely first international market, with EU concurrent or shortly after. This phase requires specific changes beyond what Phase 1 delivers.

| Component | Implementation |
|-----------|----------------|
| Identity module | UK module: UPN (Unique Pupil Number) as primary identifier. EU modules vary by country. The pluggable identity interface built in Phase 1 means this is a new implementation, not a rewrite. Whether UK UPN has similar restrictions to SA ID numbers (sensitivity, prior authorisation) needs legal opinion. |
| Consent module | Consent age threshold changes: 13 in UK, 16 in most EU member states (vs 18 in SA). The configurable consent module from Phase 1 supports this without core changes. |
| GDPR Article 9 | **Decided:** Fitness performance scores will be treated as GDPR Article 9 special category data (health data) for UK/EU deployment. The ICO explicitly classifies "athletic performance" as health data. The CJEU Lindenapotheke ruling (C-21/23, 2024) confirms broad interpretation. This requires explicit consent and a mandatory DPIA. See [GDPR Article 9 analysis](./gdpr-article9-fitness-scores.md). |
| UK AADC | **Decided:** UK AADC compliance required — Vigour is in scope as an edtech provider (not a pure processor). Key requirements: (1) High privacy defaults — results private by default, parent access opt-in. (2) Profiling — norm comparison and progress tracking are profiling and must be justified as core service in DPIA. (3) Age-banded privacy notices required (at least 2 versions). (4) Detrimental use — result presentation must avoid harmful labelling. See [UK AADC requirements](./uk-aadc-requirements.md). |
| DPIA | Data Protection Impact Assessment required before deployment. Mandatory under GDPR Article 35 for large-scale processing of children's data. |
| Data residency | GCS bucket in a European region for all persistent data. Identity module configured for UK/EU identifiers. |
| Encryption | Per-jurisdiction Cloud KMS keys |
| Reporting | k-anonymity enforcement at Layer 4. Thresholds configurable per jurisdiction. |
| Pose estimation | Legal opinion needed on whether pose estimation / skeletal keypoints constitute biometric data under UK/EU law. Architecture already treats it as potentially biometric (keypoints not persisted). |
| DSAR process | Automated DSAR handling through the consent module. |

### Phase 3: Scale

| Component | Implementation |
|-----------|----------------|
| Database | Physical separation if regulatory or scaling pressure requires it |
| Deployment | Multi-region deployment topology (regional instances + Vigour Central for anonymous aggregates) |
| Encryption | Full key hierarchy; HSM-backed master keys if enterprise customers require it |
| Processing | Edge processing option for jurisdictions that demand on-premises video processing |

---

## 9. What Phase 1 Must Get Right for Phase 2

These are the non-negotiable architectural requirements in Phase 1 (SA) that prevent a rewrite when Phase 2 (UK/EU) begins. Every item here is a "pay now or pay triple later" decision.

| Requirement | Why it matters |
|-------------|----------------|
| **The core data layer must contain zero PII** | If PII leaks into Layer 1 during SA development, it's a rewrite for EU/UK. This is the single most important invariant. |
| **Consent module must be configurable** | Age thresholds, consent types, and parental verification methods must not be hardcoded to SA values. SA uses 18 for all minors; UK uses 13; EU varies by member state. The consent module must accept these as configuration, not code changes. |
| **Identity module must be pluggable** | LURITS is SA-specific. UK uses UPN, EU varies by country. The interface between core data and identity must be clean enough to swap implementations without touching the core schema or pipeline. |
| **Video retention must be configurable per jurisdiction** | UK/EU may have different retention requirements. Retention periods, cold storage transitions, and deletion timelines must be configuration, not constants. |
| **k-anonymity thresholds must be configurable** | Different jurisdictions may require different minimums for aggregate reporting. The tiered thresholds (class k>=5, school k>=10, district k>=20) must be adjustable per jurisdiction. |
| **Consent granularity must be in place** | Even if SA only uses a simple consent form, the data model must support granular consent items (video, metrics, identity, long-term retention) because EU/UK will need them. Building granular consent into the schema now is trivial; retrofitting it later is a migration. |
| **DSAR handling must be designed** | Even if Phase 1 DSAR is manual, the data model must support "find all data for student X" and "delete all PII for student X" operations. EU/UK GDPR requires timely responses to data subject access requests — the data architecture must make this possible, not heroic. |
| **Privacy defaults must be configurable per jurisdiction** | SA may allow teachers to see all students' results by default; UK AADC requires high privacy by default (results private, parent access opt-in). The default visibility/sharing state must be a jurisdiction-level configuration, not hardcoded. |
| **Result sharing must be opt-in toggleable** | Sharing results to parents, between classes, between schools must be implemented as toggleable features, not hardwired data flows. UK AADC Standard 7 requires sharing to be off by default. If sharing is built as a core data flow in Phase 1, it will need to be reworked. |
| **Profiling features must be toggleable** | Norm comparison and progress tracking must be features that can be enabled/disabled per jurisdiction or per school. UK AADC Standard 12 requires profiling to be off by default unless justified as essential to the core service. |
| **UI must support age-band awareness** | The system must know the child's age band (or at least school year/grade) to serve age-appropriate privacy notices and apply appropriate defaults. UK AADC requires different treatment for different age groups. This metadata must be in the data model from Phase 1. |

---

## 10. What We Are NOT Doing (And Why)

| Decision NOT to do | Rationale |
|--------------------|-----------|
| NOT storing SA ID numbers by default | Disproportionate risk (lifetime identifier, identity theft, prior authorisation burden) for marginal matching benefit over LURITS. |
| NOT claiming video is "anonymised" | Face blurring alone does not achieve anonymisation. Body shape, gait, clothing, and contextual information still enable identification. Claiming anonymisation is legally indefensible. |
| NOT requiring edge processing for SA schools | Impractical. Unreliable power (load-shedding), no IT staff, no GPU budget, limited connectivity. Cloud processing with ephemeral cross-region transfer is the viable path. |
| NOT building separate databases per layer for MVP | Over-engineered. Schema separation with dedicated roles provides logical isolation at minimal cost. Physical separation adds infrastructure complexity without proportional security benefit at current scale. |
| NOT implementing HSM key hierarchies for MVP | Cost and complexity are unjustified at single-jurisdiction, single-instance scale. Cloud KMS with automatic rotation is sufficient. |
| NOT deploying multi-region for MVP | SA is the only launch market. Multi-region adds infrastructure cost and operational complexity with no immediate benefit. |
| NOT persisting raw skeletal keypoint sequences | Temporal accumulation creates biometric profiles. Derived metrics (times, counts, distances) serve the product purpose without the biometric risk. |
| NOT implementing face recognition | Vigour does not need to identify who is in the video by face. Face detection (is a face present?) is used for subject localisation only. Face recognition is explicitly excluded from the system. |

---

## 11. Risk Acceptance

The following risks are consciously accepted for the SA launch:

| Risk | Mitigation | Residual exposure |
|------|-----------|-------------------|
| **Ephemeral cross-region video transfer (SA to EU)** | GCP DPA, ephemeral SSDs with cryptographic erasure, audit logging, no persistent storage abroad, EU provides "adequate" protection | Legal opinion needed on whether POPIA S72 requires explicit consent for transient processing. Defensible position but untested with the Information Regulator. |
| **Schema separation instead of physical separation for MVP** | Dedicated PostgreSQL roles, no cross-schema permissions, application-level module boundaries | A database-level breach exposes all schemas. Acceptable at current scale; upgradeable to physical separation. |
| **Single Cloud KMS key for MVP** | Cloud KMS handles key storage, access control, automatic rotation | No per-layer key isolation. Acceptable; rotatable and upgradeable to per-jurisdiction keys. |
| **Small-school re-identification risk from aggregated reports** | Tiered minimum group sizes (class k>=5, school k>=10, district k>=20) before reporting aggregates; groups below threshold suppressed or merged; Layer 1 contains no school names (only UUIDs) | An attacker with Layer 2 access could re-identify individuals in small cohorts. Access controls on Layer 2 are the primary mitigation. |
| **Long-term video retention in cold storage** | Restricted access controls, audit logging, cold storage (GCS Nearline/Coldline) after 90 days, and the identity-unlinking mechanism on consent withdrawal (deleting Layer 2 makes the video effectively anonymous). Jurisdiction-configurable maximum retention where required. | Retained video is a breach target. Accepted because the video is the evidence chain for the metrics — if a parent disputes a score, the source video is needed. Pipeline improvements require re-processing original video. Quality assurance requires comparing pipeline output against source. Deleting video while retaining metrics removes the evidence chain. Privacy risk is mitigated by cold storage with restricted access, audit logging, and the fact that consent withdrawal deletes the identity link. |

---

## 12. Open Questions

### Must answer before SA launch

| Question | Owner |
|----------|-------|
| Vigour's legal status under POPIA — operator (processing on behalf of schools) or separate responsible party? This affects consent obligations, breach notification duties, and who bears primary POPIA liability. | Legal counsel |
| Legal opinion on whether POPIA Section 72 requires explicit consent for transient cross-region video processing. | Legal counsel |
| Legal opinion on whether prior authorisation (S57-58) is needed if LURITS numbers are used for cross-system matching. | Legal counsel |

### Must answer before UK/EU deployment

| Question | Owner |
|----------|-------|
| ~~Whether fitness performance scores constitute health data under GDPR Article 9 (special category).~~ **Answered — see [gdpr-article9-fitness-scores.md](./gdpr-article9-fitness-scores.md).** Fitness scores will be treated as Article 9 health data. ICO explicitly lists "athletic performance"; CJEU Lindenapotheke (2024) confirms broad interpretation. | Research complete |
| ~~UK AADC applicability and specific requirements for Vigour's use case.~~ **Answered — see [uk-aadc-requirements.md](./uk-aadc-requirements.md).** Vigour is in scope as an edtech provider. Full 15-standard assessment completed. | Research complete |
| Whether Vigour's norm comparison constitutes profiling that can be justified as essential to the core service — requires DPIA analysis. | DPIA / Legal counsel |
| Whether pose estimation / skeletal keypoints constitute biometric data under UK/EU law. Architecture already treats it as potentially biometric, but classification affects consent requirements and DPIA scope. | Legal counsel |
| Whether UK UPN (Unique Pupil Number) has similar sensitivity or restrictions to SA ID numbers. | Legal counsel |

### Informative but not blocking

| Question | Owner |
|----------|-------|
| Whether GCP will offer GPU VMs in `africa-south1` — would eliminate cross-region transfer but not blocking. | GCP account team |
| Cost modelling for multi-region deployment when international expansion begins. | Architecture |
| Whether pose estimation will be classified as biometric by the SA Information Regulator — architecture already treats it as potentially biometric. | Legal counsel |
| Other territory-specific compliance questions (US BIPA/COPPA/FERPA structuring, India DPDP, etc.) — deferred until those territories are in active planning. | Legal counsel |

---

## 13. Supporting Research

| Document | Coverage |
|----------|----------|
| [POPIA Student Identity](./popia-student-identity.md) | SA ID number storage under POPIA, LURITS as alternative identifier, consent requirements for children's data, prior authorisation obligations, breach implications, and a recommendation for LURITS-first with optional SA ID. |
| [Data Classification and Regulatory Landscape](./data-classification-and-regulation.md) | Classification of every data type Vigour handles (video, biometric-adjacent, identity, metrics, consent, institutional, operational, aggregated), regulatory analysis across ten jurisdictions, risk heat map, the "video problem" (when video becomes biometric data), and face detection vs recognition distinctions. |
| [Modular Data Architecture](./modular-data-architecture.md) | Five-layer architecture (ephemeral processing, anonymised core, identity module, consent module, reporting), country module design with SA/UK/US comparison, video retention strategies, ephemeral cross-region GPU processing pattern, cross-border data flow scenarios, progressive implementation roadmap, and schema build plan from the current POC. |
| [GDPR Article 9: Fitness Scores as Health Data](./gdpr-article9-fitness-scores.md) | GDPR Article 9 analysis of fitness performance scores as health data — legal definitions (Article 4(15), Recital 35), ICO "athletic performance" guidance, CJEU Lindenapotheke ruling (C-21/23, 2024), Article 29 Working Party framework, implications for consent and DPIA. |
| [UK AADC Requirements](./uk-aadc-requirements.md) | UK Age Appropriate Design Code requirements for Vigour — applicability analysis, assessment of all 15 standards, high privacy defaults, profiling analysis, age-banded transparency, DPIA requirements, enforcement examples, Phase 2 checklist, and Phase 1 architecture implications. |

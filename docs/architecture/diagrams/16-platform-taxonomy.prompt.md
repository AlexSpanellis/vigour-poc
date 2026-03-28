# 16 - Platform Taxonomy

**Tool**: `gemini --yolo "/diagram '...'"`
**Generated**: 2026-03-24

## Prompt

```
Vigour Platform Taxonomy — Term Reference Card.

A single-page visual glossary that defines every key term in the Vigour platform. Card-based grid layout, grouped by category. Each term is a card with: Term name (bold), one-line definition, key attributes, and relates-to pointers. Consistent color per category. Readable at a glance.

PEOPLE (purple cards):
- Student: A child at a school. NOT a system user — has no login. A data record. Defined as UUID + age_band + gender_category in core_data schema, with PII (name, DOB, external identifiers) in identity schema. Keeps the same UUID forever, even across school transfers.
- Teacher: A school staff member who runs fitness test sessions. Logs in via the Teacher App (Expo / React Native). Scoped to their own classes only. Creates sessions, records video, approves results.
- Coach: A school staff member with read-only access to all classes in their school. Logs in via Coach Web (React SPA). Views dashboards, leaderboards, trends. Cannot approve or modify results.
- School Head: Principal or head of school. Full authority over their school — all classes, all results, all staff. Logs in via School Head Web (React SPA). Can approve results, manage teachers, view school-wide dashboards.
- Parent/Guardian: A student's parent or legal guardian. Authenticated user (ZITADEL, magic link). Can view their own child's results gated by REPORTING consent. Logs in via Parent App (Expo / React Native).
- Super Admin: Vigour platform operator. Cross-school access. Onboards schools, manages users, handles transfers. Uses Admin UI (React SPA).
- Developer (proposed): Internal Vigour team member. Read-only access across all schools for debugging and support. No write permissions.

ORGANISATION (green cards):
- Platform: The Vigour system as a whole. Top-level entity in authorization. One platform: "vigour".
- School: A registered educational institution on the platform. Has staff, classes, and students. Each school is a separate ZITADEL organization for authentication isolation.
- Class: A group of students within a school, assigned to a grade and a teacher. e.g. "Grade 6A". A teacher can have multiple classes. A student belongs to one class.
- Grade: The school year level. Configurable per school. Classes are grouped by grade. Not a separate entity in the database — it is an attribute of Class and Student.

TESTING (blue cards):
- Test Type: One of five fitness assessments: Explosiveness (Vertical Jump), Speed (5m Sprint), Fitness (Shuttle Sprints), Agility (Cone Drill), Balance (Single-Leg Hold). Each test has specific CV pipeline requirements.
- Session (TestSession): One class doing one test type. e.g. "Gr 6A — Vertical Jump". Created by a teacher. Contains all bib assignments for the class. Progresses through states: draft → ready → recording → recorded → uploading → queued → processing → review → complete (or failed).
- Run: A batch of students within a session who perform the test together in one video recording. A session has multiple runs if the class is larger than the configured batch size (e.g. max 8 students per run). Runs are recorded sequentially. Each run produces one Clip.
- Clip: The video file recorded during one run. Has its own pipeline job. Linked to a session. Contains footage of a subset of the class performing the test. Stored locally on device until uploaded to cloud (GCS).
- Bib: A numbered vest (1-30) worn by a student during testing. The CV pipeline uses bib numbers to identify which student is which in the video.
- Bib Assignment: The mapping of bib numbers to students for a session. Assigned once at session setup, before any recording. Persists across all runs in the session. Can be manual, auto-assigned, or reused from a previous session.

RESULTS (orange cards):
- Result: A single measurement extracted by the CV pipeline from a clip. e.g. "Liam, bib #01, 42cm vertical jump". Linked to both a clip (source) and a session. Has a confidence score (high/low/unresolved). Must be approved by the teacher before it counts.
- Test Results: The raw measurements from each fitness test (e.g. 42cm vertical jump, 1.12s sprint). Stored per student per session. Used for trend analysis and reporting.

PIPELINE (red cards):
- Pipeline: The CV processing system that turns video into results. Stages: 0. Metadata Strip → 1. Ingest → 2. Detect → 3. Track → 4. Pose → 5. OCR → 6. Calibrate → 7. Extract → 8. Output. Stage 0 strips all metadata (GPS, timestamps) before any processing. Each clip gets its own pipeline job.
- Pipeline Job: A single processing task for one clip. Has a job_id. Runs asynchronously on GPU workers. Reports progress through the stages.
- Confidence Score: The pipeline's assessment of how reliable a result is. High = bib clearly read, student clearly tracked. Low = possible misread or tracking loss. Unresolved = bib could not be read at all.

DATA (cyan cards):
- Three schemas: core_data (UUIDs, non-sensitive attributes like age_band, gender_category), identity (PII — names, DOB, external identifiers), consent (consent records, jurisdiction config, audit logs)
- External Identifiers: LURITS (South Africa Learner Unit Record), UPN (UK Unique Pupil Number). Stored in identity.ExternalIdentifier. Persist across school transfers.
- ConsentRecord: Record of consent granted for a student, stored in consent schema. Links student UUID, consent type, grantor, timestamp.
- JurisdictionConfig: Per-jurisdiction consent rules (e.g. SA POPIA, UK GDPR). Stored in consent schema. Determines what consent types are required.
- AuditLog: Immutable log of all consent changes. Stored in consent schema.
- Data Residency: All data stored in africa-south1 (Google Cloud, Johannesburg).

CONFIGURATION (grey cards):
- max_students_per_run: Configurable limit on how many students can be in one run/clip. Default: 8 (based on tested tracking capacity). Determines how many runs a session needs.
- Bib Range: 1-30. The set of available bib numbers. Physical constraint based on school bib sets.

AUTHORIZATION (teal cards):
- OpenFGA: The relationship-based access control system. Stores who-can-do-what-to-which-resource as relationship tuples. Checked on every API request. Answers: "can this user access this resource?"
- ZITADEL: The identity provider. Handles authentication (login, magic links, JWT tokens). Each school is a separate ZITADEL organization.
- Consent Module: Works alongside OpenFGA and ZITADEL. Gates data use based on consent records. Answers: "is this data use permitted?" Both OpenFGA and Consent Module must pass.
- Tuple: A single relationship fact in OpenFGA. Format: "user:X is role of resource:Y". e.g. "user:teacher-uuid is teacher of school:oakwood".

CLIENT APPS (indigo cards):
- Mobile apps built with Expo / React Native, web apps built with React SPA
- Teacher App (Expo / React Native): session recording, result approval
- Coach Web (React SPA): dashboards, read-only views
- School Head Web (React SPA): school management, approvals
- Parent App (Expo / React Native): child result viewing
- Admin UI (React SPA): platform administration

Visual Style: Card-based grid layout, 3-4 columns. Each card: colored header bar (category color), term in bold, definition below, small icons for key attributes. Relationship lines between cards where terms reference each other (light grey). White background, clean sans-serif font. Title: "Vigour Platform — Taxonomy and Glossary". Subtitle: "Quick reference for all platform terminology". Footer: "v1.1 — March 2026".
```

## Regenerate

```bash
cd docs/architecture/diagrams
GEMINI_API_KEY="$NANOBANANA_GEMINI_API_KEY" gemini --yolo "/diagram 'Vigour Platform Taxonomy — Term Reference Card.

A single-page visual glossary that defines every key term in the Vigour platform. Card-based grid layout, grouped by category. Each term is a card with: Term name (bold), one-line definition, key attributes, and relates-to pointers. Consistent color per category. Readable at a glance.

PEOPLE (purple cards):
- Student: A child at a school. NOT a system user — has no login. A data record. Defined as UUID + age_band + gender_category in core_data schema, with PII (name, DOB, external identifiers) in identity schema. Keeps the same UUID forever, even across school transfers.
- Teacher: A school staff member who runs fitness test sessions. Logs in via the Teacher App (Expo / React Native). Scoped to their own classes only. Creates sessions, records video, approves results.
- Coach: A school staff member with read-only access to all classes in their school. Logs in via Coach Web (React SPA). Views dashboards, leaderboards, trends. Cannot approve or modify results.
- School Head: Principal or head of school. Full authority over their school — all classes, all results, all staff. Logs in via School Head Web (React SPA). Can approve results, manage teachers, view school-wide dashboards.
- Parent/Guardian: A student parent or legal guardian. Authenticated user (ZITADEL, magic link). Can view their own child results gated by REPORTING consent. Logs in via Parent App (Expo / React Native).
- Super Admin: Vigour platform operator. Cross-school access. Onboards schools, manages users, handles transfers. Uses Admin UI (React SPA).
- Developer (proposed): Internal Vigour team member. Read-only access across all schools for debugging and support. No write permissions.

ORGANISATION (green cards):
- Platform: The Vigour system as a whole. Top-level entity in authorization. One platform: vigour.
- School: A registered educational institution on the platform. Has staff, classes, and students. Each school is a separate ZITADEL organization for authentication isolation.
- Class: A group of students within a school, assigned to a grade and a teacher. e.g. Grade 6A. A teacher can have multiple classes. A student belongs to one class.
- Grade: The school year level. Configurable per school. Classes are grouped by grade. Not a separate entity in the database — it is an attribute of Class and Student.

TESTING (blue cards):
- Test Type: One of five fitness assessments: Explosiveness (Vertical Jump), Speed (5m Sprint), Fitness (Shuttle Sprints), Agility (Cone Drill), Balance (Single-Leg Hold). Each test has specific CV pipeline requirements.
- Session (TestSession): One class doing one test type. Created by a teacher. Contains all bib assignments. Progresses through states: draft → ready → recording → recorded → uploading → queued → processing → review → complete (or failed).
- Run: A batch of students within a session who perform the test together in one video recording. Max 8 students per run. Runs are recorded sequentially. Each run produces one Clip.
- Clip: The video file recorded during one run. Has its own pipeline job. Linked to a session. Stored locally on device until uploaded to cloud (GCS).
- Bib: A numbered vest (1-30) worn by a student during testing. The CV pipeline uses bib numbers to identify which student is which in the video.
- Bib Assignment: The mapping of bib numbers to students for a session. Assigned once at session setup. Persists across all runs. Can be manual, auto-assigned, or reused from a previous session.

RESULTS (orange cards):
- Result: A single measurement extracted by the CV pipeline from a clip. Has a confidence score (high/low/unresolved). Must be approved by the teacher before it counts.
- Test Results: The raw measurements from each fitness test. Stored per student per session. Used for trend analysis and reporting.

PIPELINE (red cards):
- Pipeline: The CV processing system that turns video into results. Stages: 0. Metadata Strip → 1. Ingest → 2. Detect → 3. Track → 4. Pose → 5. OCR → 6. Calibrate → 7. Extract → 8. Output. Stage 0 strips all metadata (GPS, timestamps) before any processing. Each clip gets its own pipeline job.
- Pipeline Job: A single processing task for one clip. Has a job_id. Runs asynchronously on GPU workers. Reports progress through the stages.
- Confidence Score: The pipeline assessment of how reliable a result is. High = bib clearly read, student clearly tracked. Low = possible misread or tracking loss. Unresolved = bib could not be read at all.

DATA (cyan cards):
- Three schemas: core_data (UUIDs, non-sensitive attributes like age_band, gender_category), identity (PII — names, DOB, external identifiers), consent (consent records, jurisdiction config, audit logs)
- External Identifiers: LURITS (South Africa Learner Unit Record), UPN (UK Unique Pupil Number). Stored in identity.ExternalIdentifier. Persist across school transfers.
- ConsentRecord: Record of consent granted for a student, stored in consent schema. Links student UUID, consent type, grantor, timestamp.
- JurisdictionConfig: Per-jurisdiction consent rules (e.g. SA POPIA, UK GDPR). Stored in consent schema.
- AuditLog: Immutable log of all consent changes. Stored in consent schema.
- Data Residency: All data stored in africa-south1 (Google Cloud, Johannesburg).

CONFIGURATION (grey cards):
- max_students_per_run: Configurable limit on how many students can be in one run/clip. Default: 8. Determines how many runs a session needs.
- Bib Range: 1-30. The set of available bib numbers. Physical constraint based on school bib sets.

AUTHORIZATION (teal cards):
- OpenFGA: The relationship-based access control system. Stores who-can-do-what-to-which-resource as relationship tuples. Checked on every API request. Answers: can this user access this resource?
- ZITADEL: The identity provider. Handles authentication (login, magic links, JWT tokens). Each school is a separate ZITADEL organization.
- Consent Module: Works alongside OpenFGA and ZITADEL. Gates data use based on consent records. Answers: is this data use permitted? Both OpenFGA and Consent Module must pass.
- Tuple: A single relationship fact in OpenFGA. Format: user:X is role of resource:Y.

CLIENT APPS (indigo cards):
- Mobile apps built with Expo / React Native, web apps built with React SPA
- Teacher App (Expo / React Native): session recording, result approval
- Coach Web (React SPA): dashboards, read-only views
- School Head Web (React SPA): school management, approvals
- Parent App (Expo / React Native): child result viewing
- Admin UI (React SPA): platform administration

Visual Style: Card-based grid layout, 3-4 columns. Each card: colored header bar (category color), term in bold, definition below. Relationship lines between cards where terms reference each other (light grey). White background, clean sans-serif font. Title: Vigour Platform — Taxonomy and Glossary. Subtitle: Quick reference for all platform terminology. Footer: v1.1 — March 2026.'"
```

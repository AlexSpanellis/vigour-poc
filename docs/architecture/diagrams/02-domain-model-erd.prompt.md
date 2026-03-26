# 02 - Domain Model ERD

**Tool**: `gemini --yolo "/diagram '...'"`
**Generated**: 2026-03-24

## Prompt

```
Entity Relationship Diagram (ERD) for Vigour Platform domain model with 3 schemas, color-coded by schema boundary:

LAYER 1 - core_data schema (no PII, color: blue):
- School (id, contract_status, jurisdiction_id)
- Student (id, age_band, gender_category, school_id)
- User (id, role: teacher/coach/school_head/parent/super_admin, school_id, zitadel_id)
- Class (id, name, grade, school_id, teacher_id, academic_year)
- ClassStudent (class_id, student_id) - junction table
- TestSession (id, school_id, class_id, teacher_id, test_type, session_date, status)
- BibAssignment (id, session_id, student_id, bib_number)
- Clip (id, session_id, job_id, video_path, status, retention_state, pipeline_version)
- Result (id, clip_id, student_id, bib_assignment_id, bib_number, test_type, metric_value, metric_unit, confidence_score, approved)
- JurisdictionConfig (id, code, name, consent_age_threshold, video_hot_storage_days)

LAYER 2 - identity schema (PII, encrypted, color: orange):
- StudentIdentity (id, internal_id→Student, first_name, last_name, date_of_birth, grade, gender)
- ExternalIdentifier (id, internal_id→Student, id_type: LURITS/UPN, id_value)
- SchoolIdentity (id, internal_id→School, name, district, province)
- UserIdentity (id, internal_id→User, email, name)

LAYER 3 - consent schema (color: green):
- ConsentRecord (id, student_id, consenting_party, consent_type, consent_status, granted_at, consent_method)
- AuditLog (id, event_timestamp, actor, action, target_student_id, details)

Relationships: School has many Students, Users, Classes, TestSessions. Class has many ClassStudents. Student has many ClassStudents. User teaches Classes. TestSession belongs to Class and User. TestSession has many BibAssignments and Clips. Student has many BibAssignments. Clip has many Results. Student has many Results. StudentIdentity links to Student via internal_id. ExternalIdentifier links to Student via internal_id. SchoolIdentity links to School via internal_id. UserIdentity links to User via internal_id. ConsentRecord links to Student. AuditLog references Student. JurisdictionConfig links to School.

Show schema boundaries with color-coded regions. Clean modern ERD style with entity boxes showing primary keys and foreign keys.
```

## Regenerate

```bash
cd docs/architecture/diagrams
GEMINI_API_KEY="$NANOBANANA_GEMINI_API_KEY" gemini --yolo "/diagram 'Entity Relationship Diagram (ERD) for Vigour Platform domain model with 3 schemas, color-coded by schema boundary:

LAYER 1 - core_data schema (no PII, color: blue):
- School (id, contract_status, jurisdiction_id)
- Student (id, age_band, gender_category, school_id)
- User (id, role: teacher/coach/school_head/parent/super_admin, school_id, zitadel_id)
- Class (id, name, grade, school_id, teacher_id, academic_year)
- ClassStudent (class_id, student_id) - junction table
- TestSession (id, school_id, class_id, teacher_id, test_type, session_date, status)
- BibAssignment (id, session_id, student_id, bib_number)
- Clip (id, session_id, job_id, video_path, status, retention_state, pipeline_version)
- Result (id, clip_id, student_id, bib_assignment_id, bib_number, test_type, metric_value, metric_unit, confidence_score, approved)
- JurisdictionConfig (id, code, name, consent_age_threshold, video_hot_storage_days)

LAYER 2 - identity schema (PII, encrypted, color: orange):
- StudentIdentity (id, internal_id→Student, first_name, last_name, date_of_birth, grade, gender)
- ExternalIdentifier (id, internal_id→Student, id_type: LURITS/UPN, id_value)
- SchoolIdentity (id, internal_id→School, name, district, province)
- UserIdentity (id, internal_id→User, email, name)

LAYER 3 - consent schema (color: green):
- ConsentRecord (id, student_id, consenting_party, consent_type, consent_status, granted_at, consent_method)
- AuditLog (id, event_timestamp, actor, action, target_student_id, details)

Relationships: School has many Students, Users, Classes, TestSessions. Class has many ClassStudents. Student has many ClassStudents. User teaches Classes. TestSession belongs to Class and User. TestSession has many BibAssignments and Clips. Student has many BibAssignments. Clip has many Results. Student has many Results. StudentIdentity links to Student via internal_id. ExternalIdentifier links to Student via internal_id. SchoolIdentity links to School via internal_id. UserIdentity links to User via internal_id. ConsentRecord links to Student. AuditLog references Student. JurisdictionConfig links to School.

Show schema boundaries with color-coded regions. Clean modern ERD style with entity boxes showing primary keys and foreign keys.'"
```

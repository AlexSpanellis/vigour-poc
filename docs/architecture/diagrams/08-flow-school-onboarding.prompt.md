# 08 - School Onboarding Flow

**Tool**: `gemini --yolo "/diagram '...'"`
**Generated**: 2026-03-24

## Prompt

```
School Onboarding Flow. Admin-driven process bringing a new school onto the Vigour platform. Covers school creation, staff provisioning, student enrollment, consent collection, and parent onboarding.

Flow (top to bottom):
1. Contract signed between school and Vigour
2. Super admin logs into Admin UI
3. Creates ZITADEL Organization for the school
4. Creates School record: core_data.School (UUID, contract_status) + identity schema (name, district, province)
5. OpenFGA tuples written: school linked to platform
6. Adds school head (name, email, role: school_head) → User created in ZITADEL org, OpenFGA tuple written
7. Invite email sent to school head with magic link
8. Decision: How are staff added? Manual (one by one) OR Bulk CSV import
9. CSV path: CSV prepared (name, email, role) → Upload → Decision: Valid? If errors (invalid email, duplicates, unknown role) → validation report, fix and re-upload. If valid → bulk create
10. Bulk creation: ZITADEL users created, OpenFGA tuples per user, invite emails queued
11. All staff provisioned with invite emails sent
12. School head logs in (first-time login flow) → Creates classes (class name, grade, assign teacher) → OpenFGA tuples for class
13. Enrol students: Manual entry OR Bulk CSV. Each student creates two records: core_data.Student (UUID, age_band, gender_category) and identity.StudentIdentity (PII: name, DOB, external identifiers)
14. Student CSV validation (missing fields, invalid values) → fix and retry
15. Students created as data records (no user accounts), OpenFGA tuples for class enrollment
16. Consent form distribution: school distributes consent forms to parents/guardians for each enrolled student
17. Parent account creation: parent/guardian added to ZITADEL, magic link sent for first login
18. Consent collection — Decision: Digital or Paper? Digital path: parent logs into app and submits consent per student. Paper path: admin enters paper consent manually via Admin UI
19. consent.ConsentRecord created for each student (linked by student UUID, records consent type, timestamp, grantor)
20. Decision: More classes? If yes, repeat from step 12. If no → School fully onboarded
21. Checklist: School created ✓, Staff provisioned ✓, Classes created ✓, Students enrolled ✓, Consent collected ✓, Parents onboarded ✓
22. Testing can begin ONLY for students with valid ConsentRecords
23. Teachers can now create first test sessions for consented students

Actors: Super Admin, School Head, Teacher, Parent/Guardian.
Professional clean style, clear separation between admin actions, parent actions, and system responses.
```

## Regenerate

```bash
cd docs/architecture/diagrams
GEMINI_API_KEY="$NANOBANANA_GEMINI_API_KEY" gemini --yolo "/diagram 'School Onboarding Flow. Admin-driven process bringing a new school onto the Vigour platform. Covers school creation, staff provisioning, student enrollment, consent collection, and parent onboarding.

Flow (top to bottom):
1. Contract signed between school and Vigour
2. Super admin logs into Admin UI
3. Creates ZITADEL Organization for the school
4. Creates School record: core_data.School (UUID, contract_status) + identity schema (name, district, province)
5. OpenFGA tuples written: school linked to platform
6. Adds school head (name, email, role: school_head) → User created in ZITADEL org, OpenFGA tuple written
7. Invite email sent to school head with magic link
8. Decision: How are staff added? Manual (one by one) OR Bulk CSV import
9. CSV path: CSV prepared (name, email, role) → Upload → Decision: Valid? If errors (invalid email, duplicates, unknown role) → validation report, fix and re-upload. If valid → bulk create
10. Bulk creation: ZITADEL users created, OpenFGA tuples per user, invite emails queued
11. All staff provisioned with invite emails sent
12. School head logs in (first-time login flow) → Creates classes (class name, grade, assign teacher) → OpenFGA tuples for class
13. Enrol students: Manual entry OR Bulk CSV. Each student creates two records: core_data.Student (UUID, age_band, gender_category) and identity.StudentIdentity (PII: name, DOB, external identifiers)
14. Student CSV validation (missing fields, invalid values) → fix and retry
15. Students created as data records (no user accounts), OpenFGA tuples for class enrollment
16. Consent form distribution: school distributes consent forms to parents/guardians for each enrolled student
17. Parent account creation: parent/guardian added to ZITADEL, magic link sent for first login
18. Consent collection — Decision: Digital or Paper? Digital path: parent logs into app and submits consent per student. Paper path: admin enters paper consent manually via Admin UI
19. consent.ConsentRecord created for each student (linked by student UUID, records consent type, timestamp, grantor)
20. Decision: More classes? If yes, repeat from step 12. If no → School fully onboarded
21. Checklist: School created, Staff provisioned, Classes created, Students enrolled, Consent collected, Parents onboarded
22. Testing can begin ONLY for students with valid ConsentRecords
23. Teachers can now create first test sessions for consented students

Actors: Super Admin, School Head, Teacher, Parent/Guardian.
Professional clean style, clear separation between admin actions, parent actions, and system responses.'"
```

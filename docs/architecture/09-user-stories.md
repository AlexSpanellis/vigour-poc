# User Stories

## Overview

This document defines user stories for all five roles in the Vigour platform. Stories are grouped by workflow theme and marked as **MVP** or **Future** to indicate release phase. The Teacher role includes a detailed primary workflow mapped to the session lifecycle states.

Stories follow the standard format: _"As a [role], I want to [action] so that [benefit]."_

---

## 1. Teacher

### Persona

Mrs. van Wyk is a Grade 6 PE teacher at Oakwood Primary in the Western Cape. She runs fitness testing sessions for her classes of ~28 students each term. She works on a field with her phone, often with limited connectivity. She cares about running sessions quickly with minimal friction, getting accurate results matched to the right students, and being able to show parents how their children are progressing. She is not technical but is comfortable with a mobile app.

---

### Primary Workflow: Session Lifecycle (Step-by-Step)

This maps directly to the `TestSession.status` state machine: `draft` > `ready` > `recording` > `recorded` > `uploading` > `queued` > `processing` > `review` > `complete`.

#### Step 1 -- Session Setup (`draft`)

The teacher opens the Teacher App and creates a new test session. She selects the grade, then the specific class (e.g. "6A"), then the test type (Vertical Jump, 5m Sprint, Shuttle Run, Cone Drill, or Single-Leg Balance). The app creates a `TestSession` record in `draft` state. This step works offline using cached class lists.

#### Step 2 -- Bib Assignment (`draft` > `ready`)

The teacher assigns numbered bibs (1-30) to each student in the class. She taps each student name and assigns a bib number -- for example, Bib 4 to Liam van der Berg, Bib 7 to Amara Dlamini. This creates `BibAssignment` records that link session + student + bib number. This is the critical bridge between the CV pipeline (which only sees bib numbers) and actual student identities. Once all bibs are assigned, the session transitions to `ready`. This step works offline.

#### Step 3 -- Pre-flight Check (`ready`)

The teacher opens the camera preview. The app runs CV pre-checks: verifies cones are visible, students are in frame, bib numbers are readable, and lighting is adequate. The teacher adjusts the setup until all checks pass.

#### Step 4 -- Recording (`recording` > `recorded`)

The teacher taps "Record" to begin capturing video at 60fps/4K. The live overlay shows bib detection count and tracking indicators so she can see the pipeline will have what it needs. When the test is done, she stops recording. The session transitions to `recorded`.

#### Step 5 -- Clip Review (`recorded`)

The teacher plays back the recorded clip with a CV quality summary. She decides to either re-record (back to step 4) or accept the clip and proceed to upload.

#### Step 6 -- Upload (`uploading` > `queued`)

The teacher taps "Upload". The app calls the API to create a Clip record and receives a `clip_id` plus a signed GCS upload URL. The app uploads the video directly to cloud storage (no bytes through the API). A progress bar shows upload status. Once complete, the app confirms the upload, which triggers pipeline job submission. The session transitions through `uploading` to `queued`. If the teacher is offline, the upload is queued locally and executes when connectivity returns.

#### Step 7 -- Pipeline Processing (`queued` > `processing`)

The teacher sees a stage-by-stage progress indicator as the CV pipeline processes the video through 8 stages (Ingest, Detect, Track, Pose, OCR, Calibrate, Extract, Output). The app polls for status updates. If the pipeline fails, the teacher can retry or go back and re-record. On success, the session transitions to `review`.

#### Step 8 -- Results Processing (`review`)

The teacher opens the Results Processing screen. She sees each student's result matched via the bib assignment, with confidence indicators:
- **Green check** -- high-confidence match, likely correct
- **Warning triangle** -- low confidence, needs review
- **Red X** -- bib unresolved or rejected

She can approve individual results, reject and reassign mismatched bibs (e.g. OCR misread "7" as "1"), or use the "Approve All High Confidence" bulk action for results above the confidence threshold. She then taps "Commit Results to Profiles" to finalise.

#### Step 9 -- Session Complete (`complete`)

The session is complete. The teacher sees a ranked results list showing each student's measured value. Results are permanently linked to student profiles.

---

### Session Management

| ID | Story | Priority |
|----|-------|----------|
| T-01 | As a teacher, I want to create a test session by selecting a class and test type so that I can begin preparing for a fitness assessment. | MVP |
| T-02 | As a teacher, I want to set up sessions while offline so that I can prepare on the field without needing a data connection. | MVP |
| T-03 | As a teacher, I want to assign bib numbers to students for a session so that the CV pipeline can match detected bibs to actual student identities. | MVP |
| T-04 | As a teacher, I want to see a list of my upcoming and past sessions so that I can manage my testing schedule. | MVP |
| T-05 | As a teacher, I want to resume an in-progress session if the app is interrupted so that I do not lose my work. | MVP |
| T-06 | As a teacher, I want to re-use a previous session's bib assignments as a template so that I do not have to re-assign bibs every time I test the same class. | Future |

### Recording and Upload

| ID | Story | Priority |
|----|-------|----------|
| T-07 | As a teacher, I want to run a pre-flight camera check before recording so that I know the setup (cones, bibs, lighting, framing) will produce usable video. | MVP |
| T-08 | As a teacher, I want to record a test session on my phone at high quality so that the CV pipeline has sufficient detail to extract results. | MVP |
| T-09 | As a teacher, I want to review the recorded clip before uploading so that I can re-record if the quality is poor. | MVP |
| T-10 | As a teacher, I want to upload the video directly to cloud storage via a signed URL so that the upload is fast and does not pass through the API server. | MVP |
| T-11 | As a teacher, I want to see upload progress so that I know whether to wait or move on to the next activity. | MVP |
| T-12 | As a teacher, I want uploads to queue locally when I am offline and resume automatically when connectivity returns so that I do not lose recorded sessions. | MVP |
| T-13 | As a teacher, I want to see stage-by-stage pipeline progress (e.g. "3/8 Track") so that I know the system is working and roughly how long to wait. | MVP |
| T-14 | As a teacher, I want to receive a notification when pipeline processing is complete so that I can review results without having to check repeatedly. | Future |

### Results Review and Approval

| ID | Story | Priority |
|----|-------|----------|
| T-15 | As a teacher, I want to see all pipeline results matched to student names (via bib assignments) with confidence indicators so that I can verify accuracy before committing. | MVP |
| T-16 | As a teacher, I want to approve individual results so that I can confirm each student's score is correct. | MVP |
| T-17 | As a teacher, I want to bulk-approve all high-confidence results (confidence > 0.8) so that I can save time when most matches are correct. | MVP |
| T-18 | As a teacher, I want to manually reassign a result to a different student when a bib was misread by OCR so that the correct student gets credit. | MVP |
| T-19 | As a teacher, I want to see flagged results (unresolved bibs, low confidence, partial occlusion) highlighted for attention so that I focus my review effort where it matters. | MVP |
| T-20 | As a teacher, I want to reject a result that is clearly erroneous so that bad data does not pollute a student's profile. | MVP |
| T-21 | As a teacher, I want to commit approved results to student profiles in one action so that results are visible to stakeholders. | MVP |
| T-22 | As a teacher, I want to watch the annotated video (with tracking overlays) for a completed session so that I can visually verify what the pipeline detected. | Future |

### Student Management

| ID | Story | Priority |
|----|-------|----------|
| T-23 | As a teacher, I want to enrol new students in my class so that they can participate in fitness testing. | MVP |
| T-24 | As a teacher, I want to view a student's full fitness profile (per-test results, trends, attendance) so that I can track their progress over time. | MVP |
| T-25 | As a teacher, I want to see a student's change vs last term so that I can identify who is improving and who may need extra support. | MVP |
| T-26 | As a teacher, I want to update student details (name, grade, class assignment) so that records stay current. | MVP |

### Results Viewing

| ID | Story | Priority |
|----|-------|----------|
| T-27 | As a teacher, I want to view session results as a ranked list so that I can see how students performed. | MVP |

### Authentication

| ID | Story | Priority |
|----|-------|----------|
| T-31 | As a teacher, I want to log in via a magic link sent to my email so that I do not need to remember a password. | MVP |
| T-32 | As a teacher, I want to log in via my school's Google or Microsoft account (SSO) so that I can use my existing credentials. | MVP |
| T-33 | As a teacher, I want to stay logged in between app sessions so that I do not have to re-authenticate every time I open the app. | MVP |

---

## 2. Coach

### Persona

Coach Dlamini oversees fitness training at Oakwood Primary. He does not run test sessions himself -- that is the teacher's job. He reviews results on his laptop to track class performance, identify students who need targeted training, and monitor improvement over time. He exports data for his own training plans.

---

### Performance Review

| ID | Story | Priority |
|----|-------|----------|
| C-01 | As a coach, I want to view a class leaderboard showing each student's name, test results, attendance, and change vs last term so that I can assess class performance at a glance. | MVP |
| C-02 | As a coach, I want to sort and filter the leaderboard by test type (Vertical Jump, Sprint, Shuttle, Cone Drill, Balance) so that I can focus on specific fitness domains. | MVP |
| C-03 | As a coach, I want to view an individual student's per-test breakdown with historical trends across terms so that I can identify their strengths and weaknesses. | MVP |
| C-04 | As a coach, I want to see which students have improved and which have declined since the last testing session so that I can adjust my training focus. | MVP |
| C-05 | As a coach, I want to compare performance across classes within the same grade so that I can identify class-level patterns. | Future |

### Participation Tracking

| ID | Story | Priority |
|----|-------|----------|
| C-06 | As a coach, I want to see attendance and completion rates per session so that I know which students are consistently missing tests. | MVP |
| C-07 | As a coach, I want to see a summary of how many students improved out of the total tested so that I can gauge the impact of training programmes. | MVP |

### Data Export

| ID | Story | Priority |
|----|-------|----------|
| C-09 | As a coach, I want to export class results as CSV so that I can analyse data in my own spreadsheet. | MVP |
| C-10 | As a coach, I want to view session history for a class so that I can see the progression of testing over the term. | MVP |

### Authentication

| ID | Story | Priority |
|----|-------|----------|
| C-11 | As a coach, I want to log in via my school credentials (magic link or SSO) so that I can access the Coach Web dashboard. | MVP |

---

## 3. School Head

### Persona

Principal Naidoo runs Oakwood Primary with 341 students across multiple grades. She needs a school-wide view of fitness outcomes for governance and parent communication. She does not look at individual sessions -- she wants high-level metrics: school score, participation rates, improvement trends, and which students are at risk. She also manages the teacher roster on the platform.

---

### School Overview

| ID | Story | Priority |
|----|-------|----------|
| SH-01 | As a school head, I want to see a school overview dashboard showing total students, performance summary, participation rate, improvement percentage, and at-risk count so that I can assess overall school fitness health. | MVP |
| SH-02 | As a school head, I want to see a grade-by-grade breakdown of test results and term-over-term change so that I can compare performance across grades. | MVP |
| SH-03 | As a school head, I want to see participation rates by grade so that I can identify grades with low engagement. | MVP |
| SH-04 | As a school head, I want to see average scores by test type (Explosiveness, Speed, Fitness, Agility, Balance) across all grades so that I can see where the school is strong and where it needs improvement. | MVP |

### At-Risk Monitoring

| ID | Story | Priority |
|----|-------|----------|
| SH-05 | As a school head, I want to see a list of students flagged as at-risk (declining test results over 2+ sessions) so that I can coordinate intervention with teachers and coaches. | MVP |
| SH-06 | As a school head, I want to drill into an at-risk student's profile to understand which test domains are declining so that I can provide targeted guidance to staff. | MVP |

### Data Viewing

| ID | Story | Priority |
|----|-------|----------|
| SH-08 | As a school head, I want to view term-over-term trend data so that I can track school fitness progress for governing body meetings. | Future |

### Staff and Student Administration

| ID | Story | Priority |
|----|-------|----------|
| SH-09 | As a school head, I want to view and manage teachers and coaches registered at my school so that I can control who has access to the platform. | MVP |
| SH-10 | As a school head, I want to add a new teacher or coach to my school so that they can begin using the platform. | MVP |
| SH-11 | As a school head, I want to deactivate a staff member who has left the school so that they lose access to school data. | MVP |
| SH-12 | As a school head, I want to manage class assignments (which teacher is responsible for which class) so that permissions are correct. | MVP |
| SH-13 | As a school head, I want to manage student enrolment (add, update, transfer out) so that the student roster stays accurate. | MVP |

### Authentication

| ID | Story | Priority |
|----|-------|----------|
| SH-14 | As a school head, I want to log in via magic link or school SSO so that I can access the School Head dashboard. | MVP |

---

## 4. Super Admin

### Persona

Sipho is a member of the Vigour platform operations team. He onboards new schools after contracts are signed, manages user accounts when school heads need help, monitors platform health, and handles edge cases like student transfers between schools. He operates via admin API routes and (eventually) an admin UI. There is no self-signup -- every school and user is provisioned through him.

---

### School Onboarding

| ID | Story | Priority |
|----|-------|----------|
| SA-01 | As a super admin, I want to create a new school record (name, district, province, contract status) so that a contracted school is provisioned on the platform. | MVP |
| SA-02 | As a super admin, I want to create a ZITADEL organization for the school so that its users are isolated in their own identity tenant. | MVP |
| SA-03 | As a super admin, I want to create the initial school head user account for a newly onboarded school so that the school head can log in and begin managing their school. | MVP |
| SA-04 | As a super admin, I want to set a school's contract status (active, suspended, expired) so that access is revoked when contracts lapse. | MVP |
| SA-05 | As a super admin, I want to view a list of all schools on the platform with their contract status and usage metrics so that I can manage the portfolio. | MVP |

### User Management

| ID | Story | Priority |
|----|-------|----------|
| SA-06 | As a super admin, I want to create, update, and deactivate user accounts at any school so that I can handle support requests from school heads. | MVP |
| SA-07 | As a super admin, I want to assign roles (teacher, coach, school_head) to users so that they have the correct permissions. | MVP |
| SA-08 | As a super admin, I want to reset a user's authentication (re-send magic link, reset SSO binding) so that locked-out users can regain access. | MVP |

### Student Transfers

| ID | Story | Priority |
|----|-------|----------|
| SA-09 | As a super admin, I want to transfer a student from one school to another so that the student's record moves with them while historical results remain intact. | MVP |
| SA-10 | As a super admin, I want the old school to lose access to a transferred student's data (via OpenFGA tuple deletion) and the new school to gain access so that data privacy is maintained. | MVP |

### Platform Operations

| ID | Story | Priority |
|----|-------|----------|
| SA-11 | As a super admin, I want to view pipeline job status and failure rates so that I can identify processing issues before schools report them. | MVP |
| SA-12 | As a super admin, I want to manage pipeline cache (view, clear per job, invalidate from a specific stage) so that I can resolve stuck or corrupted jobs. | MVP |
| SA-13 | As a super admin, I want to view system health across all services (Application API, Pipeline API, ZITADEL, OpenFGA, Redis, databases) so that I can monitor platform uptime. | MVP |
| SA-14 | As a super admin, I want to configure platform-level settings (confidence threshold for auto-approval, video retention policy) so that the platform behaviour can be tuned without code changes. | Future |
| SA-15 | As a super admin, I want to view an audit log of administrative actions (school creation, user management, student transfers) so that there is accountability for all platform changes. | Future |

### Authentication

| ID | Story | Priority |
|----|-------|----------|
| SA-16 | As a super admin, I want to log in via OIDC with elevated credentials so that platform administration is secured behind strong authentication. | MVP |

---

## 5. Student (Future Phase)

### Persona

Liam is a 12-year-old Grade 6 learner at Oakwood Primary. He just did fitness testing and wants to see how he performed. He cares about his overall score, where he ranks in class, and what he can do to improve. He uses the Learner App on his parents' phone. He sees his own data only -- he cannot see other students' individual results.

> **Note**: This role is blocked on the student authentication model decision (parent-managed accounts, school-issued codes, or parent email magic links). All stories below are **Future**.

---

### Personal Dashboard

| ID | Story | Priority |
|----|-------|----------|
| ST-01 | As a student, I want to see my overall test results so that I know where I stand. | Future |
| ST-02 | As a student, I want to see my score for each of the 5 fitness tests (Jump, Sprint, Shuttle, Cone Drill, Balance) so that I know my strengths and weaknesses. | Future |
| ST-03 | As a student, I want to see how my score changed vs last term (e.g. "+8 pts this term") so that I can see my improvement. | Future |
| ST-04 | As a student, I want to see how my results compare within my grade so that I understand how I compare to peers. | Future |

### Class Comparison

| ID | Story | Priority |
|----|-------|----------|
| ST-05 | As a student, I want to see an anonymised class board showing where I rank without revealing other students' names so that I feel motivated to improve. | Future |

### Improvement Guidance

| ID | Story | Priority |
|----|-------|----------|
| ST-06 | As a student, I want to see a recommendation highlighting my weakest test area (e.g. "Improve your Balance") so that I know what to focus on. | Future |
| ST-07 | As a student, I want to see exercise tips and activities for my weakest domain so that I have actionable guidance. | Future |

### Authentication

| ID | Story | Priority |
|----|-------|----------|
| ST-08 | As a student, I want to log in via a parent-approved method (magic link to parent email or school-issued code) so that my account is appropriately supervised. | Future |
| ST-09 | As a student, I want my data to be visible only to me (and my teachers/coaches/parents) so that my privacy is protected. | Future |

---

## Story Count Summary

| Role | MVP | Future | Total |
|------|-----|--------|-------|
| Teacher | 26 | 7 | 33 |
| Coach | 10 | 1 | 11 |
| School Head | 13 | 1 | 14 |
| Super Admin | 13 | 3 | 16 |
| Student | 0 | 9 | 9 |
| **Total** | **62** | **21** | **83** |

---

## Cross-Cutting Concerns (Applicable to All Roles)

These are not user stories per se, but non-functional requirements that apply across the platform.

- **POPIA Compliance**: All student data is PII for minors. Access is scoped by school via OpenFGA. No individual student data crosses the school boundary.
- **Offline Support (Teacher App)**: Session setup, bib assignment, and video recording work offline. Upload queues locally. Results review requires connectivity.
- **Signed URLs**: All video access uses time-limited signed GCS URLs. No public buckets.
- **Contract-Based Access**: No self-signup. Schools are provisioned by super admin after contract. Users are pre-approved per school.
- **Student Data Portability**: Results are linked to student UUID permanently. School transfers move the student record; historical results remain attached to identity.
- **Audit Trail**: All result approvals are tracked with `approved_by` (teacher user ID) and timestamp. Administrative actions should be logged.

# 11 - Student Transfer Between Schools

**Tool**: `gemini --yolo "/diagram '...'"`
**Generated**: 2026-03-24

## Prompt

```
Student Transfer Between Schools - User Flow diagram. Shows data changes across core_data, identity, consent, and OpenFGA layers.

Flow (top to bottom):
1. Student leaving School A (Oakwood Primary) for School B (Hilltop Academy)
2. Decision: Who initiates? School A head (via School Head Web → Admin → Students) OR Super admin (via Admin UI, search student)
3. Find student (e.g. Liam van der Berg) → Student Record showing: Grade 6, Class 6A, School Oakwood, Transfer Student button
4. Click Transfer Student → Transfer Dialog: search and select destination school, optionally select class at new school. Note: Historical results remain linked but not automatically visible.
5. Select Hilltop Academy, optionally class → Confirm dialog explaining: student moves, old school loses access, historical results stay with student but require explicit sharing, consent must be re-collected at new school
6. Decision: Cancel (back to record) or Confirm
7. Transfer executed (system actions):
   a. core_data.Student.school_id updated to new school
   b. identity.StudentIdentity and identity.ExternalIdentifier records updated by receiving school (external identifiers like LURITS/UPN persist across transfer)
   c. Old school OpenFGA tuples deleted (all class/school relationships)
   d. New school OpenFGA tuples written (new class/school relationships)
   e. All Result records remain on student UUID
8. Effect at old school (Oakwood): student disappears from roster, staff lose access, historical sessions show transferred marker, no data deleted
9. Effect at new school (Hilltop): student appears in class, teachers can include in new sessions, new results accumulate under same UUID
10. Consent re-collection required: new school must distribute consent forms and collect new ConsentRecords. Note: consent-authorization boundary — OpenFGA controls access, Consent Module gates data use. Both must pass.
11. Decision: Does new school need historical results? If no, done. If yes → super admin grants explicit sharing via OpenFGA tuple → Hilltop staff can view historical results (sharing is explicit, not automatic)
12. Transfer complete: UUID is the anchor, external identifiers (LURITS/UPN) persist, old results access-controlled, new consent collected, new results accumulate at new school

Two-school visual layout showing data flow between institutions, emphasis on UUID permanence and consent-authorization boundary.
```

## Regenerate

```bash
cd docs/architecture/diagrams
GEMINI_API_KEY="$NANOBANANA_GEMINI_API_KEY" gemini --yolo "/diagram 'Student Transfer Between Schools - User Flow diagram. Shows data changes across core_data, identity, consent, and OpenFGA layers.

Flow (top to bottom):
1. Student leaving School A (Oakwood Primary) for School B (Hilltop Academy)
2. Decision: Who initiates? School A head (via School Head Web → Admin → Students) OR Super admin (via Admin UI, search student)
3. Find student (e.g. Liam van der Berg) → Student Record showing: Grade 6, Class 6A, School Oakwood, Transfer Student button
4. Click Transfer Student → Transfer Dialog: search and select destination school, optionally select class at new school. Note: Historical results remain linked but not automatically visible.
5. Select Hilltop Academy, optionally class → Confirm dialog explaining: student moves, old school loses access, historical results stay with student but require explicit sharing, consent must be re-collected at new school
6. Decision: Cancel (back to record) or Confirm
7. Transfer executed (system actions):
   a. core_data.Student.school_id updated to new school
   b. identity.StudentIdentity and identity.ExternalIdentifier records updated by receiving school (external identifiers like LURITS/UPN persist across transfer)
   c. Old school OpenFGA tuples deleted (all class/school relationships)
   d. New school OpenFGA tuples written (new class/school relationships)
   e. All Result records remain on student UUID
8. Effect at old school (Oakwood): student disappears from roster, staff lose access, historical sessions show transferred marker, no data deleted
9. Effect at new school (Hilltop): student appears in class, teachers can include in new sessions, new results accumulate under same UUID
10. Consent re-collection required: new school must distribute consent forms and collect new ConsentRecords. Note: consent-authorization boundary — OpenFGA controls access, Consent Module gates data use. Both must pass.
11. Decision: Does new school need historical results? If no, done. If yes → super admin grants explicit sharing via OpenFGA tuple → Hilltop staff can view historical results (sharing is explicit, not automatic)
12. Transfer complete: UUID is the anchor, external identifiers (LURITS/UPN) persist, old results access-controlled, new consent collected, new results accumulate at new school

Two-school visual layout showing data flow between institutions, emphasis on UUID permanence and consent-authorization boundary.'"
```

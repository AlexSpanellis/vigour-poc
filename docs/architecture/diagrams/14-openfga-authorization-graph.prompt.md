# 14 - OpenFGA Authorization Graph

**Tool**: `gemini --yolo "/diagram '...'"`
**Generated**: 2026-03-24

## Prompt

```
OpenFGA Authorization Graph — Vigour Platform.

Visualize the OpenFGA relationship-based access control model for the Vigour fitness testing platform. Show how users relate to resources through typed relationships, and how permissions are derived by traversing the graph. Include the consent-authorization boundary: OpenFGA controls access (who CAN see), Consent Module gates data use (who MAY see). Both must pass.

Layout: Clean, hierarchical graph flowing top-to-bottom. Use distinct colors for each entity type. Show relationship edges with labeled arrows. Group by scope: Platform → School → Class → Session → Results.

Entity Types (nodes):
1. Platform: vigour (top level, dark blue) — Relations: super_admin, developer (proposed)
2. School: Oakwood Primary (green) — Relations: school_head, teacher, coach. Permission: can_view = member OR super_admin from parent. Permission: can_manage = school_head OR super_admin from parent. Relation to platform: parent_platform
3. Class: 6A (yellow) — Relations: school, teacher, enrolled_student. Permission: can_view = teacher OR school_head from school OR coach from school. Permission: can_edit = teacher OR school_head from school
4. TestSession: VJ-001 (orange) — Relations: school, class, teacher. Permission: can_view = teacher OR teacher from class OR school_head from school OR coach from school. Permission: can_approve_results = teacher OR school_head from school
5. Result: R-001 (red) — Relations: session, tested_student. Permission: can_view = can_view from session. Permission: can_approve = can_approve_results from session. Note: parent access to results gated by REPORTING consent (consent-authorization boundary)
6. Student: Liam (purple, data record NOT an authenticated user) — Relation: enrolled_student of class
7. Parent/Guardian: Mrs. Molefe (pink, authenticated user) — Relation: guardian of student (e.g. Mrs. Molefe, parent of Thabo). Permission path: parent → guardian of student → student's results (gated by REPORTING consent in Consent Module)

Users to show (left side, as actors):
- Sipho (super_admin) — platform-level, can see everything
- Mr. Dlamini (school_head) — school-wide authority
- Mrs. van Wyk (teacher) — class-scoped, owns sessions
- Mr. Botha (coach) — school-wide read-only
- Mrs. Molefe (parent/guardian) — guardian of Thabo, can view Thabo's results only if REPORTING consent granted
- Developer (proposed) — platform-level read-only

Key relationship paths to illustrate:
1. Teacher → teaches class:6A → can view session VJ-001 → can approve result R-001
2. Coach → coach of school:oakwood → can view class:6A → can view session VJ-001 → CANNOT approve result (read-only)
3. School head → school_head of school:oakwood → can view ALL classes → can approve ANY result
4. Super admin → super_admin of platform:vigour → traverses parent_platform → full access
5. Parent → Mrs. Molefe guardian of student:Thabo → can view Thabo's results ONLY IF REPORTING consent exists in Consent Module
6. Student transfer: Show Liam moving from class:6A to class:7B (different school) — old tuples deleted, new tuples written, results stay linked to Liam's UUID

Visual style: Rounded rectangles for entity types. Circles/avatars for user actors. Solid arrows for direct relationships. Dashed arrows for derived permissions (traversal). Color-code by access level: green = full access, yellow = read-only, red = no access. Include a legend.

Annotations:
- Two-layer auth: JWT role (route gating) + OpenFGA tuple (resource gating)
- Roles exist in BOTH ZITADEL (JWT) and OpenFGA (tuples) and must stay in sync
- Students are data records, NOT authenticated users. Parents/guardians ARE authenticated users.
- Consent-authorization boundary: OpenFGA answers "can this user access this resource?" Consent Module answers "is this data use permitted?" Both must pass. Example: Mrs. Molefe has guardian tuple for Thabo (OpenFGA) but can only view results if REPORTING consent is active (Consent Module).
```

## Regenerate

```bash
cd docs/architecture/diagrams
GEMINI_API_KEY="$NANOBANANA_GEMINI_API_KEY" gemini --yolo "/diagram 'OpenFGA Authorization Graph — Vigour Platform.

Visualize the OpenFGA relationship-based access control model for the Vigour fitness testing platform. Show how users relate to resources through typed relationships, and how permissions are derived by traversing the graph. Include the consent-authorization boundary: OpenFGA controls access (who CAN see), Consent Module gates data use (who MAY see). Both must pass.

Layout: Clean, hierarchical graph flowing top-to-bottom. Use distinct colors for each entity type. Show relationship edges with labeled arrows. Group by scope: Platform → School → Class → Session → Results.

Entity Types (nodes):
1. Platform: vigour (top level, dark blue) — Relations: super_admin, developer (proposed)
2. School: Oakwood Primary (green) — Relations: school_head, teacher, coach. Permission: can_view = member OR super_admin from parent. Permission: can_manage = school_head OR super_admin from parent. Relation to platform: parent_platform
3. Class: 6A (yellow) — Relations: school, teacher, enrolled_student. Permission: can_view = teacher OR school_head from school OR coach from school. Permission: can_edit = teacher OR school_head from school
4. TestSession: VJ-001 (orange) — Relations: school, class, teacher. Permission: can_view = teacher OR teacher from class OR school_head from school OR coach from school. Permission: can_approve_results = teacher OR school_head from school
5. Result: R-001 (red) — Relations: session, tested_student. Permission: can_view = can_view from session. Permission: can_approve = can_approve_results from session. Note: parent access to results gated by REPORTING consent (consent-authorization boundary)
6. Student: Liam (purple, data record NOT an authenticated user) — Relation: enrolled_student of class
7. Parent/Guardian: Mrs. Molefe (pink, authenticated user) — Relation: guardian of student (e.g. Mrs. Molefe, parent of Thabo). Permission path: parent → guardian of student → student results (gated by REPORTING consent in Consent Module)

Users to show (left side, as actors):
- Sipho (super_admin) — platform-level, can see everything
- Mr. Dlamini (school_head) — school-wide authority
- Mrs. van Wyk (teacher) — class-scoped, owns sessions
- Mr. Botha (coach) — school-wide read-only
- Mrs. Molefe (parent/guardian) — guardian of Thabo, can view Thabo results only if REPORTING consent granted
- Developer (proposed) — platform-level read-only

Key relationship paths to illustrate:
1. Teacher → teaches class:6A → can view session VJ-001 → can approve result R-001
2. Coach → coach of school:oakwood → can view class:6A → can view session VJ-001 → CANNOT approve result (read-only)
3. School head → school_head of school:oakwood → can view ALL classes → can approve ANY result
4. Super admin → super_admin of platform:vigour → traverses parent_platform → full access
5. Parent → Mrs. Molefe guardian of student:Thabo → can view Thabo results ONLY IF REPORTING consent exists in Consent Module
6. Student transfer: Show Liam moving from class:6A to class:7B (different school) — old tuples deleted, new tuples written, results stay linked to Liam UUID

Visual style: Rounded rectangles for entity types. Circles/avatars for user actors. Solid arrows for direct relationships. Dashed arrows for derived permissions (traversal). Color-code by access level: green = full access, yellow = read-only, red = no access. Include a legend.

Annotations:
- Two-layer auth: JWT role (route gating) + OpenFGA tuple (resource gating)
- Roles exist in BOTH ZITADEL (JWT) and OpenFGA (tuples) and must stay in sync
- Students are data records, NOT authenticated users. Parents/guardians ARE authenticated users.
- Consent-authorization boundary: OpenFGA answers can this user access this resource? Consent Module answers is this data use permitted? Both must pass. Example: Mrs. Molefe has guardian tuple for Thabo (OpenFGA) but can only view results if REPORTING consent is active (Consent Module).'"
```

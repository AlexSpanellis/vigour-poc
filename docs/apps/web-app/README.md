# Vigour Web App -- Application Specification

## 1. App Overview

### Purpose

The Vigour Web App is a single React SPA serving all three web-facing roles: **Coach**, **School Head**, and **Super Admin**. Users authenticate via ZITADEL OIDC and are routed to role-appropriate screens. There is no separate deployed app per role -- one build, one URL, role-based routing.

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | React 18+ (Vite) |
| Routing | React Router v6 (nested routes, layout routes, route guards) |
| Server state | TanStack Query (caching, polling, background refetch) |
| Styling | Tailwind CSS + shared component library |
| Auth | `react-oidc-context` + ZITADEL OIDC, tokens in `httpOnly` secure cookies |
| API client | Auto-generated TypeScript client from OpenAPI spec |
| Charts | Recharts (or Nivo -- TBD, see architecture open questions) |
| Forms | React Hook Form + Zod validation |
| Tables | TanStack Table (sorting, filtering, pagination) |

### Roles Served

| Role | Slug | Description |
|------|------|-------------|
| Coach | `coach` | Read-only analytics for assigned classes. Cannot modify data. |
| School Head | `school_head` | School-wide overview, dashboards, staff/student admin. Maps to `admin` in OpenFGA. |
| Super Admin | `super_admin` | Platform operations: school onboarding, user management, pipeline monitoring. |

### Role-Based Routing

1. User navigates to `app.vigour.co.za`.
2. `react-oidc-context` checks for a valid session. If none, redirect to ZITADEL login.
3. On successful auth, the JWT `id_token` contains a custom claim `vigour_role` (one of `coach`, `school_head`, `super_admin`).
4. A `<RoleRouter>` component reads the role from the auth context and renders the appropriate layout and route tree.
5. If a user manually navigates to a route outside their role, the route guard redirects to their role's dashboard.
6. The sidebar, header, and available navigation items are all driven by the role claim.

---

## 2. Navigation Structure

### Shell Layout

All authenticated screens share a common layout shell:

```
+---------------------------------------------------------------+
|  HEADER BAR                                                   |
|  [Vigour logo]  [School/Org name]         [User avatar] [v]  |
+----------+----------------------------------------------------+
|          |                                                    |
| SIDEBAR  |  CONTENT AREA                                     |
|          |                                                    |
| [icon]   |  Page title + breadcrumbs                         |
| Dashboard|                                                    |
|          |  +-----------+ +-----------+ +-----------+        |
| [icon]   |  | KPI Card  | | KPI Card  | | KPI Card  |        |
| Classes  |  +-----------+ +-----------+ +-----------+        |
|          |                                                    |
| [icon]   |  +-------------------------------------------+    |
| Students |  | Main content: tables, charts, forms        |    |
|          |  |                                           |    |
| [icon]   |  |                                           |    |
|          |  +-------------------------------------------+    |
|          |                                                    |
| [icon]   |  [Action buttons]                                 |
| Settings |                                                    |
+----------+----------------------------------------------------+
```

- **Header**: Fixed top bar. Vigour logo (left), school/org name (center-left), user avatar + dropdown (right). Dropdown contains: profile, settings, logout.
- **Sidebar**: Fixed left, collapsible to icons only. Navigation items vary by role. Active item is highlighted. Grouped with section dividers where applicable.
- **Content area**: Scrollable. Page title and breadcrumbs at top. Content below.

### Sidebar Items Per Role

| Nav Item | Icon | Coach | School Head | Super Admin |
|----------|------|:-----:|:-----------:|:-----------:|
| Dashboard | `LayoutDashboard` | Yes | Yes | Yes |
| Classes | `Users` | Yes | Yes | -- |
| Students | `UserCircle` | Yes | Yes | -- |
| Sessions | `Video` | Yes | -- | -- |
| At-Risk | `AlertTriangle` | -- | Yes | -- |
| Test Scores | `BarChart` | -- | Yes | -- |
| Admin | `Settings` | -- | Yes | -- |
| Schools | `Building` | -- | -- | Yes |
| Users | `UserCog` | -- | -- | Yes |
| Transfers | `ArrowRightLeft` | -- | -- | Yes |
| Pipeline | `Cpu` | -- | -- | Yes |
| System | `Server` | -- | -- | Yes |
| Settings | `Cog` | Yes | Yes | Yes |

---

## 3. Route Table

### Shared Routes (All Roles)

| Route | Screen Name | Roles | Description |
|-------|-------------|-------|-------------|
| `/login` | Login | Public | ZITADEL OIDC redirect entry point |
| `/auth/callback` | Auth Callback | Public | OIDC callback handler, exchanges code for tokens |
| `/logout` | Logout | All | Clears session, redirects to login |
| `/settings` | Settings | All | User profile, notification preferences, password/auth management |
| `/settings/profile` | Profile | All | Edit display name, email preferences |

### Coach Routes (`/coach/*`)

| Route | Screen Name | Roles | Description |
|-------|-------------|-------|-------------|
| `/coach` | Coach Dashboard | `coach` | Class summary cards, recent sessions, quick stats |
| `/coach/classes` | Classes List | `coach` | All assigned classes with grade, student count, avg score |
| `/coach/classes/:classId` | Class Detail | `coach` | Class leaderboard, sortable student table, class KPIs |
| `/coach/students` | Students List | `coach` | All students across assigned classes, searchable |
| `/coach/students/:studentId` | Student Profile | `coach` | Individual student: per-test results, historical trends |
| `/coach/sessions` | Sessions History | `coach` | Past sessions with dates, test types, completion status |
| `/coach/sessions/:sessionId` | Session Detail | `coach` | Session results, ranked list, participation |
### School Head Routes (`/school/*`)

| Route | Screen Name | Roles | Description |
|-------|-------------|-------|-------------|
| `/school` | School Overview | `school_head` | Dashboard with KPI cards: students, school score, participation, improved, at-risk |
| `/school/grades` | Grade Breakdown | `school_head` | Per-grade performance data, trends, participation |
| `/school/grades/:grade` | Grade Detail | `school_head` | Class comparison within grade, bar chart |
| `/school/grades/:grade/:classId` | Class Detail | `school_head` | Per-student results table, class metrics |
| `/school/students` | Students List | `school_head` | All students at school, searchable, filterable |
| `/school/students/:studentId` | Student Profile | `school_head` | Individual student detail with full history |
| `/school/at-risk` | At-Risk Students | `school_head` | Students with declining test results over 2+ sessions |
| `/school/at-risk/:studentId` | At-Risk Student Detail | `school_head` | Detailed view of declining student, weak areas highlighted |
| `/school/test-scores` | Test Score Overview | `school_head` | Avg score by test type across all grades, identify weaknesses |
| `/school/admin` | Admin Hub | `school_head` | Staff management, class management, student enrolment |
| `/school/admin/staff` | Manage Staff | `school_head` | View, add, deactivate teachers and coaches |
| `/school/admin/staff/new` | Add Staff Member | `school_head` | Form to add a new teacher or coach |
| `/school/admin/classes` | Manage Classes | `school_head` | Create classes, assign teachers |
| `/school/admin/classes/:classId` | Edit Class | `school_head` | Update class details, reassign teacher |
| `/school/admin/students` | Student Enrolment | `school_head` | Add students manually or via CSV import, manage transfers out |
| `/school/admin/students/import` | CSV Import | `school_head` | Upload CSV, validate, preview, confirm import |
| `/school/admin/students/:studentId/transfer` | Transfer Student | `school_head` | Initiate student transfer to another school |

### Super Admin Routes (`/admin/*`)

| Route | Screen Name | Roles | Description |
|-------|-------------|-------|-------------|
| `/admin` | Platform Dashboard | `super_admin` | Total schools, users, sessions, pipeline health summary |
| `/admin/schools` | School Management | `super_admin` | List all schools with contract status, usage metrics |
| `/admin/schools/new` | School Onboarding Wizard | `super_admin` | Step-by-step: create ZITADEL org, school record, add head, bulk staff CSV |
| `/admin/schools/:schoolId` | School Detail | `super_admin` | View/edit school, contract status, usage stats |
| `/admin/schools/:schoolId/suspend` | Suspend School | `super_admin` | Confirm suspension, revoke access |
| `/admin/users` | User Management | `super_admin` | Search/filter all users across schools, manage accounts |
| `/admin/users/:userId` | User Detail | `super_admin` | View/edit user, reset auth, change role |
| `/admin/users/new` | Create User | `super_admin` | Add user to a specific school with role assignment |
| `/admin/transfers` | Student Transfers | `super_admin` | Pending and completed transfers, initiate new transfer |
| `/admin/transfers/new` | New Transfer | `super_admin` | Search student, select destination school, confirm |
| `/admin/pipeline` | Pipeline Monitoring | `super_admin` | Queue depth, processing times, failure rates, job list |
| `/admin/pipeline/:jobId` | Job Detail | `super_admin` | Per-stage status, error logs, retry/clear cache actions |
| `/admin/system` | System Config | `super_admin` | Platform settings: confidence threshold, retention policy, category thresholds |

---

## 4. Screen Specifications

---

### 4.1 Shared Screens

---

#### 4.1.1 Login

- **Route**: `/login`
- **Purpose**: Entry point for unauthenticated users. Redirects to ZITADEL OIDC login.
- **Roles**: Public (unauthenticated)
- **Layout**: Centered card on a full-bleed background. Vigour logo at top. "Sign in to Vigour" heading. Two options: "Sign in with Email" (magic link / email code) and "Sign in with Google/Microsoft" (SSO). Footer with support link.
- **Data displayed**: None (static).
- **User actions**: Click "Sign in with Email" (redirects to ZITADEL email flow) or click SSO provider button (redirects to ZITADEL OIDC with provider hint).
- **Navigation**: On success, redirects to `/auth/callback`. On failure, shows inline error message.

---

#### 4.1.2 Auth Callback

- **Route**: `/auth/callback`
- **Purpose**: Handles OIDC code exchange silently. Shows a spinner while processing.
- **Roles**: Public
- **Layout**: Centered spinner with "Signing you in..." text.
- **Data displayed**: None.
- **User actions**: None (automatic).
- **Navigation**: On success, redirects to the user's role-appropriate dashboard (`/coach`, `/school`, or `/admin`). On failure, redirects to `/login` with an error parameter.

---

#### 4.1.3 Settings / Profile

- **Route**: `/settings`, `/settings/profile`
- **Purpose**: View and edit personal profile, notification preferences.
- **Roles**: All authenticated roles
- **Layout**: Content area with a vertical tab list on the left (Profile, Notifications, Security). Right side shows the selected tab's form. Profile tab: display name (text input), email (read-only), school/org affiliation (read-only), role (read-only badge). Save button at bottom.
- **Data displayed**: User profile from `GET /users/me`.
- **User actions**: Edit display name, toggle notification preferences, save changes.
- **Navigation**: Sidebar remains visible. Back to dashboard via sidebar.

---

### 4.2 Coach Screens

---

#### 4.2.1 Coach Dashboard

- **Route**: `/coach`
- **Purpose**: At-a-glance summary of the coach's assigned classes and recent activity.
- **Roles**: `coach`
- **Layout**:
  - **Top row**: 4 KPI cards in a horizontal row, equal width:
    - "Classes" -- count of assigned classes (e.g. "4")
    - "Students" -- total students across classes (e.g. "108")
    - "Avg Score" -- average across classes, with a small trend arrow vs last term
    - "Sessions This Term" -- count of completed sessions (e.g. "12")
  - **Middle section**: "Recent Sessions" -- a table showing the last 5 sessions: date, class, test type, students tested, status (complete/processing). Each row is clickable.
  - **Bottom section**: "My Classes" -- grid of cards (2 or 3 columns), one per assigned class. Each card shows: class name (e.g. "Grade 6A"), teacher name, student count, latest test results summary, and a "View" link.
- **Data displayed**: `GET /coaches/me/dashboard` -- classes, recent sessions, aggregate stats.
- **User actions**: Click a session row to navigate to session detail. Click a class card to navigate to class detail. Click "View All Sessions" link.
- **Navigation**: Session row goes to `/coach/sessions/:sessionId`. Class card goes to `/coach/classes/:classId`. "All Sessions" goes to `/coach/sessions`.

---

#### 4.2.2 Classes List

- **Route**: `/coach/classes`
- **Purpose**: View all classes the coach is assigned to.
- **Roles**: `coach`
- **Layout**:
  - **Page title**: "My Classes"
  - **Grid of cards** (responsive, 2-3 columns on desktop, 1 on mobile). Each card:
    - Class name and grade (e.g. "6A -- Grade 6")
    - Teacher name
    - Student count
    - Avg test result displayed as large bold number
    - Participation rate as a small progress bar
    - "Last tested: 1 Mar 2026" subtitle
    - Change vs last term (e.g. "+4" in green or "-2" in red)
- **Data displayed**: `GET /coaches/me/classes` -- class list with aggregate metrics.
- **User actions**: Click any class card.
- **Navigation**: Card click goes to `/coach/classes/:classId`.

---

#### 4.2.3 Class Detail (Leaderboard)

- **Route**: `/coach/classes/:classId`
- **Purpose**: Detailed view of a single class with a sortable student leaderboard.
- **Roles**: `coach`
- **Layout**:
  - **Breadcrumb**: Classes > Grade 6A
  - **Header area**: Class name, teacher name, term selector dropdown (e.g. "Term 1 2026").
  - **KPI row**: 4 small cards: "Students" (28), "Avg Score" (58/100), "Participation" (81%), "Improved" (19/28).
  - **Filter bar**: Test type dropdown (All Tests, Vertical Jump, 5m Sprint, Shuttle Run, Cone Drill, Single-Leg Balance).
  - **Leaderboard table** (full-width, striped rows):
    - Columns: Rank (#), Student Name, Bib, Test Result, Attendance (%), Change vs Last Term (arrow + delta).
    - Sortable by any column (click header).
    - Pagination at bottom (25 per page).
  - **Export button**: "Export CSV" button above the table, right-aligned.
- **Data displayed**: `GET /classes/:classId/leaderboard?term=...&test_type=...` -- per-student results.
- **User actions**: Sort table columns. Filter by test type. Filter by category. Click student name. Export CSV. Change term.
- **Navigation**: Student name click goes to `/coach/students/:studentId`. Breadcrumb "Classes" goes to `/coach/classes`.

---

#### 4.2.4 Students List

- **Route**: `/coach/students`
- **Purpose**: Browse all students across the coach's assigned classes.
- **Roles**: `coach`
- **Layout**:
  - **Page title**: "Students"
  - **Search bar**: Full-width text input with search icon. Searches by name.
  - **Filter row**: Grade dropdown, Class dropdown, Category dropdown.
  - **Student table**:
    - Columns: Name, Grade, Class, Last Tested, Change.
    - Clickable rows.
    - Pagination.
- **Data displayed**: `GET /coaches/me/students?search=...&grade=...&class=...` -- paginated student list.
- **User actions**: Search by name. Filter by grade/class/category. Click student row.
- **Navigation**: Row click goes to `/coach/students/:studentId`.

---

#### 4.2.5 Student Profile

- **Route**: `/coach/students/:studentId`
- **Purpose**: Individual student's full fitness profile with historical data.
- **Roles**: `coach`, `school_head`
- **Layout**:
  - **Breadcrumb**: Students > Liam van der Berg
  - **Header card** (full-width, light background):
    - Student name (large), grade, class, bib number (if current session context).
    - Three stat badges inline: Change vs Last Term ("+8"), Attendance ("80%").
  - **Per-test breakdown** (5-column grid of small cards, one per test):
    - Each card: Test name (e.g. "Explosiveness"), icon, result (e.g. "42cm"), mini sparkline showing trend over last 4 terms.
  - **Test result trend chart** (line chart, full-width):
    - X-axis: terms (T1 2025, T2 2025, ..., T1 2026).
    - Y-axis: test result values.
    - Single line with data points. Hover shows exact value + date.
  - **Session history table**:
    - Columns: Date, Test Type, Result.
    - Shows all sessions this student participated in.
    - Sorted by date descending.
- **Data displayed**: `GET /students/:studentId` (profile), `GET /students/:studentId/scores` (historical), `GET /students/:studentId/sessions` (session list).
- **User actions**: Hover on chart points. Click a session row to see session detail. Toggle between "All Tests" and individual test type view.
- **Navigation**: Session row goes to `/coach/sessions/:sessionId`. Breadcrumb navigates back.

---

#### 4.2.6 Sessions History

- **Route**: `/coach/sessions`
- **Purpose**: Browse past test sessions for assigned classes.
- **Roles**: `coach`
- **Layout**:
  - **Page title**: "Sessions"
  - **Filter row**: Class dropdown, Test Type dropdown, Date range picker.
  - **Sessions table**:
    - Columns: Date, Class, Test Type, Students Tested, Avg Score, Status (badge: complete, processing, failed).
    - Clickable rows.
    - Sorted by date descending.
    - Pagination.
- **Data displayed**: `GET /coaches/me/sessions?class=...&test_type=...&from=...&to=...`
- **User actions**: Filter by class/type/date. Click session row.
- **Navigation**: Row click goes to `/coach/sessions/:sessionId`.

---

#### 4.2.7 Session Detail

- **Route**: `/coach/sessions/:sessionId`
- **Purpose**: View results for a specific completed session.
- **Roles**: `coach`
- **Layout**:
  - **Breadcrumb**: Sessions > Gr 6A Vertical Jump -- 1 Mar 2026
  - **Header**: Class name, test type, date, teacher name.
  - **KPI row**: Students Tested, Avg Score, Highest Score, Lowest Score.
  - **Results table**:
    - Columns: Rank, Student Name, Bib, Score.
    - Sorted by rank.
  - **Export button**: CSV (right-aligned above table).
- **Data displayed**: `GET /sessions/:sessionId` -- session metadata + results.
- **User actions**: Click student name. Export CSV.
- **Navigation**: Student name goes to `/coach/students/:studentId`.

---

### 4.3 School Head Screens

---

#### 4.3.1 School Overview Dashboard

- **Route**: `/school`
- **Purpose**: High-level school fitness health at a glance. The primary landing page for school heads.
- **Roles**: `school_head`
- **Layout**:
  - **Header area**: School name (e.g. "Oakwood Primary"), term selector dropdown.
  - **KPI row** (5 cards, horizontal):
    - "Total Students" -- large number (e.g. "341"), subtitle "enrolled this term"
    - "School Performance" -- summary metric, change badge (e.g. "+3 vs last term")
    - "Participation" -- percentage (e.g. "83%"), small bar, subtitle "students tested"
    - "Improved" -- percentage (e.g. "68%"), green text, subtitle "students improved vs last term"
    - "At-Risk" -- count (e.g. "12"), red text, subtitle "declining 2+ sessions", clickable link to at-risk list
  - **Two-column section below KPIs**:
    - **Left**: "Performance by Grade" -- horizontal bar chart. One bar per grade (dynamically rendered from the school's configured grades). Bar shows average test results. Small delta label on each bar.
    - **Right**: "Avg Score by Test Type" -- grouped bar chart or radar chart. 5 axes/bars: Explosiveness, Speed, Fitness, Agility, Balance. Shows school-wide average per test.
  - **Bottom section**: "Recent Activity" -- compact list of recent sessions across all classes. Each row: date, class, test type, teacher, students tested. Last 10 items. "View All" link.
- **Data displayed**: `GET /schools/:schoolId/dashboard?term=...` -- all KPIs and chart data.
- **User actions**: Click "At-Risk" card to go to at-risk list. Click a grade bar to drill into grade detail. Click a session in the activity list. Change term.
- **Navigation**: At-risk card goes to `/school/at-risk`. Grade bar goes to `/school/grades/:grade`. Session click goes to class detail.

---

#### 4.3.2 Grade Breakdown

- **Route**: `/school/grades`
- **Purpose**: Compare performance and participation across grades.
- **Roles**: `school_head`
- **Layout**:
  - **Page title**: "Grades"
  - **Grade cards** (one per grade, vertical stack or 2-column grid). Each card:
    - Grade label (e.g. "Grade 6")
    - Avg test results
    - Change vs last term (delta with arrow)
    - Participation rate (progress bar)
    - Number of classes
    - Number of students
    - "View Classes" link
  - **Comparison chart** (below cards): Grouped bar chart comparing all grades side by side for each test type.
- **Data displayed**: `GET /schools/:schoolId/grades?term=...`
- **User actions**: Click a grade card. Hover on chart.
- **Navigation**: Grade card goes to `/school/grades/:grade`.

---

#### 4.3.3 Grade Detail (Class Comparison)

- **Route**: `/school/grades/:grade`
- **Purpose**: Compare classes within a grade.
- **Roles**: `school_head`
- **Layout**:
  - **Breadcrumb**: Grades > Grade 6
  - **Header**: "Grade 6" title, term selector.
  - **KPI row**: Total Students, Avg Test Results, Participation, Improved count.
  - **Class comparison chart**: Horizontal bar chart, one bar per class (6A, 6B, 6C), showing avg test results. Teacher name labeled on each bar.
  - **Class table** below chart:
    - Columns: Class, Teacher, Students, Avg Score, Participation, Improved (%), Change.
    - Clickable rows.
- **Data displayed**: `GET /schools/:schoolId/grades/:grade/classes?term=...`
- **User actions**: Click a class row. Hover on chart.
- **Navigation**: Class row goes to `/school/grades/:grade/:classId`.

---

#### 4.3.4 Class Detail (School Head View)

- **Route**: `/school/grades/:grade/:classId`
- **Purpose**: View per-student results for a specific class.
- **Roles**: `school_head`
- **Layout**:
  - **Breadcrumb**: Grades > Grade 6 > 6A
  - **Header**: Class name, teacher name, term selector.
  - **KPI row**: Students, Avg Results, Participation, Improved.
  - **Student results table**:
    - Columns: Name, Test Results, Attendance, Change vs Last Term.
    - Sortable, paginated.
  - **Export button**: CSV.
- **Data displayed**: `GET /classes/:classId/leaderboard?term=...`
- **User actions**: Sort table. Click student name. Export.
- **Navigation**: Student name goes to `/school/students/:studentId`.

---

#### 4.3.5 Students List (School Head)

- **Route**: `/school/students`
- **Purpose**: Search and browse all students enrolled at the school.
- **Roles**: `school_head`
- **Layout**: Same as Coach Students List (4.2.4) but covers all students at the school, not just assigned classes. Additional filter: "At-Risk Only" toggle.
- **Data displayed**: `GET /schools/:schoolId/students?search=...&grade=...&class=...&at_risk=...`
- **User actions**: Search, filter, click student.
- **Navigation**: Row click goes to `/school/students/:studentId`.

---

#### 4.3.6 Student Profile (School Head)

- **Route**: `/school/students/:studentId`
- **Purpose**: Same as Coach Student Profile (4.2.5). School heads see the same data with full school-wide context.
- **Roles**: `school_head`
- **Layout**: Identical to section 4.2.5.
- **Additional actions**: "Transfer Student" button (links to transfer flow).
- **Navigation**: "Transfer" goes to `/school/admin/students/:studentId/transfer`.

---

#### 4.3.7 At-Risk Students

- **Route**: `/school/at-risk`
- **Purpose**: List students flagged as at-risk (declining test results over 2+ consecutive sessions).
- **Roles**: `school_head`
- **Layout**:
  - **Page title**: "At-Risk Students"
  - **Summary banner** (full-width, light red background): "12 students are currently at-risk, showing declining test results over 2 or more consecutive sessions."
  - **Filter row**: Grade dropdown, Class dropdown.
  - **At-risk table**:
    - Columns: Name, Grade, Class, Trend (mini sparkline showing last 4 data points), Decline (e.g. "declining over 2 sessions"), Primary Weak Area (e.g. "Balance"), Teacher.
    - Sorted by severity (largest decline first).
    - Red row highlight for students declining 3+ sessions.
    - Clickable rows.
- **Data displayed**: `GET /schools/:schoolId/at-risk?grade=...&class=...`
- **User actions**: Filter by grade/class. Click student row.
- **Navigation**: Student row goes to `/school/at-risk/:studentId` (or `/school/students/:studentId` with at-risk context).

---

#### 4.3.8 At-Risk Student Detail

- **Route**: `/school/at-risk/:studentId`
- **Purpose**: Detailed view of an at-risk student showing exactly which domains are declining.
- **Roles**: `school_head`
- **Layout**: Same as Student Profile (4.2.5) with an additional "At-Risk Analysis" panel:
  - **At-risk banner** at top: "This student has been declining for 3 consecutive sessions."
  - **Declining domains**: Highlighted cards for the test areas that are declining, with trend arrows down in red.
  - **Recommended actions** section: "Discuss with class teacher", "Schedule re-assessment".
  - **Action buttons**: "Back to At-Risk List".
- **Data displayed**: `GET /students/:studentId` + `GET /students/:studentId/at-risk-analysis`
- **User actions**: Navigate to teacher contact. Return to list.
- **Navigation**: "Back" returns to `/school/at-risk`.

---

#### 4.3.9 Test Score Overview

- **Route**: `/school/test-scores`
- **Purpose**: Analyze school-wide performance by test type to identify strengths and weaknesses.
- **Roles**: `school_head`
- **Layout**:
  - **Page title**: "Test Score Overview"
  - **Term selector**: Dropdown at top right.
  - **Bar chart** (full-width, prominent): 5 bars, one per test domain (Explosiveness, Speed, Fitness, Agility, Balance). Y-axis: average score. Each bar labeled with the exact average. Color-coded: green for above-average domains, red for below-average.
  - **Breakdown table** below chart:
    - Columns: Test Type, School Avg, Strongest Grade, Weakest Grade.
    - One row per test type.
  - **Insight callout**: A highlighted card below the table: "Balance (avg 48) is your school's weakest area. Consider focused training programmes for lower grades."
- **Data displayed**: `GET /schools/:schoolId/test-scores?term=...`
- **User actions**: Change term. Hover on chart bars. Click a test type row to see grade-level breakdown for that test.
- **Navigation**: Test type row drill-down (inline expand or modal).

---

#### 4.3.10 Admin Hub

- **Route**: `/school/admin`
- **Purpose**: Landing page for school administration tasks.
- **Roles**: `school_head`
- **Layout**:
  - **Page title**: "Administration"
  - **Three navigation cards** (horizontal row):
    - "Manage Staff" -- icon, count of active staff, "View" link.
    - "Manage Classes" -- icon, count of classes, "View" link.
    - "Student Enrolment" -- icon, count of enrolled students, "View" link.
- **Data displayed**: Summary counts.
- **User actions**: Click a card.
- **Navigation**: Cards go to `/school/admin/staff`, `/school/admin/classes`, `/school/admin/students`.

---

#### 4.3.11 Manage Staff

- **Route**: `/school/admin/staff`
- **Purpose**: View, add, and deactivate teachers and coaches at the school.
- **Roles**: `school_head`
- **Layout**:
  - **Page title**: "Staff" with "Add Staff" primary button (top right).
  - **Filter row**: Role filter dropdown (All, Teacher, Coach), Status filter (Active, Deactivated).
  - **Staff table**:
    - Columns: Name, Email, Role (badge), Classes Assigned, Status (active/deactivated badge), Last Login.
    - Row actions: "Edit" (pencil icon), "Deactivate" (for active) / "Reactivate" (for deactivated).
  - **Deactivation confirmation**: Modal dialog: "Deactivate [Name]? They will lose access to all school data. This can be reversed."
- **Data displayed**: `GET /schools/:schoolId/staff`
- **User actions**: Add new staff. Edit staff details. Deactivate/reactivate.
- **Navigation**: "Add Staff" goes to `/school/admin/staff/new`. "Edit" opens inline form or navigates to edit page.

---

#### 4.3.12 Add Staff Member

- **Route**: `/school/admin/staff/new`
- **Purpose**: Add a new teacher or coach to the school.
- **Roles**: `school_head`
- **Layout**:
  - **Page title**: "Add Staff Member"
  - **Form fields**: First name, Last name, Email, Role (dropdown: Teacher, Coach), Classes (multi-select, optional).
  - **Submit button**: "Add & Send Invite". On submit: creates ZITADEL user in school org, writes OpenFGA tuples, sends magic link invite email.
  - **Success state**: Green banner "Invite sent to [email]".
- **Data displayed**: Class list for multi-select.
- **User actions**: Fill form, submit.
- **Navigation**: Back to `/school/admin/staff` after success.

---

#### 4.3.13 Manage Classes

- **Route**: `/school/admin/classes`
- **Purpose**: Create and manage classes at the school.
- **Roles**: `school_head`
- **Layout**:
  - **Page title**: "Classes" with "Create Class" primary button.
  - **Classes table**:
    - Columns: Class Name, Grade, Teacher, Students, Created Date.
    - Row actions: "Edit", "Delete" (only if no sessions exist).
  - **Create/edit form** (modal or separate page):
    - Fields: Class Name, Grade (dropdown populated from the school's configured grades), Assigned Teacher (dropdown).
- **Data displayed**: `GET /schools/:schoolId/classes`
- **User actions**: Create class, edit class, delete empty class.
- **Navigation**: "Create Class" opens form. "Edit" opens form with pre-filled values.

---

#### 4.3.14 Edit Class

- **Route**: `/school/admin/classes/:classId`
- **Purpose**: Edit class details and reassign teacher.
- **Roles**: `school_head`
- **Layout**: Form with pre-filled fields: Class Name, Grade, Teacher dropdown. "Save" button. "Delete Class" danger button (disabled if sessions exist, with tooltip explaining why).
- **Data displayed**: `GET /classes/:classId`
- **User actions**: Update fields, save. Delete if applicable.
- **Navigation**: Back to `/school/admin/classes`.

---

#### 4.3.15 Student Enrolment

- **Route**: `/school/admin/students`
- **Purpose**: Manage student roster -- add manually, import via CSV, transfer out.
- **Roles**: `school_head`
- **Layout**:
  - **Page title**: "Student Enrolment" with two buttons: "Add Student" (primary), "Import CSV" (secondary).
  - **Filter row**: Grade dropdown, Class dropdown, search input.
  - **Student table**:
    - Columns: Name, Grade, Class, Date of Birth, Gender, Enrolled Date, Status.
    - Row actions: "Edit", "Transfer Out".
  - **Add Student form** (modal): First name, Last name, Date of birth, Gender, Grade, Class (dropdown).
- **Data displayed**: `GET /schools/:schoolId/students`
- **User actions**: Add student, import CSV, edit student, initiate transfer.
- **Navigation**: "Import CSV" goes to `/school/admin/students/import`. "Transfer Out" goes to `/school/admin/students/:studentId/transfer`.

---

#### 4.3.16 CSV Import

- **Route**: `/school/admin/students/import`
- **Purpose**: Bulk import students from a CSV file.
- **Roles**: `school_head`
- **Layout**:
  - **Step 1 -- Upload**: File drop zone. "Download Template" link to get a blank CSV template. Accepted format description: `first_name, last_name, dob, gender, class`.
  - **Step 2 -- Validate**: Table preview of parsed CSV rows. Valid rows in white, invalid rows highlighted red with error description in a tooltip (e.g. "Missing date of birth", "Invalid gender value", "Duplicate name"). Summary: "26 of 28 rows valid".
  - **Step 3 -- Confirm**: "Import 26 valid students" primary button. Option to "Fix errors and re-upload" or "Proceed with valid rows only".
  - **Step 4 -- Result**: Success banner with count imported. List of any skipped rows.
- **Data displayed**: Parsed CSV preview.
- **User actions**: Upload file, review validation, confirm import.
- **Navigation**: Back to `/school/admin/students` after completion.

---

#### 4.3.17 Transfer Student (School Head)

- **Route**: `/school/admin/students/:studentId/transfer`
- **Purpose**: Initiate transfer of a student to another school.
- **Roles**: `school_head`
- **Layout**:
  - **Student info card**: Name, grade, class.
  - **Transfer form**:
    - Destination school: Searchable dropdown of all schools on the platform.
    - Destination class (optional): Dropdown of classes at destination school (loads after school is selected).
  - **Info notice**: "Historical results will remain linked to this student. Your school will lose access to this student's data after transfer."
  - **Confirm button**: "Transfer Student". Confirmation dialog with summary before execution.
- **Data displayed**: `GET /students/:studentId`, `GET /schools` (for destination list).
- **User actions**: Select destination, optionally select class, confirm.
- **Navigation**: Back to `/school/admin/students` after completion.

---

### 4.4 Super Admin Screens

---

#### 4.4.1 Platform Dashboard

- **Route**: `/admin`
- **Purpose**: Platform-wide health and usage overview.
- **Roles**: `super_admin`
- **Layout**:
  - **KPI row** (4 cards):
    - "Schools" -- total active schools (e.g. "309"), with "+3 this month" subtitle
    - "Users" -- total active users (e.g. "1,420")
    - "Sessions" -- total sessions processed this month (e.g. "2,841")
    - "Pipeline Health" -- status indicator (green/yellow/red), with "98.2% success rate" subtitle
  - **Two-column section**:
    - **Left**: "Recent School Activity" -- table showing last 10 schools with activity. Columns: School, Last Session, Active Users, Sessions This Month.
    - **Right**: "Pipeline Status" -- compact dashboard: queue depth gauge, avg processing time, failure rate trend (sparkline over 7 days), active workers count.
  - **Bottom**: "Alerts" -- list of actionable alerts: failed pipeline jobs, suspended schools approaching expiry, schools with no activity in 30+ days.
- **Data displayed**: `GET /admin/dashboard`
- **User actions**: Click school row. Click pipeline status for detail. Click alert items.
- **Navigation**: School click goes to `/admin/schools/:schoolId`. Pipeline click goes to `/admin/pipeline`. Alert clicks go to relevant detail pages.

---

#### 4.4.2 School Management

- **Route**: `/admin/schools`
- **Purpose**: View and manage all schools on the platform.
- **Roles**: `super_admin`
- **Layout**:
  - **Page title**: "Schools" with "Onboard School" primary button.
  - **Filter row**: Province dropdown, District dropdown, Contract Status filter (Active, Suspended, Expired), search input.
  - **Schools table**:
    - Columns: School Name, District, Province, Students, Users, Contract Status (color-coded badge: green=Active, yellow=Suspended, red=Expired), Last Activity, Actions.
    - Row actions: "View" (eye icon), "Suspend" / "Reactivate" (toggle).
    - Sortable, paginated.
- **Data displayed**: `GET /admin/schools?province=...&district=...&status=...&search=...`
- **User actions**: Search/filter schools. Click to view. Onboard new school. Suspend/reactivate.
- **Navigation**: "View" goes to `/admin/schools/:schoolId`. "Onboard School" goes to `/admin/schools/new`.

---

#### 4.4.3 School Onboarding Wizard

- **Route**: `/admin/schools/new`
- **Purpose**: Step-by-step wizard to onboard a new contracted school.
- **Roles**: `super_admin`
- **Layout**: Multi-step wizard with progress indicator at top (Step 1 of 4, Step 2 of 4, etc.):
  - **Step 1 -- School Details**:
    - Fields: School Name, District (dropdown), Province (dropdown), EMIS Number (optional), Address, Contact Phone.
    - "Next" button.
  - **Step 2 -- Identity Setup**:
    - "Create ZITADEL Organization" button. Shows spinner while creating. On success: green checkmark and org ID displayed.
    - Automatic: links school record to ZITADEL org.
    - "Next" button (disabled until org is created).
  - **Step 3 -- School Head**:
    - Fields: First Name, Last Name, Email, Phone (optional).
    - "Create School Head Account" button. Creates user in ZITADEL org, writes OpenFGA tuples (`user:uuid -> school_head -> school:X`), queues invite email.
    - Success: "Invite sent to [email]" banner.
    - "Next" button.
  - **Step 4 -- Bulk Staff Import** (optional):
    - "Skip" link (can add staff later).
    - CSV file upload zone. Template download link.
    - Validation preview table (same as 4.3.18 CSV Import but for staff: `name, email, role`).
    - "Import Staff" button. Creates ZITADEL users, writes tuples, queues invite emails.
    - Summary: "15 staff members imported. 15 invite emails queued."
  - **Completion screen**: Summary card with all created resources. "Go to School Detail" and "Onboard Another School" buttons.
- **Data displayed**: Province/district lists. Validation results.
- **User actions**: Fill forms, create org, create head, optionally import staff.
- **Navigation**: Wizard steps. On completion: `/admin/schools/:schoolId` or `/admin/schools/new`.

---

#### 4.4.4 School Detail (Admin)

- **Route**: `/admin/schools/:schoolId`
- **Purpose**: View and manage a specific school.
- **Roles**: `super_admin`
- **Layout**:
  - **Header card**: School name, district, province, EMIS number. Contract status badge. "Suspend" / "Reactivate" button.
  - **Usage stats row**: Students enrolled, Active users, Sessions this term, Last activity date.
  - **Tabs** (horizontal tab bar):
    - **Overview**: School details, contact info, ZITADEL org link.
    - **Staff**: Staff table (same structure as 4.3.13). "Add Staff" button.
    - **Students**: Student count, grade breakdown, enrolment stats. No individual student data (admin doesn't need it).
    - **Classes**: Class list with teacher assignments.
    - **Sessions**: Recent session activity log.
  - **Danger zone** (at bottom, red border): "Suspend School" button with confirmation dialog.
- **Data displayed**: `GET /admin/schools/:schoolId`
- **User actions**: View tabs, suspend/reactivate, add staff, view activity.
- **Navigation**: Tabs within the page. "Add Staff" opens form.

---

#### 4.4.5 Suspend School

- **Route**: `/admin/schools/:schoolId/suspend`
- **Purpose**: Confirm suspension of a school's access.
- **Roles**: `super_admin`
- **Layout**: Confirmation page or modal:
  - School name and details.
  - Impact summary: "All [N] users at [School] will lose access. Active sessions will be preserved but no new sessions can be created."
  - Reason field (text input, required): "Contract expired", "Non-payment", or free text.
  - "Confirm Suspension" danger button and "Cancel" link.
- **Data displayed**: School info, user count.
- **User actions**: Enter reason, confirm or cancel.
- **Navigation**: Back to `/admin/schools/:schoolId` after action.

---

#### 4.4.6 User Management

- **Route**: `/admin/users`
- **Purpose**: Search and manage users across all schools.
- **Roles**: `super_admin`
- **Layout**:
  - **Page title**: "Users" with "Create User" primary button.
  - **Filter row**: School dropdown, Role dropdown (Teacher, Coach, School Head, Super Admin), Status (Active, Deactivated), search input.
  - **Users table**:
    - Columns: Name, Email, Role (badge), School, Status (badge), Last Login, Actions.
    - Row actions: "View" (eye), "Deactivate"/"Reactivate", "Reset Auth".
    - Paginated.
- **Data displayed**: `GET /admin/users?school=...&role=...&status=...&search=...`
- **User actions**: Search, filter, view user, deactivate, reset auth, create user.
- **Navigation**: "View" goes to `/admin/users/:userId`. "Create User" goes to `/admin/users/new`.

---

#### 4.4.7 User Detail

- **Route**: `/admin/users/:userId`
- **Purpose**: View and manage a specific user account.
- **Roles**: `super_admin`
- **Layout**:
  - **Header card**: Name, email, role badge, school name, status badge.
  - **Account info section**: Created date, last login, auth method (magic link / SSO provider).
  - **Actions section** (button group):
    - "Edit Role" -- dropdown to change role with confirmation.
    - "Reset Authentication" -- re-sends magic link or resets SSO binding. Confirmation dialog.
    - "Deactivate Account" / "Reactivate Account" -- toggle with confirmation.
  - **Activity log**: Recent actions by this user (sessions created, logins, etc.).
- **Data displayed**: `GET /admin/users/:userId`
- **User actions**: Edit role, reset auth, deactivate/reactivate.
- **Navigation**: Back to `/admin/users`.

---

#### 4.4.8 Create User

- **Route**: `/admin/users/new`
- **Purpose**: Create a new user account at any school.
- **Roles**: `super_admin`
- **Layout**:
  - **Form fields**: First Name, Last Name, Email, School (searchable dropdown), Role (dropdown: Teacher, Coach, School Head, Super Admin).
  - **Conditional fields**: If role is Teacher or Coach, show "Assign Classes" multi-select (classes at the selected school).
  - **Submit button**: "Create & Send Invite".
  - **Success state**: Banner with "User created. Invite sent to [email]."
- **Data displayed**: School list, class list (filtered by selected school).
- **User actions**: Fill form, submit.
- **Navigation**: Back to `/admin/users` after success.

---

#### 4.4.9 Student Transfers

- **Route**: `/admin/transfers`
- **Purpose**: Manage student transfers between schools.
- **Roles**: `super_admin`
- **Layout**:
  - **Page title**: "Student Transfers" with "New Transfer" primary button.
  - **Tabs**: "Pending" and "Completed".
  - **Transfers table**:
    - Columns: Student Name, From School, To School, Initiated By, Date, Status (Pending/Completed/Failed).
    - Clickable rows for detail.
- **Data displayed**: `GET /admin/transfers?status=...`
- **User actions**: View transfers, initiate new transfer.
- **Navigation**: "New Transfer" goes to `/admin/transfers/new`.

---

#### 4.4.10 New Transfer

- **Route**: `/admin/transfers/new`
- **Purpose**: Initiate a student transfer between schools.
- **Roles**: `super_admin`
- **Layout**:
  - **Step 1 -- Find Student**: Search input (name or ID). Results table with: Name, Grade, Current School, Current Class.
  - **Step 2 -- Select Destination**: Destination School (searchable dropdown). Destination Class (optional, dropdown filtered by selected school and appropriate grade).
  - **Step 3 -- Confirm**: Summary card showing: student name, from school, to school, destination class. Impact notice: "The source school will lose access to this student. Historical results remain linked to the student." "Confirm Transfer" button.
  - **Success state**: "Transfer completed. [Student] has been moved to [School]."
- **Data displayed**: Student search results, school list, class list.
- **User actions**: Search student, select destination, confirm.
- **Navigation**: Back to `/admin/transfers` after completion.

---

#### 4.4.11 Pipeline Monitoring

- **Route**: `/admin/pipeline`
- **Purpose**: Monitor CV pipeline health, queue depth, and processing metrics.
- **Roles**: `super_admin`
- **Layout**:
  - **Page title**: "Pipeline Monitoring"
  - **KPI row** (4 cards):
    - "Queue Depth" -- number of jobs waiting (e.g. "3"), with trend arrow
    - "Avg Processing Time" -- in minutes (e.g. "4.2 min"), trend vs last week
    - "Success Rate" -- percentage (e.g. "98.2%"), last 7 days
    - "Active Workers" -- count (e.g. "2/4"), with capacity indicator
  - **Failure rate chart** (line chart): Failure rate % over last 30 days. Red threshold line at 5%.
  - **Job list table** (below):
    - Columns: Job ID, School, Class, Test Type, Submitted At, Duration, Status (badge: queued/processing/complete/failed), Current Stage (e.g. "5/8 OCR").
    - Filter: Status dropdown. Date range.
    - Failed jobs highlighted in red.
    - Clickable rows.
- **Data displayed**: `GET /admin/pipeline/dashboard`, `GET /admin/pipeline/jobs?status=...`
- **User actions**: Filter jobs. Click job for detail. Hover on chart.
- **Navigation**: Job row goes to `/admin/pipeline/:jobId`.

---

#### 4.4.12 Pipeline Job Detail

- **Route**: `/admin/pipeline/:jobId`
- **Purpose**: Inspect a specific pipeline job, view per-stage status, retry or clear cache.
- **Roles**: `super_admin`
- **Layout**:
  - **Breadcrumb**: Pipeline > Job abc123
  - **Header card**: Job ID, school, class, test type, submitted by (teacher name), submitted at, total duration.
  - **Stage progress** (vertical timeline, 8 stages):
    - Each stage: stage name, status icon (complete/in-progress/pending/failed), duration, start/end time.
    - Failed stage highlighted in red with error message.
  - **Error details** (shown if failed): Error type, error message, stack trace (collapsible), affected frames/bibs.
  - **Action buttons**:
    - "Retry Job" -- resubmits the job.
    - "Retry from Stage [X]" -- resubmits from the failed stage using cached prior stages.
    - "Clear Cache" -- invalidates cached stage outputs, forces full reprocessing.
  - **Logs section** (collapsible): Raw log output for each stage.
- **Data displayed**: `GET /admin/pipeline/jobs/:jobId`
- **User actions**: Retry, retry from stage, clear cache, view logs.
- **Navigation**: Back to `/admin/pipeline`.

---

#### 4.4.13 System Config

- **Route**: `/admin/system`
- **Purpose**: View and modify platform-wide configuration settings.
- **Roles**: `super_admin`
- **Layout**:
  - **Page title**: "System Configuration"
  - **Grouped settings** (accordion sections):
    - **Pipeline Settings**: Auto-approval confidence threshold (slider, 0.0-1.0, default 0.8). Max retry attempts (number input). Processing timeout (minutes).
    - **Storage Settings**: Video retention policy (days).
    - **Scoring Settings**: Reserved for future scoring system configuration.
    - **Auth Settings**: Magic link code expiry (minutes). Session duration (hours). Refresh token lifetime (days).
  - **Save button**: "Save Changes" with confirmation dialog: "Changes will apply platform-wide. Are you sure?"
  - **Audit note**: "All configuration changes are logged."
- **Data displayed**: `GET /admin/system/config`
- **User actions**: Adjust settings, save.
- **Navigation**: Standalone page.

---

## 5. Role-Based UI Summary

### Route Access Matrix

| Route Pattern | Coach | School Head | Super Admin |
|---------------|:-----:|:-----------:|:-----------:|
| `/login`, `/auth/callback`, `/logout` | Yes | Yes | Yes |
| `/settings` | Yes | Yes | Yes |
| `/coach` | **Yes** | -- | -- |
| `/coach/classes` | **Yes** | -- | -- |
| `/coach/classes/:classId` | **Yes** | -- | -- |
| `/coach/students` | **Yes** | -- | -- |
| `/coach/students/:studentId` | **Yes** | -- | -- |
| `/coach/sessions` | **Yes** | -- | -- |
| `/coach/sessions/:sessionId` | **Yes** | -- | -- |
| `/school` | -- | **Yes** | -- |
| `/school/grades` | -- | **Yes** | -- |
| `/school/grades/:grade` | -- | **Yes** | -- |
| `/school/grades/:grade/:classId` | -- | **Yes** | -- |
| `/school/students` | -- | **Yes** | -- |
| `/school/students/:studentId` | -- | **Yes** | -- |
| `/school/at-risk` | -- | **Yes** | -- |
| `/school/at-risk/:studentId` | -- | **Yes** | -- |
| `/school/test-scores` | -- | **Yes** | -- |
| `/school/admin` | -- | **Yes** | -- |
| `/school/admin/staff` | -- | **Yes** | -- |
| `/school/admin/staff/new` | -- | **Yes** | -- |
| `/school/admin/classes` | -- | **Yes** | -- |
| `/school/admin/classes/:classId` | -- | **Yes** | -- |
| `/school/admin/students` | -- | **Yes** | -- |
| `/school/admin/students/import` | -- | **Yes** | -- |
| `/school/admin/students/:studentId/transfer` | -- | **Yes** | -- |
| `/admin` | -- | -- | **Yes** |
| `/admin/schools` | -- | -- | **Yes** |
| `/admin/schools/new` | -- | -- | **Yes** |
| `/admin/schools/:schoolId` | -- | -- | **Yes** |
| `/admin/schools/:schoolId/suspend` | -- | -- | **Yes** |
| `/admin/users` | -- | -- | **Yes** |
| `/admin/users/:userId` | -- | -- | **Yes** |
| `/admin/users/new` | -- | -- | **Yes** |
| `/admin/transfers` | -- | -- | **Yes** |
| `/admin/transfers/new` | -- | -- | **Yes** |
| `/admin/pipeline` | -- | -- | **Yes** |
| `/admin/pipeline/:jobId` | -- | -- | **Yes** |
| `/admin/system` | -- | -- | **Yes** |

### Sidebar Adaptation Logic

```
function getSidebarItems(role):
  shared = [Settings]

  if role == "coach":
    return [Dashboard, Classes, Students, Sessions] + shared

  if role == "school_head":
    return [Dashboard, Grades, Students, At-Risk, Test Scores, Admin] + shared

  if role == "super_admin":
    return [Dashboard, Schools, Users, Transfers, Pipeline, System] + shared
```

### Default Redirect Per Role

| Role | Login Redirects To |
|------|-------------------|
| `coach` | `/coach` |
| `school_head` | `/school` |
| `super_admin` | `/admin` |

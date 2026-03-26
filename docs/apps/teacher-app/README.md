# Vigour Teacher App -- Application Specification

## 1. App Overview

### What It Is

The Vigour Teacher App is a native mobile application used by teachers to run physical fitness test sessions in South African schools. It is the primary operational tool in the Vigour platform -- all downstream data (coach dashboards, school dashboards) originates from sessions completed in this app.

### Who Uses It

Teachers (PE teachers, class teachers running fitness assessments) at contracted South African schools. The persona is a non-technical teacher working on a school field with a phone, often with limited connectivity.

### Why It Exists

The app bridges the gap between physical fitness testing on a field and automated CV-powered performance analysis. A teacher records video of learners performing a fitness test, assigns bib numbers to match students to detected figures, uploads the video, and reviews CV-processed results before committing them to student profiles.

### Tech Stack

- **Framework**: Expo / React Native (iOS + Android)
- **Auth**: `expo-auth-session` + ZITADEL OIDC (PKCE flow), tokens stored in `expo-secure-store`
- **State management**: TanStack Query (server state, polling, offline mutation queue)
- **API client**: Auto-generated TypeScript client from OpenAPI spec
- **Camera**: `expo-camera` for 4K/60fps recording
- **Storage**: Local device storage for offline video, `expo-file-system` for queue persistence

### Key Capabilities

| Capability | Detail |
|---|---|
| Camera recording | 4K resolution at 60fps with live CV overlay (bib detection count, tracking indicators) |
| Offline support | Session setup, bib assignment, and recording work fully offline using cached class/student data |
| Upload queue | Videos queue locally when offline; auto-upload resumes when connectivity returns; queue persists across app restarts |
| Direct cloud upload | Video bytes go directly to GCS/S3 via signed URL -- never through the Application API |
| Push notifications | Notifies teacher when pipeline processing completes or fails |
| Pipeline status polling | Real-time stage-by-stage progress for the 8-stage CV pipeline (MVP uses polling; WebSocket future) |
| Result review | Per-student result review with confidence indicators, bulk approve, manual reassignment |

---

## 2. Navigation Structure

The app uses a **bottom tab bar** with 4 tabs as the primary navigation, plus modal/stack flows for the session lifecycle.

```
Tab Bar
  |-- Home (tab)
  |     |-- Dashboard (class list + recent sessions)
  |     |-- Session Detail (from recent sessions list)
  |     |-- Student Profile (from results)
  |
  |-- Sessions (tab)
  |     |-- Session List (all sessions, filterable by status)
  |     |-- Session Detail
  |
  |-- Upload Queue (tab)
  |     |-- Upload Queue list
  |
  |-- Settings (tab)
        |-- Account
        |-- Notifications
        |-- Offline Data
        |-- Help & Support
        |-- About

Modal / Stack Flows (pushed on top of tab bar):
  |-- New Session Flow (full-screen stack)
  |     |-- Create Session (select class + test)
  |     |-- Bib Assignment
  |     |-- Pre-flight Check
  |     |-- Recording
  |     |-- Clip Review
  |     |-- Upload Progress
  |
  |-- Pipeline Status (full-screen or inline in session detail)
  |-- Results Review (full-screen stack)
  |     |-- Results List
  |     |-- Result Detail / Reassign modal
  |     |-- Bulk Approve confirmation
  |     |-- Commit confirmation
  |
  |-- Session Complete (full-screen)

Auth Flow (before tab bar, unauthenticated):
  |-- Welcome
  |-- Email Entry
  |-- Code Verification
  |-- First-Time Setup
```

---

## 3. Route Table

| Route | Screen Name | Description | Auth Required | Offline Support |
|---|---|---|---|---|
| `/welcome` | Welcome | App landing with branding and "Get Started" CTA | No | Yes (static) |
| `/auth/email` | Email Entry | Teacher enters their school email address | No | No |
| `/auth/verify` | Code Verification | 6-digit code input sent to email | No | No |
| `/auth/setup` | First-Time Setup | Shows school, classes, and optional guided tour | Yes | No |
| `/home` | Home Dashboard | Class list with session counts and recent sessions | Yes | Partial (cached data) |
| `/sessions` | Session List | All sessions filterable by status, class, test type | Yes | Partial (cached data) |
| `/sessions/:id` | Session Detail | Single session status, actions, and result summary | Yes | Partial (cached data) |
| `/sessions/new` | Create Session | Select grade, class, and test type to create a draft session | Yes | Yes (cached class lists) |
| `/sessions/:id/bibs` | Bib Assignment | Assign bib numbers (1-30) to each student in the class | Yes | Yes (cached student roster) |
| `/sessions/:id/preflight` | Pre-flight Check | Live camera preview with CV readiness checks | Yes | Yes (camera only) |
| `/sessions/:id/record` | Recording | 4K/60fps camera capture with live CV overlay | Yes | Yes (local storage) |
| `/sessions/:id/review-clip` | Clip Review | Playback recorded clip with CV quality summary | Yes | Yes (local video) |
| `/sessions/:id/upload` | Upload Progress | Progress bar for direct-to-cloud video upload | Yes | No (queues if offline) |
| `/sessions/:id/pipeline` | Pipeline Status | 8-stage progress indicator while CV pipeline processes | Yes | No |
| `/sessions/:id/results` | Results Review | Per-student results with confidence indicators for approval | Yes | No |
| `/sessions/:id/results/:resultId` | Result Detail | Single result with reassign/approve/reject actions | Yes | No |
| `/sessions/:id/complete` | Session Complete | Ranked results | Yes | Partial (cached after load) |
| `/upload-queue` | Upload Queue | List of queued/in-progress uploads with status | Yes | Yes |
| `/students/:id` | Student Profile | Individual student history, per-test results and trends | Yes | Partial (cached data) |
| `/settings` | Settings | Account, notification, and data management options | Yes | Partial |
| `/settings/account` | Account Settings | Name, email, school info, sign out | Yes | Partial |
| `/settings/notifications` | Notification Settings | Push notification preferences | Yes | No |
| `/settings/offline` | Offline Data | Cache status, storage usage, clear cache | Yes | Yes |
| `/settings/about` | About | App version, terms, privacy policy, licences | Yes | Yes (static) |
| `/help` | Help & Support | Troubleshooting guides, common fixes | Yes | Yes (cached) |
| `/help/contact` | Contact Support | Pre-filled support ticket form | Yes | No |

---

## 4. Screen Specifications

### 4.1 Welcome (`/welcome`)

**Purpose**: First screen a new user sees. Establishes branding and directs to authentication.

**Layout description**: Full-screen splash layout. Vigour logo centred in the upper third. Below the logo, a tagline: "Fitness testing, simplified." A large illustration or background image of children doing fitness activities fills the middle area. At the bottom, a primary button "Get Started" spans the full width with horizontal padding. Below it, a text link "Already have an account? Sign in" for returning users.

**Data displayed**: None (static).

**User actions**: Tap "Get Started" or "Sign in" to navigate to email entry.

**Navigation**: Forward to `/auth/email`.

**State variations**: Static -- no loading, error, or offline states. If the user is already authenticated (valid refresh token), skip this screen and go directly to `/home`.

**Session state**: N/A.

---

### 4.2 Email Entry (`/auth/email`)

**Purpose**: Teacher enters their school email to begin the magic-link authentication flow.

**Layout description**: Back arrow in the top-left corner. Heading "Sign in to Vigour" near the top. Subtext: "Enter the email your school registered you with." A single email text input field with keyboard type set to email. Below it, a primary button "Continue" (disabled until a valid email format is entered). Below the button, secondary text: "Don't have an account? Contact your school administrator."

**Data displayed**: None.

**User actions**: Type email address, tap "Continue".

**Navigation**: Back to `/welcome`. Forward to `/auth/verify` on success. Shows inline error if email is not registered ("You are not registered. Contact your school admin." with school head contact info if available).

**State variations**:
- **Default**: Empty input, button disabled.
- **Valid input**: Button enabled.
- **Loading**: Button shows spinner after tap, input disabled.
- **Error -- not registered**: Error message below input with school contact information.
- **Error -- network**: "Could not connect. Check your internet connection." with retry.

**Session state**: N/A.

---

### 4.3 Code Verification (`/auth/verify`)

**Purpose**: Teacher enters the 6-digit verification code sent to their email.

**Layout description**: Back arrow top-left. Heading "Check your email". Subtext: "We sent a 6-digit code to jane@oakwood.edu.za" (shows the entered email). Six individual digit input boxes in a row, auto-advancing focus as each digit is entered. Below the inputs, a countdown timer showing code expiry ("Code expires in 4:32"). Below that, a text link "Didn't receive it? Resend code" (disabled during a brief cooldown after sending). At the bottom, a "Verify" button (auto-triggers when all 6 digits are entered).

**Data displayed**: The email address the code was sent to.

**User actions**: Enter 6-digit code (auto-submits), tap "Resend code".

**Navigation**: Back to `/auth/email`. Forward to `/auth/setup` (first-time) or `/home` (returning user) on success.

**State variations**:
- **Default**: Empty code boxes, timer counting down.
- **Loading**: Spinner overlay while verifying.
- **Error -- wrong code**: Boxes shake, error text "Invalid code. Please try again." with remaining attempts shown.
- **Error -- expired**: "Code expired. Please request a new one." with resend link highlighted.
- **Error -- too many attempts**: "Too many attempts. Please try again in 5 minutes."

**Session state**: N/A.

---

### 4.4 First-Time Setup (`/auth/setup`)

**Purpose**: Orients a new teacher after first successful authentication. Shows their school, assigned classes, and offers a guided tour.

**Layout description**: Heading "Welcome, Mrs. van Wyk" (teacher's name from their profile). Below, a card showing school information: school name, logo (if available), and address. Below the school card, a section "Your Classes" listing each assigned class as a row: class name (e.g. "Grade 6A"), student count (e.g. "28 students"), and the teacher's name. At the bottom, two buttons stacked vertically: a primary button "Take the Tour" and a secondary/text button "Skip -- go to Home".

**Data displayed**: Teacher name, school name, list of assigned classes with student counts (from `GET /me` and `GET /classes`).

**User actions**: Tap "Take the Tour" for a guided walkthrough, or "Skip" to go directly to home.

**Navigation**: Forward to guided walkthrough overlay (tooltip-style) or directly to `/home`.

**State variations**:
- **Loading**: Skeleton cards while fetching profile and class data.
- **Error**: "Could not load your profile. Tap to retry." with retry button.

**Session state**: N/A.

---

### 4.5 Home Dashboard (`/home`)

**Purpose**: Primary landing screen. Gives the teacher a quick overview of their classes and recent/in-progress sessions.

**Layout description**: Top section has a greeting ("Good morning, Mrs. van Wyk") with a small avatar/icon and a notification bell icon (with badge count if unread). Below, a prominent "New Session" button (pill-shaped, full width, primary colour).

Below the button, a section "Your Classes" shows horizontal scrollable cards, one per class. Each card displays: class name ("6A"), grade ("Gr 6"), student count ("28"), and last session date ("Last tested: 3 days ago") or "No sessions yet" if none.

Below the classes, a section "Recent Sessions" shows a vertical list of session cards, sorted by most recent. Each session card shows: class name and grade, test type (e.g. "Vertical Jump"), date, and a status badge (`draft`, `ready`, `recording`, `uploading`, `processing`, `review`, `complete`, `failed`). The badge is colour-coded: grey for draft/ready, blue for recording/uploading/processing, orange for review, green for complete, red for failed.

A floating action button (FAB) or the top "New Session" button both trigger session creation.

**Data displayed**: Teacher profile (name), classes with student counts and last session dates (from `GET /classes`), recent sessions with status (from `GET /sessions?sort=-created_at&limit=10`).

**User actions**: Tap "New Session" to start a new session. Tap a class card to see sessions for that class. Tap a session card to open session detail. Tap notification bell to see notifications.

**Navigation**: To `/sessions/new` (new session). To `/sessions/:id` (session detail). To class-filtered session list. To notification list (future).

**State variations**:
- **Loading**: Skeleton cards for classes and sessions.
- **Empty -- no classes**: "No classes assigned. Contact your school administrator." (this would be unusual -- teachers are assigned classes during onboarding).
- **Empty -- no sessions**: Classes show normally. Recent sessions section says "No sessions yet. Tap 'New Session' to get started!" with an illustration.
- **Offline**: Cached data shown with an offline banner at the top: "You are offline. Some features are limited." Classes and cached sessions still visible. "New Session" button still works (offline session setup).
- **Error**: "Could not load data. Pull down to refresh." with pull-to-refresh.

**Session state**: Displays sessions across all states.

---

### 4.6 Session List (`/sessions`)

**Purpose**: Full list of all sessions the teacher has created, with filtering and sorting.

**Layout description**: Top bar with "Sessions" title and a filter icon. Below the title, horizontal filter chips for session status: "All", "In Progress" (draft/ready/recording/uploading), "Processing" (queued/processing), "Review", "Complete", "Failed". Tapping a chip filters the list.

Below the chips, a vertical scrolling list of session cards. Each card shows: class name and grade, test type with icon, date and time, status badge (colour-coded as in Home), and for `uploading`/`processing` states, a small progress indicator. Cards are sorted by date descending.

Pull-to-refresh at the top.

**Data displayed**: All sessions for the teacher (from `GET /sessions` with pagination), filtered by selected status.

**User actions**: Tap a filter chip. Tap a session card to open detail. Pull to refresh.

**Navigation**: To `/sessions/:id` on card tap. Back to Home via tab bar.

**State variations**:
- **Loading**: Skeleton list.
- **Empty (filtered)**: "No [status] sessions." with a prompt to create one if applicable.
- **Empty (all)**: "No sessions yet. Create your first session from the Home tab."
- **Offline**: Cached sessions shown. Stale data banner: "Showing cached data. Connect to refresh."
- **Error**: Inline error with retry.

**Session state**: Shows sessions in all states.

---

### 4.7 Session Detail (`/sessions/:id`)

**Purpose**: Single session overview with contextual actions based on the session's current status.

**Layout description**: Back arrow top-left. Header area shows: class name and grade ("Gr 6 - 6A"), test type ("Vertical Jump"), date created, and a large status badge.

Below the header, the content varies by session status:

- **`draft`**: Shows bib assignment summary ("12/28 bibs assigned"). Primary button: "Continue Bib Assignment". Secondary: "Edit Session".
- **`ready`**: Shows "All bibs assigned". Primary button: "Start Recording". List of assigned bibs (student name + bib number).
- **`recording`/`recorded`**: Note that the user is typically in the full-screen recording flow, not here. If they navigate back, shows "Recording in progress" or "Clip recorded". Button: "Continue" to return to the flow.
- **`uploading`**: Upload progress bar with percentage. "Do not close the app" warning.
- **`queued`/`processing`**: Pipeline stage progress (see Pipeline Status screen). Link: "You can leave this screen."
- **`review`**: Summary cards: "X results to review", "Y approved", "Z flagged". Primary button: "Review Results".
- **`complete`**: Ranked result list preview. Button: "View Full Results".
- **`failed`**: Error message with reason. Buttons: "Retry Processing", "Re-record Video", "Get Help".

At the bottom, a "Delete Session" text link (only for `draft` sessions).

**Data displayed**: Session metadata, bib assignment count, clip status, pipeline stage, result summary -- from `GET /sessions/:id` with includes.

**User actions**: Context-dependent based on status. See actions listed per status above.

**Navigation**: Back to session list or home. Forward to the appropriate screen in the session flow based on status.

**State variations**:
- **Loading**: Skeleton layout.
- **Offline**: Cached session data shown if available. Actions requiring connectivity are disabled with "Offline" label.
- **Error**: "Could not load session. Tap to retry."

**Session state**: Adapts to all `TestSession.status` values.

---

### 4.8 Create Session (`/sessions/new`)

**Purpose**: Teacher selects a grade, class, and test type to create a new draft session.

**Layout description**: Full-screen modal with "X" close button top-right and "Create Session" title.

**Step 1 -- Grade**: Heading "Select Grade". Large tappable cards in a grid, one per grade configured for the school. Each card shows the grade number prominently. The list of grades is dynamic based on the school's configuration.

**Step 2 -- Class** (after grade selected): Heading updates to "Select Class". Shows classes within the selected grade as a vertical list. Each row shows: class name ("6A"), teacher name, student count. If the teacher has only one class in that grade, auto-select and skip to step 3.

**Step 3 -- Test Type** (after class selected): Heading "Select Test". A summary line at top: "Gr 6 - 6A -- 28 students". Five tappable cards in a vertical list, each with an icon, test name, attribute, and metric:
- Vertical Jump -- Explosiveness -- cm
- 5m Sprint -- Speed -- seconds
- Shuttle Run -- Fitness -- metres
- Cone Drill -- Agility -- seconds
- Single-Leg Balance -- Balance -- seconds

Tapping a test type creates the session and navigates forward.

**Data displayed**: Grades, classes per grade, student counts (from cached `GET /classes` data).

**User actions**: Tap grade, tap class, tap test type. Back button to go to previous step. Close to cancel.

**Navigation**: Close returns to previous screen (home or session list). Completing the flow navigates to `/sessions/:id/bibs`.

**State variations**:
- **Loading**: Skeleton cards (only if cache is empty and fetching).
- **Offline**: Works fully from cached class data. If cache is empty: "Class data not available offline. Connect to the internet to download your class lists before going to the field."
- **Error**: Inline error with retry if fetch fails and no cache.

**Session state**: Creates a `TestSession` in `draft` state.

---

### 4.9 Bib Assignment (`/sessions/:id/bibs`)

**Purpose**: Assign numbered bibs (1-30) to each student so the CV pipeline can map detected bib numbers to student identities.

**Layout description**: Header shows session context: "Gr 6 - 6A -- Vertical Jump". Below, a progress indicator: "14/28 bibs assigned".

Below the progress indicator, three action buttons in a horizontal row:
- "Auto-Assign" (assigns sequential bib numbers automatically)
- "Reuse Previous" (copies bib layout from the last session for this class, if one exists)
- "Clear All" (removes all assignments)

The main content is a scrollable list of students. Each row shows: student name, and either an assigned bib number (in a coloured circle, e.g. blue circle with "4") or an "Assign" button (grey dashed circle). Tapping a row or the "Assign" button opens a bib number picker -- a grid of numbers 1-30 where already-assigned numbers are greyed out.

At the bottom, a fixed footer with a primary button "Confirm Bibs" (disabled until all students have a bib assigned). The button shows the count: "Confirm Bibs (28/28)".

**Data displayed**: Student roster for the class (from `GET /classes/:id/students`, cached), current bib assignments (local state until confirmed, then `BibAssignment` records).

**User actions**: Tap student to assign/change bib number. Tap "Auto-Assign" for sequential assignment. Tap "Reuse Previous" to copy from last session. Tap "Clear All" to reset. Tap "Confirm Bibs" to finalise.

**Navigation**: Back to session detail (saves progress as draft). Forward to `/sessions/:id/preflight` on confirm.

**State variations**:
- **Partially assigned**: Progress bar partially filled. "Confirm Bibs" button disabled.
- **All assigned**: Progress bar full, green. "Confirm Bibs" button enabled and highlighted.
- **Conflict -- duplicate bib**: If a teacher tries to assign a bib that is already taken, the picker highlights the conflict: "Bib 7 is assigned to Amara Dlamini. Reassign?"
- **Offline**: Fully functional using cached student roster.
- **Reuse unavailable**: "Reuse Previous" button disabled with tooltip "No previous session for this class" if no prior session exists.

**Session state**: `draft`. Transitions to `ready` when bibs are confirmed.

---

### 4.10 Pre-flight Check (`/sessions/:id/preflight`)

**Purpose**: Live camera preview with CV readiness checks to ensure the test setup will produce usable video.

**Layout description**: Full-screen camera preview fills the entire screen. Overlaid on the camera feed, a semi-transparent panel at the top shows the session context ("Gr 6 - 6A -- Vertical Jump").

On the right side, a vertical checklist overlay with four items, each showing a label and a status icon (green checkmark or red X, updating in real time):
- "Cones visible" -- checks if calibration cones are detected
- "Students in frame" -- checks if figures are detected
- "Bibs readable" -- checks if bib numbers can be read (shows count: "24/28 readable")
- "Lighting adequate" -- checks exposure and contrast levels

At the bottom, a large circular "Start Recording" button (disabled and greyed out until all checks pass, enabled and red when ready). Below it, text: "Adjust your setup until all checks pass."

If a check fails, tapping it shows a brief tooltip with guidance (e.g. "Move closer so bib numbers fill more of the frame").

**Data displayed**: Real-time camera feed, CV check results (from on-device analysis or API frame analysis -- TBD).

**User actions**: Adjust physical setup until checks pass. Tap "Start Recording" when ready.

**Navigation**: Back to bib assignment (if teacher needs to change bibs). Forward to `/sessions/:id/record` on "Start Recording".

**State variations**:
- **Checks failing**: One or more items show red X. Record button disabled.
- **All checks passing**: All items green. Record button enabled with pulse animation.
- **Camera permission denied**: Full-screen message: "Camera access is required. Tap to open Settings." with a button to open device settings.

**Session state**: `ready`.

---

### 4.11 Recording (`/sessions/:id/record`)

**Purpose**: Capture video of the fitness test at 4K/60fps with live CV overlay.

**Layout description**: Full-screen camera feed, no chrome except overlays. At the top-left, a red recording indicator dot with elapsed time ("01:23"). At the top-right, session context in small text ("6A -- Vertical Jump").

Overlaid on the camera feed (semi-transparent):
- **Bib detection counter** at the bottom-left: "Bibs detected: 26/28" (updates in real time as the pipeline detects bib numbers).
- **Tracking indicators**: Small coloured dots or bounding box outlines around detected students (subtle, non-distracting).

At the bottom centre, a large circular "Stop" button (white circle with red square inside). The button is the only interactive element -- everything else is informational overlay.

**Data displayed**: Live camera feed, real-time bib detection count, tracking overlay, elapsed time.

**User actions**: Tap "Stop" to end recording.

**Navigation**: Forward to `/sessions/:id/review-clip` when recording stops. No back navigation during active recording (would require stopping first).

**State variations**:
- **Recording active**: Red dot pulses, timer increments, overlays update.
- **Low storage warning**: If device storage drops below threshold during recording, a banner appears: "Storage low. Recording will stop in X seconds."

**Session state**: `recording`. Transitions to `recorded` when stopped.

---

### 4.12 Clip Review (`/sessions/:id/review-clip`)

**Purpose**: Teacher reviews the recorded clip and decides whether to upload or re-record.

**Layout description**: Video player fills the top two-thirds of the screen with standard playback controls (play/pause, scrub bar, elapsed/total time). The video plays back the recorded clip.

Below the player, a "CV Quality Summary" card with three metrics in a row:
- "Students detected: 28/28" (with green/yellow/red indicator)
- "Bibs read: 26/28"
- "Quality: Good" (or "Fair" / "Poor")

Below the summary card, two buttons side by side:
- Secondary button (left): "Re-record" (outlined, with a redo icon)
- Primary button (right): "Upload" (filled, with an upload icon)

If quality is "Poor", a warning banner appears between the summary and buttons: "Video quality may affect results. Consider re-recording."

**Data displayed**: Recorded video (local file), CV quality metrics (from a quick local analysis or first-pass frame check).

**User actions**: Play/pause/scrub video. Tap "Re-record" to discard and return to pre-flight. Tap "Upload" to begin upload.

**Navigation**: "Re-record" goes back to `/sessions/:id/preflight`. "Upload" goes to `/sessions/:id/upload`.

**State variations**:
- **Good quality**: Summary shows green indicators. Both buttons available.
- **Poor quality**: Warning banner visible. "Re-record" is visually emphasised.
- **Offline**: "Upload" button changes to "Queue for Upload" with text: "Video will upload when you reconnect."

**Session state**: `recorded`.

---

### 4.13 Upload Progress (`/sessions/:id/upload`)

**Purpose**: Shows real-time progress as the video uploads directly to cloud storage via signed URL.

**Layout description**: Centred layout. At the top, the session context ("Gr 6 - 6A -- Vertical Jump"). Below, a large circular progress indicator showing percentage (e.g. "67%") with an animated ring. Below the ring, text: "Uploading video..." and "Estimated time remaining: 2m 14s". Below that, a file size indicator: "842 MB / 1.2 GB".

At the bottom, a warning message: "Please keep the app open during upload." A secondary "Cancel" text link is available but de-emphasised.

**Data displayed**: Upload percentage, bytes transferred / total, estimated time remaining.

**User actions**: Wait. Tap "Cancel" to abort upload (with confirmation dialog: "Cancel this upload? You can retry later from the Upload Queue.").

**Navigation**: Automatically advances to `/sessions/:id/pipeline` on completion. On cancel or failure, returns to session detail with the video queued locally.

**State variations**:
- **Uploading**: Progress ring animating, percentage incrementing.
- **Upload complete**: Brief success animation (checkmark), auto-navigates to pipeline status.
- **Network error**: Progress pauses. Banner: "Upload interrupted. Retrying..." with automatic retry. After 3 failed retries: "Upload failed. Your video is saved locally." with buttons "Retry Now" and "Queue for Later".
- **Offline (detected before upload starts)**: Immediately queues the video and shows: "You are offline. Video queued for upload." Button: "Go to Upload Queue".

**Session state**: `uploading`. Transitions to `queued` on successful upload confirmation.

---

### 4.14 Pipeline Status (`/sessions/:id/pipeline`)

**Purpose**: Shows stage-by-stage progress while the CV pipeline processes the uploaded video.

**Layout description**: Header with session context. Below, a vertical stepper/timeline showing the 8 pipeline stages in order. Each stage row shows:
- Stage number (1-8)
- Stage name (Ingest, Detect, Track, Pose, OCR, Calibrate, Extract, Output)
- Status icon: green checkmark (complete), blue spinner (in progress), grey circle (pending)
- For the in-progress stage, a subtle progress bar or animation

The currently active stage is visually expanded with a brief description of what is happening (e.g. "Detecting students and bibs in video frames...").

Below the stepper, informational text: "This usually takes 3-5 minutes. You can leave this screen -- we will notify you when results are ready."

At the bottom, a "Back to Home" button (secondary) so the teacher can do other things while waiting.

**Data displayed**: Pipeline job status per stage (from `GET /sessions/:id/clips/:clipId` with pipeline status, polled every 5 seconds).

**User actions**: Wait and watch progress. Tap "Back to Home" to leave. Return via push notification or session detail.

**Navigation**: Back to home (teacher can return later). Auto-navigates to `/sessions/:id/results` on pipeline success. Navigates to failed state if pipeline errors.

**State variations**:
- **Processing**: Stages advancing one by one.
- **Complete**: All 8 stages green. Brief celebration animation, then auto-navigate to results.
- **Failed**: Failed stage highlighted in red with error icon. Error message shown (e.g. "OCR stage failed: bib numbers could not be read clearly"). Buttons: "Retry Processing", "Re-record Video", "Get Help".
- **Second failure**: After a second pipeline failure on the same clip, the "Retry Processing" option is removed. Only "Re-record Video" and "Get Help" remain.

**Session state**: `queued` then `processing`. Transitions to `review` on success or `failed` on error.

---

### 4.15 Results Review (`/sessions/:id/results`)

**Purpose**: Teacher reviews CV-processed results matched to students via bib assignments, approving correct matches and fixing errors before committing to profiles.

**Layout description**: Header: "Results -- Gr 6 - 6A -- Vertical Jump". Below the header, three summary cards in a horizontal row:
- "X Tracked" (total results from pipeline, neutral colour)
- "Y High Confidence" (green)
- "Z Need Review" (orange)

Below the summary cards, a "Bulk Approve" button spanning full width: "Approve All High Confidence (Y)" -- styled as a secondary/outlined button to prevent accidental taps.

Below the button, the main content: a scrollable list of result rows. Each row shows:
- **Left**: Confidence indicator icon (green checkmark for high confidence, orange warning triangle for low confidence, red X for unresolved bib)
- **Centre**: Student name (or "Unknown" for unresolved), bib number in a small badge, and the measured value (e.g. "42 cm")
- **Right**: Action button(s) -- a checkmark button to approve, or for already-approved rows, a green "Approved" label

Rows are sorted: unresolved first, then low confidence, then high confidence (flagged items at the top for attention).

At the bottom, a fixed footer with a primary button: "Commit Results to Profiles" (disabled until all results are either approved or rejected). The button shows the count: "Commit X Results".

**Data displayed**: Pipeline results matched via bib assignments (from `GET /sessions/:id/results`). Each result includes: student name (via BibAssignment lookup), bib number, measured value, unit, confidence score, approval status.

**User actions**:
- Tap "Approve All High Confidence" to bulk-approve results with confidence > 0.8.
- Tap checkmark on individual row to approve.
- Tap a low-confidence or unresolved row to open the Result Detail modal.
- Tap "Commit Results to Profiles" to finalise.

**Navigation**: Back to session detail. Tap a row opens `/sessions/:id/results/:resultId` as a modal. "Commit" navigates to `/sessions/:id/complete`.

**State variations**:
- **Loading**: Skeleton list with placeholder rows.
- **All high confidence**: Bulk approve button is prominent. "Commit" could be enabled immediately after bulk approve.
- **Mixed confidence**: Flagged items shown at top. Teacher works through them.
- **All reviewed**: "Commit Results to Profiles" button enabled and highlighted.
- **Error**: "Could not load results. Tap to retry."

**Session state**: `review`.

---

### 4.16 Result Detail (`/sessions/:id/results/:resultId`)

**Purpose**: Detailed view of a single result for review, reassignment, or rejection.

**Layout description**: Bottom sheet modal sliding up over the results list. At the top, a drag handle and "X" close button.

The modal shows:
- **Student info**: Name (or "Unknown"), bib number, confidence score (as a percentage bar: green >80%, orange 50-80%, red <50%).
- **Measured value**: Large text showing the result (e.g. "42 cm") with the test type label.
- **Confidence details**: Brief explanation of why confidence is low (e.g. "Bib partially occluded in frames 340-890" or "OCR detected '1' but expected '7' based on position").

Below the details, three action buttons stacked vertically:
- "Approve" (green, primary) -- approves as-is.
- "Reassign to Different Student" (orange, secondary) -- opens a student picker. The picker shows the class roster with a search bar. Tapping a student reassigns this result.
- "Reject Result" (red, text/destructive) -- marks as rejected with confirmation dialog: "This result will be excluded from student profiles. Are you sure?"

**Data displayed**: Single result with confidence details, student match info (from result object).

**User actions**: Approve, reassign (with student picker), or reject.

**Navigation**: Close returns to results list. Student picker is an inline sub-view within the modal.

**State variations**:
- **High confidence**: "Approve" is emphasised. Reassign/Reject available but de-emphasised.
- **Low confidence**: Warning colour scheme. Reassign is emphasised.
- **Unresolved bib**: "Unknown" shown for student name. "Reassign" is the primary action. "Approve" is hidden (cannot approve without a student).

**Session state**: `review`.

---

### 4.17 Session Complete (`/sessions/:id/complete`)

**Purpose**: Displays final ranked results after the teacher has committed approved results to student profiles.

**Layout description**: A celebration header with a checkmark icon and "Session Complete" title. Below, the session context: "Gr 6 - 6A -- Vertical Jump -- [date]".

Below the header, a summary bar: "X results committed."

The main content is a ranked list (numbered 1 through N). Each row shows:
- **Rank number** (1, 2, 3...) in a circle
- **Student name** and bib number
- **Measured value** (e.g. "48 cm")
The list is sorted by measured value (best to worst, adjusted for test type -- higher is better for jump, lower is better for sprint time).

At the bottom, two buttons:
- "New Session for This Class" (primary) -- starts another test for the same class
- "Done" (secondary) -- returns to home

**Data displayed**: Committed results (from `GET /sessions/:id/results?status=approved`).

**User actions**: Tap a student row to view their full profile. Tap "New Session" to start another test. Tap "Done" to go home.

**Navigation**: Tap student goes to `/students/:id`. "New Session" goes to `/sessions/new` (pre-populated with same class). "Done" goes to `/home`.

**State variations**:
- **Loading**: Skeleton list while results load.

**Session state**: `complete`.

---

### 4.18 Upload Queue (`/upload-queue`)

**Purpose**: Shows all queued, in-progress, and recently completed uploads. Critical for offline workflows where multiple sessions are recorded before connectivity is available.

**Layout description**: Header "Upload Queue" with a sync icon that animates when uploads are active. Below the header, a status banner:
- If online and uploading: "Uploading... X of Y" with overall progress.
- If online and idle: "All uploads complete" (green).
- If offline: "You are offline. Uploads will resume when you reconnect." (orange banner).

Below the banner, a list of upload items. Each item shows:
- Session context (class + test type)
- File size (e.g. "1.2 GB")
- Status: "Queued" (grey), "Uploading -- 34%" (blue with progress bar), "Complete" (green checkmark), "Failed" (red with retry button)
- Timestamp (when recorded)

Items are sorted: uploading first, then queued, then failed, then complete.

At the bottom, device storage summary: "3.4 GB used by Vigour / 12 GB free on device". If storage is critically low, a red warning: "Storage low. Upload or delete queued videos."

**Data displayed**: Local upload queue state (persisted in local storage), device storage metrics.

**User actions**: Tap a failed item to retry. Swipe to delete a queued item (with confirmation). Tap a completed item to go to its session.

**Navigation**: Tap completed item goes to `/sessions/:id`. Tab bar navigation to other tabs.

**State variations**:
- **Empty**: "No uploads in queue. Record a session to get started."
- **All complete**: Green header. List shows recent completions.
- **Offline with items**: Orange banner. Items show "Queued" status.
- **Upload in progress**: Active item shows animated progress bar. Others show "Waiting".
- **Failed items**: Red badge on tab bar icon. Failed items prominent at top with "Retry" button.

**Session state**: Covers sessions in `recorded`, `uploading`, and `queued` states.

---

### 4.19 Student Profile (`/students/:id`)

**Purpose**: Individual student fitness history accessible from results screens. Shows per-test results and trends over time.

**Layout description**: Back arrow top-left. Header area with student name, grade, class, and a change indicator: "+8 vs last term" (green arrow up) or "-3 vs last term" (red arrow down).

Below the header, a horizontal row of 5 small stat cards, one per test domain:
- Explosiveness: 42 cm
- Speed: 1.12s
- Fitness: 38m
- Agility: 4.2s
- Balance: 18s

Each card shows a small trend arrow (up/down/flat).

Below the stat cards, a section "History" with a line chart showing test results across terms (T1, T2, T3, etc.). The x-axis is terms, the y-axis is the result value.

Below the chart, a list of "Recent Test Results" showing individual session results in reverse chronological order. Each row: date, test type, measured value.

**Data displayed**: Student profile, per-test results, historical results across terms, recent individual results (from `GET /students/:id` with result and history includes).

**User actions**: Scroll through history. Tap a test result row to see session details. Tap a domain card to see detailed history for that test type.

**Navigation**: Back to previous screen (results list or home). Tap result row goes to session detail.

**State variations**:
- **Loading**: Skeleton layout.
- **No history**: "No test results yet for this student." (new student who has not been tested).
- **Offline**: Cached data shown if previously loaded. "Connect to see latest data."
- **Error**: "Could not load student profile. Tap to retry."

**Session state**: N/A (cross-session view).

---

### 4.20 Settings (`/settings`)

**Purpose**: Access to account management, notification preferences, offline data management, and help.

**Layout description**: Standard settings list layout. Header "Settings". Grouped list sections:

**Account section**:
- Row: Teacher name and email (tap to go to account details)
- Row: School name (non-interactive, informational)

**Preferences section**:
- Row: "Notifications" with chevron (tap to manage push notification settings)

**Data & Storage section**:
- Row: "Offline Data" with storage usage summary (e.g. "2.1 GB") and chevron
- Row: "Video Quality" with current setting (e.g. "4K / 60fps") and chevron

**Support section**:
- Row: "Help & Troubleshooting" with chevron
- Row: "Contact Support" with chevron

**About section**:
- Row: "About Vigour" with app version number
- Row: "Terms of Service" (opens web view)
- Row: "Privacy Policy" (opens web view)

**Sign Out** section:
- Row: "Sign Out" in red text

**Data displayed**: Teacher name, email, school name, storage usage, app version.

**User actions**: Tap any row to navigate to the relevant sub-screen. Tap "Sign Out" to log out (with confirmation dialog).

**Navigation**: To sub-screens within settings. "Sign Out" returns to `/welcome`.

**State variations**:
- **Offline**: All rows visible. Network-dependent actions (contact support, sign out) show offline note.

**Session state**: N/A.

---

### 4.21 Account Settings (`/settings/account`)

**Purpose**: View and manage account details.

**Layout description**: Back arrow, header "Account". Read-only fields: name, email, role ("Teacher"), school name. At the bottom, "Sign Out" button.

**Data displayed**: User profile from `GET /me`.

**User actions**: View info. Tap "Sign Out".

**Navigation**: Back to settings.

**State variations**: Standard loading/error.

**Session state**: N/A.

---

### 4.22 Notification Settings (`/settings/notifications`)

**Purpose**: Configure which push notifications the teacher receives.

**Layout description**: Back arrow, header "Notifications". Toggle rows:
- "Pipeline complete" -- on/off (default: on)
- "Pipeline failed" -- on/off (default: on)
- "Session reminders" -- on/off (default: off, future)

If push notifications are disabled at the OS level, a banner at top: "Notifications are disabled. Tap to open device settings." with a button.

**Data displayed**: Current notification preference state.

**User actions**: Toggle notification types. Tap OS settings prompt if needed.

**Navigation**: Back to settings.

**State variations**:
- **Notifications disabled at OS level**: Warning banner.
- **Offline**: Settings are local -- toggles work offline and sync later.

**Session state**: N/A.

---

### 4.23 Offline Data (`/settings/offline`)

**Purpose**: Manage cached data and local storage used by the app.

**Layout description**: Back arrow, header "Offline Data". Sections:

**Storage Usage**: A visual bar showing storage breakdown:
- Queued videos: X GB
- Cached class data: X MB
- Cached results: X MB
- Total: X GB / X GB available

**Cache Management**:
- Row: "Sync Class Data Now" with a refresh icon (downloads latest class/student rosters for offline use)
- Row: "Last synced: [date/time]"
- Row: "Clear Cache" (red text, clears cached data but NOT queued uploads -- with confirmation: "This will clear cached class and result data. Queued uploads will not be affected.")

**Queued Uploads**:
- Row: "X videos queued (Y GB)" with chevron (navigates to Upload Queue tab)

**Data displayed**: Local storage metrics, cache timestamps, queued upload count.

**User actions**: Tap "Sync Class Data Now" to refresh cache. Tap "Clear Cache" to free space. Tap queued uploads to go to queue.

**Navigation**: Back to settings. Tap queued uploads goes to `/upload-queue`.

**State variations**:
- **Offline**: "Sync Class Data Now" disabled with note "Connect to sync."
- **No cached data**: "No data cached. Sync your classes before going to the field."

**Session state**: N/A.

---

### 4.24 About (`/settings/about`)

**Purpose**: App version, legal links, licences.

**Layout description**: Back arrow, header "About". Vigour logo centred. App name "Vigour Teacher" and version number (e.g. "v1.2.0 (build 45)"). Below, rows for "Terms of Service", "Privacy Policy", "Open Source Licences" -- each opens a web view or in-app text screen.

**Data displayed**: Static content and build metadata.

**User actions**: Tap legal links.

**Navigation**: Back to settings. Links open web views.

**State variations**: Static -- always available, even offline (content bundled with app).

**Session state**: N/A.

---

### 4.25 Help & Support (`/help`)

**Purpose**: Self-service troubleshooting and path to contact support.

**Layout description**: Back arrow, header "Help". A search bar at the top: "Search for help...".

Below, a section "Common Issues" with expandable FAQ-style rows:
- "Bibs are not being detected during pre-flight"
- "Video upload keeps failing"
- "Pipeline processing failed"
- "I cannot see my classes"
- "How to re-record a session"

Each row expands to show a brief answer with actionable steps and illustrations.

Below the FAQ section, a section "Still need help?" with a card containing a "Contact Support" button.

**Data displayed**: Static help content (bundled with app, may be supplemented by server-fetched articles).

**User actions**: Search, expand FAQ items, tap "Contact Support".

**Navigation**: Back to settings. "Contact Support" goes to `/help/contact`.

**State variations**:
- **Offline**: Bundled FAQ content available. "Contact Support" shows "Available when online."

**Session state**: N/A.

---

### 4.26 Contact Support (`/help/contact`)

**Purpose**: Submit a pre-filled support ticket with session and device context.

**Layout description**: Back arrow, header "Contact Support". The form is partially pre-filled:
- **Session** (dropdown): Select a session to attach context (auto-selected if navigating from a failed session). Shows session ID, class, test type, and error details.
- **Issue type** (dropdown): "Pipeline failure", "Upload issue", "Bib assignment problem", "Other".
- **Description** (text area): Free-form text input for the teacher to describe the issue.
- **Attachments**: Auto-attached device info (device model, OS version, app version), session ID, error logs if applicable. A "Add screenshot" button to attach a photo.

At the bottom, a primary button "Submit".

**Data displayed**: Pre-filled session context (if applicable), device metadata.

**User actions**: Select session, select issue type, type description, optionally add screenshot, submit.

**Navigation**: Back to help. On submit, shows a confirmation: "Support request submitted. Our team will respond within 24 hours." with a "Done" button back to home.

**State variations**:
- **Offline**: "Support requests require an internet connection." with a "Save Draft" option that queues the request.
- **Loading**: Submit button shows spinner.
- **Error**: "Could not submit. Tap to retry."

**Session state**: N/A.

---

## 5. Offline Behaviour

### Which Screens Work Offline

| Screen | Offline Support | Detail |
|---|---|---|
| Welcome, About, Help (FAQ) | Full | Static content bundled with app |
| Home Dashboard | Partial | Shows cached classes and sessions. New data requires connectivity. |
| Session List | Partial | Shows cached sessions. Status updates require connectivity. |
| Create Session | Full | Uses cached class lists. Creates session locally. |
| Bib Assignment | Full | Uses cached student rosters. Saves assignments locally. |
| Pre-flight Check | Full | Camera-only. CV checks run on-device or are skipped offline. |
| Recording | Full | Video saved to device storage. No network needed. |
| Clip Review | Full | Plays back local video file. |
| Upload Progress | No | Requires network. Queues video locally if offline. |
| Upload Queue | Full | Shows local queue state and storage usage. |
| Pipeline Status | No | Requires polling the API. |
| Results Review | No | Results come from the API after pipeline processing. |
| Session Complete | Partial | Cached after first load. |
| Student Profile | Partial | Cached after first load. |
| Settings | Partial | Local settings work. Sync and sign-out need connectivity. |
| Offline Data | Full | Manages local storage. Sync button needs connectivity. |
| Contact Support | No | Submission requires network. Can save draft locally. |

### What Data Is Cached and When

| Data | Cached When | Cache Duration |
|---|---|---|
| Class list (teacher's assigned classes) | On login, on manual sync, on app foreground after 1 hour stale | Until next sync or manual clear |
| Student roster per class | On login, on manual sync, when entering bib assignment | Until next sync or manual clear |
| Session list and status | On each fetch (background refresh on app foreground) | 24 hours, or until explicitly refreshed |
| Recent results (completed sessions) | On first view of session complete / student profile | 24 hours |
| Bib assignments (in-progress sessions) | Immediately as teacher assigns bibs | Until session is completed or deleted |
| Recorded video files | Immediately on recording stop | Until upload confirmed by server, then deletable |

### Upload Queue Mechanics

1. **Queue creation**: When a teacher taps "Upload" and the network is unavailable (or when an upload fails after retries), the video is added to a persistent local queue stored via `expo-file-system` / AsyncStorage.

2. **Queue persistence**: The queue survives app restarts, phone reboots, and app updates. Each queue item stores: session ID, clip ID (if already created server-side), local file path, file size, recording timestamp, retry count.

3. **Auto-resume**: When the app detects network connectivity (via `NetInfo`), it begins processing the queue automatically -- oldest first, one upload at a time to avoid bandwidth contention.

4. **Upload flow per item**:
   - If no clip ID exists: call `POST /sessions/:id/clips` to create a Clip record and get a signed upload URL.
   - Upload video directly to GCS via the signed URL with resumable upload protocol.
   - On completion: call `PATCH /sessions/:id/clips/:clipId` to confirm upload and trigger pipeline.
   - On failure: increment retry count, wait with exponential backoff (30s, 1m, 2m, 5m), retry.

5. **Retry limits**: After 5 consecutive failures for a single item, it is marked as "Failed" and requires manual retry. The teacher sees this in the Upload Queue screen.

6. **Background upload**: On iOS, the app uses background fetch and background URL session to continue uploads when the app is backgrounded. On Android, it uses a foreground service with a persistent notification showing upload progress.

7. **Storage management**: The app tracks total storage used by queued videos. When device storage drops below 1 GB free, a warning is shown. The teacher is encouraged to find connectivity and clear the queue before recording more sessions.

8. **Conflict handling**: If the same session's clip is somehow uploaded from another device (edge case), the server rejects the duplicate confirmation. The queue item is marked as "Already uploaded" and the local file can be deleted.

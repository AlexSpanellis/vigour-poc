# Session, Run, and Clip Terminology — Model B

## Purpose
Visualize the hierarchical relationship between Sessions, Runs (batches of students), Clips (video recordings), Bib Assignments, and Results in the Vigour fitness testing platform. This is "Model B" where runs are clips within one session, giving unified class-level aggregation.

## Scenario to Illustrate

**Setup**: Mrs. van Wyk is testing Class 6A (24 students) on Vertical Jump. The system is configured for max 8 students per run.

### Hierarchy (top to bottom)

```
TestSession: "Gr 6A — Vertical Jump"
├── Bib Assignments (24 students, assigned once for the whole session)
│   ├── #01 → Liam van der Berg
│   ├── #02 → Keenan Jacobs
│   ├── #03 → Ruan Botha
│   ├── ... (24 total)
│   └── #24 → Chloé Pretorius
│
├── Run 1 / Clip 1 (video_001.mp4)
│   ├── Students: #01-#08 (Liam, Keenan, Ruan, Zara, Amara, Thabo, Sarah, Naledi)
│   ├── Pipeline Job: job-abc-001
│   ├── Results: 8 results extracted
│   │   ├── Result: Liam #01 → 42cm (High confidence)
│   │   ├── Result: Keenan #02 → 45cm (High confidence)
│   │   └── ... 6 more
│   └── Status: complete
│
├── Run 2 / Clip 2 (video_002.mp4)
│   ├── Students: #09-#16 (next 8 students)
│   ├── Pipeline Job: job-abc-002
│   ├── Results: 8 results extracted
│   └── Status: complete
│
└── Run 3 / Clip 3 (video_003.mp4)
    ├── Students: #17-#24 (final 8 students)
    ├── Pipeline Job: job-abc-003
    ├── Results: 8 results extracted
    └── Status: complete
```

### Key Points to Visualize

1. **Session** = one class + one test type. Created once. Contains ALL bib assignments for the class.

2. **Bib Assignment** = permanent for the session. Student keeps same bib across all runs. Assigned at session setup, before any recording.

3. **Run / Clip** = one video recording of a batch of students performing the test. Each run has:
   - A subset of the class (determined by configurable batch size, e.g., 8)
   - Its own video file
   - Its own pipeline job
   - Its own set of raw results

4. **Result** = extracted from a clip, linked to both the clip AND the session. The bib number in the video maps back to the student via the session-level BibAssignment.

5. **Aggregation** = Results from ALL clips roll up to the session level. The teacher reviews all 24 results together on one screen, not per-clip.

### Teacher Workflow (show as a timeline/swimlane)

```
SESSION SETUP
  ↓ Select class (6A) and test (Vertical Jump)
  ↓ Assign bibs to all 24 students (once)
  ↓ Session status: "ready"

RUN 1
  ↓ Teacher calls students #01-#08 to the testing area
  ↓ Pre-flight check → Record video → Stop
  ↓ Clip 1 saved locally
  ↓ App shows: "Run 1 complete. 8/24 students recorded."

RUN 2
  ↓ Teacher calls students #09-#16
  ↓ Pre-flight check → Record video → Stop
  ↓ Clip 2 saved locally
  ↓ App shows: "Run 2 complete. 16/24 students recorded."

RUN 3
  ↓ Teacher calls students #17-#24
  ↓ Pre-flight check → Record video → Stop
  ↓ Clip 3 saved locally
  ↓ App shows: "Run 3 complete. 24/24 students recorded. Ready to upload."

UPLOAD
  ↓ All 3 clips uploaded (sequentially or in parallel)
  ↓ 3 pipeline jobs submitted
  ↓ Teacher can leave — notified when all complete

REVIEW
  ↓ All 24 results shown on one screen
  ↓ Teacher reviews, approves, resolves conflicts
  ↓ Commits results to student profiles
  ↓ Session status: "complete"
```

### Schema Change Required
Show the updated BibAssignment and Clip relationship:
- BibAssignment stays at session level (no clip_id needed — bibs are session-wide)
- Result gets clip_id FK (already has it) — this is how we know which clip produced which result
- The pipeline reads bib #05 in clip 2 → looks up session's BibAssignment where bib_number=5 → resolves to student

### Visual Style
- Use a clear hierarchical/tree layout
- Color-code: Session (blue), Runs/Clips (orange), Results (green), Students (purple)
- Show the configurable batch size as a setting icon (e.g., "max_students_per_run: 8")
- Include the teacher workflow as a vertical timeline on the right side
- Make it clear that bibs are assigned ONCE and reused across all runs

# 09 - Coach: Reviewing Student Progress

**Tool**: `gemini --yolo "/diagram '...'"`
**Generated**: 2026-03-24

## Prompt

```
Coach Reviewing Student Progress - User Flow diagram.

Flow (top to bottom):
1. Coach opens Coach Dashboard (React SPA) in browser → Decision: Already logged in? If no, sign in via ZITADEL. If yes, go to Dashboard.
2. Dashboard showing Grade 6 Term 1 Results: 28 Tested, 38cm Avg Jump, 1.18s Avg Sprint, 19/28 Improved
3. Navigation options: Class Leaderboard, Student List, Sessions, Export
4. Class Leaderboard - sortable table: rank, student name, bib, score, attendance, vs last session. Can sort by any column.
5. Click student name → Student Detail Profile: overall score 72, +8 vs last, 80% attendance. Per-test breakdown with trend lines for Jump, Sprint, Fitness, Agility, Balance. Jump history bar chart T1-T5.
6. Options: Historical trends (term-over-term test result progression), Per-test detail (individual test history), Back to class
7. Decision: Student declining? If yes → coach notes student for teacher discussion (read-only, no in-app flagging). If no → back to profile.
8. Export section: CSV export (raw data)

Note: Student names are resolved via Tier 2 API (identity schema enrichment) — dashboard only receives anonymised IDs until enrichment.

Clean web dashboard style, blue/teal color scheme, data visualization elements.
```

## Regenerate

```bash
cd docs/architecture/diagrams
GEMINI_API_KEY="$NANOBANANA_GEMINI_API_KEY" gemini --yolo "/diagram 'Coach Reviewing Student Progress - User Flow diagram.

Flow (top to bottom):
1. Coach opens Coach Dashboard (React SPA) in browser → Decision: Already logged in? If no, sign in via ZITADEL. If yes, go to Dashboard.
2. Dashboard showing Grade 6 Term 1 Results: 28 Tested, 38cm Avg Jump, 1.18s Avg Sprint, 19/28 Improved
3. Navigation options: Class Leaderboard, Student List, Sessions, Export
4. Class Leaderboard - sortable table: rank, student name, bib, score, attendance, vs last session. Can sort by any column.
5. Click student name → Student Detail Profile: overall score 72, +8 vs last, 80% attendance. Per-test breakdown with trend lines for Jump, Sprint, Fitness, Agility, Balance. Jump history bar chart T1-T5.
6. Options: Historical trends (term-over-term test result progression), Per-test detail (individual test history), Back to class
7. Decision: Student declining? If yes → coach notes student for teacher discussion (read-only, no in-app flagging). If no → back to profile.
8. Export section: CSV export (raw data)

Note: Student names are resolved via Tier 2 API (identity schema enrichment) — dashboard only receives anonymised IDs until enrichment.

Clean web dashboard style, blue/teal color scheme, data visualization elements.'"
```

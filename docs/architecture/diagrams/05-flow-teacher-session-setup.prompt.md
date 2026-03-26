# 05 - Teacher: Session Setup and Recording

**Tool**: `gemini --yolo "/diagram '...'"`
**Generated**: 2026-03-24

## Prompt

```
Teacher Complete Session Workflow - Part 1: Setup and Recording. User flow diagram from teacher perspective.

Flow (top to bottom):
1. Teacher opens app → Home Screen (class list, recent sessions)
2. Taps New Session → Session Setup (select grade from school's configured grades)
3. Selects grade and class (e.g. Gr6-6A) → Test Selection screen showing class info and 5 test options: Explosiveness (Vertical Jump), Speed (5m Sprint), Fitness (Shuttle), Agility (Cone Drill), Balance (Single-Leg)
4. Selects test → Session created (draft state)
5. Bib Assignment Screen - list of students, each assigned a bib number (configurable). Three options: Manual assign, Auto-assign (sequential), Reuse Previous
6. Review bib list → All assigned? If no, back to assignment. If yes, Confirm Bibs
7. Session moves to ready state, BibAssignment records created
8. Consent Verification - system checks all bib-assigned students have active VIDEO_CAPTURE + METRIC_PROCESSING consent. If any missing → alert teacher, block recording until resolved
9. Pre-flight Check Screen - live camera with overlays: Cones visible, Students in frame, Bibs readable, Lighting adequate
10. All checks pass? If no, teacher adjusts setup. If yes, Start Recording
11. Recording Screen - live camera 60fps/4K with bib detection count, tracking indicators, elapsed time
12. Stop Recording → Session recorded state, video saved locally
13. Clip Review Screen - playback with CV quality summary: Students detected 28/28, Bibs read 26/28, Quality Good
14. Decision: Accept clip? If no, re-record (back to pre-flight). If yes, Upload

Use rounded rectangles for user actions, regular rectangles for screens, diamonds for decisions, hexagons for system responses. Green/blue modern color scheme. Professional clean layout.
```

## Regenerate

```bash
cd docs/architecture/diagrams
GEMINI_API_KEY="$NANOBANANA_GEMINI_API_KEY" gemini --yolo "/diagram 'Teacher Complete Session Workflow - Part 1: Setup and Recording. User flow diagram from teacher perspective.

Flow (top to bottom):
1. Teacher opens app → Home Screen (class list, recent sessions)
2. Taps New Session → Session Setup (select grade from school's configured grades)
3. Selects grade and class (e.g. Gr6-6A) → Test Selection screen showing class info and 5 test options: Explosiveness (Vertical Jump), Speed (5m Sprint), Fitness (Shuttle), Agility (Cone Drill), Balance (Single-Leg)
4. Selects test → Session created (draft state)
5. Bib Assignment Screen - list of students, each assigned a bib number (configurable). Three options: Manual assign, Auto-assign (sequential), Reuse Previous
6. Review bib list → All assigned? If no, back to assignment. If yes, Confirm Bibs
7. Session moves to ready state, BibAssignment records created
8. Consent Verification - system checks all bib-assigned students have active VIDEO_CAPTURE + METRIC_PROCESSING consent. If any missing → alert teacher, block recording until resolved
9. Pre-flight Check Screen - live camera with overlays: Cones visible, Students in frame, Bibs readable, Lighting adequate
10. All checks pass? If no, teacher adjusts setup. If yes, Start Recording
11. Recording Screen - live camera 60fps/4K with bib detection count, tracking indicators, elapsed time
12. Stop Recording → Session recorded state, video saved locally
13. Clip Review Screen - playback with CV quality summary: Students detected 28/28, Bibs read 26/28, Quality Good
14. Decision: Accept clip? If no, re-record (back to pre-flight). If yes, Upload

Use rounded rectangles for user actions, regular rectangles for screens, diamonds for decisions, hexagons for system responses. Green/blue modern color scheme. Professional clean layout.'"
```

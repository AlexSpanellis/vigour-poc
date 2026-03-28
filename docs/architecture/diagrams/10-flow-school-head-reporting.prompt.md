# 10 - School Head: Term Reporting

**Tool**: `gemini --yolo "/diagram '...'"`
**Generated**: 2026-03-24

## Prompt

```
School Head Term Reporting - User Flow diagram.

Flow (top to bottom):
1. School head opens School Head Dashboard (React SPA) → Decision: Logged in? If no, sign in. If yes, go to Overview.
2. School Overview: Term 1 2026, 341 students, summary cards: 341 Students, 57/100 School Score, 83% Participation, 68% Improved, 12 At-Risk
3. Navigation: Grades, At-Risk, Admin
4. Grades path: Grade Breakdown (one row per grade from school config, showing avg score and participation rate) → Click grade → Class Comparison (e.g. 6A: 58, 6B: 55, 6C: 61 with bar charts) → Click class → Class Detail (teacher, average, participation, per-student table)
5. At-Risk path: At-Risk Alerts showing 3 declining students with test result trends → Click student → Student Profile with decline highlighted → Options: discuss with teacher, back to list
6. Data is viewable on dashboards — no report generation
7. Test Score overview: Avg by test across all grades showing Explosiveness 58, Speed 62, Fitness 51, Agility 55, Balance 48 → Identify school-wide weakness (Balance lowest)

Note: Student names are resolved via Tier 2 API (identity schema enrichment) — dashboard only receives anonymised IDs until enrichment. K-anonymity: class-level reports suppress groups smaller than k=5 to prevent individual identification.

Professional dashboard style, warm color scheme, clear hierarchy.
```

## Regenerate

```bash
cd docs/architecture/diagrams
GEMINI_API_KEY="$NANOBANANA_GEMINI_API_KEY" gemini --yolo "/diagram 'School Head Term Reporting - User Flow diagram.

Flow (top to bottom):
1. School head opens School Head Dashboard (React SPA) → Decision: Logged in? If no, sign in. If yes, go to Overview.
2. School Overview: Term 1 2026, 341 students, summary cards: 341 Students, 57/100 School Score, 83% Participation, 68% Improved, 12 At-Risk
3. Navigation: Grades, At-Risk, Admin
4. Grades path: Grade Breakdown (one row per grade from school config, showing avg score and participation rate) → Click grade → Class Comparison (e.g. 6A: 58, 6B: 55, 6C: 61 with bar charts) → Click class → Class Detail (teacher, average, participation, per-student table)
5. At-Risk path: At-Risk Alerts showing 3 declining students with test result trends → Click student → Student Profile with decline highlighted → Options: discuss with teacher, back to list
6. Data is viewable on dashboards — no report generation
7. Test Score overview: Avg by test across all grades showing Explosiveness 58, Speed 62, Fitness 51, Agility 55, Balance 48 → Identify school-wide weakness (Balance lowest)

Note: Student names are resolved via Tier 2 API (identity schema enrichment) — dashboard only receives anonymised IDs until enrichment. K-anonymity: class-level reports suppress groups smaller than k=5 to prevent individual identification.

Professional dashboard style, warm color scheme, clear hierarchy.'"
```

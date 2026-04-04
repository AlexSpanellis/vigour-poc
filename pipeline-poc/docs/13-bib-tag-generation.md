# Bib Tag Generation — ArUco Markers with Calibration Strips

## What This Is

A script that generates printable bib tags for Vigour Test. Each tag contains:

1. **ArUco marker** (8cm × 8cm) — machine-readable ID + known physical size for per-student camera calibration
2. **Bib number** (large human-readable text) — visible to the teacher during testing
3. **Calibration strip** (alternating 1cm black/white segments) — fallback scale reference if ArUco detection fails

The ArUco marker serves dual purpose:
- **Student identification**: marker ID encodes the bib number (faster + more reliable than OCR)
- **Per-student calibration**: known marker size (8cm) → compute pixels-per-cm at each student's depth

## Quick Start

```bash
cd pipeline-poc

# Generate 100 bibs (#1–#100)
python scripts/generate_bib_tags.py

# Generate 60 bibs starting from #1
python scripts/generate_bib_tags.py --count 60

# Generate 200 bibs (needs larger dictionary)
python scripts/generate_bib_tags.py --count 200 --dictionary DICT_4X4_250

# Custom marker size (10cm instead of 8cm)
python scripts/generate_bib_tags.py --marker-cm 10
```

## Output Structure

```
bib_tags/
├── individual/          ← one PNG per bib (300 DPI, exact physical size)
│   ├── bib_001.png
│   ├── bib_002.png
│   └── ...
├── sheets/              ← A4 print sheets (4 tags per page, crop marks)
│   ├── sheet_001.png
│   ├── sheet_002.png
│   └── ...
└── manifest.json        ← bib↔ArUco mapping + student assignments
```

### Individual Tags

Each PNG is 12cm × 16cm at 300 DPI (1417 × 1890 pixels). Print at 100% scale — do not resize. The physical dimensions are calibrated: the 8cm marker must print at exactly 8cm for calibration to work.

### Print Sheets

A4 pages with 4 tags each, arranged in a 2×2 grid with crop marks. Print on A4 paper, cut along the marks.

### Manifest

JSON file mapping bib numbers to ArUco IDs and tracking student assignments:

```json
{
  "dictionary": "DICT_4X4_100",
  "marker_size_cm": 8.0,
  "bibs": [
    {
      "bib_number": 1,
      "aruco_id": 0,
      "file": "individual/bib_001.png",
      "student_name": null,
      "assigned_date": null
    }
  ]
}
```

## Assigning Students to Bibs

### Single assignment

```bash
python scripts/generate_bib_tags.py --assign manifest.json 7 "Liam van der Berg"
```

### Bulk assignment from CSV

```bash
python scripts/generate_bib_tags.py --assign-csv manifest.json roster.csv
```

CSV format:
```csv
bib_number,student_name
1,Liam van der Berg
2,Thandi Nkosi
3,Ruan Botha
```

### List current assignments

```bash
python scripts/generate_bib_tags.py --list manifest.json
```

Output:
```
  Bib  ArUco ID  Student                         Assigned
---------------------------------------------------------------------------
  #001         0  Liam van der Berg               2026-04-01
  #002         1  (unassigned)
  #003         2  Ruan Botha                      2026-04-01
```

## Printing Instructions

1. **Paper**: Use standard white A4 paper (80gsm minimum). For durability, use cardstock (160–200gsm) or laminate after printing.
2. **Print settings**: 100% scale (no fit-to-page). 300 DPI. Black & white is sufficient.
3. **Verify scale**: After printing, measure the ArUco marker with a ruler. It must be exactly 8cm × 8cm. If it's not, check your printer's scale settings.
4. **Cut**: Cut along crop marks on the print sheets, or print individual tags and trim to the border.
5. **Attach**: Pin or velcro to the student's chest. The tag must lay flat — wrinkles degrade ArUco detection.

## How the Pipeline Uses These Tags

### ArUco Detection (replaces OCR as primary ID)

```python
import cv2

aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_100)
detector = cv2.aruco.ArucoDetector(aruco_dict)
corners, ids, _ = detector.detectMarkers(frame)

# ids[i] = ArUco marker ID = bib_number - 1
# corners[i] = 4 corner points in pixel space
```

### Per-Student Calibration

```python
# Marker side length in pixels (average of 4 edges)
side_px = np.mean([np.linalg.norm(corners[0][j+1] - corners[0][j]) for j in range(3)]
                   + [np.linalg.norm(corners[0][0] - corners[0][3])])

# Known physical size
marker_cm = 8.0

# Per-student scale
pixels_per_cm = side_px / marker_cm
```

### Which Tests Use ArUco Calibration

| Test | Camera | ArUco visible? | Used for |
|------|--------|---------------|----------|
| Explosiveness | Front-facing | Yes | ID + per-student px/cm calibration |
| Balance | Front-facing | Yes | ID only (no spatial calibration needed) |
| Sprint | 45° angle | Partially | ID (calibration from cones) |
| Mobility | Side-on | No | ID only when student faces camera briefly |
| Agility | Behind | No | ID from walk-up; calibration from cones |
| Fitness | Behind | No | ID from walk-up; calibration from cones |
| Coordination | Behind | No | ID from walk-up; calibration from cones |

## ArUco Dictionary Choice

| Dictionary | Max IDs | Internal grid | Detection range | Use when |
|-----------|---------|--------------|----------------|----------|
| `DICT_4X4_100` (default) | 100 | 4×4 | Best (largest cells) | ≤100 bibs |
| `DICT_4X4_250` | 250 | 4×4 | Best | ≤250 bibs |
| `DICT_5X5_100` | 100 | 5×5 | Good | Better error correction needed |
| `DICT_6X6_250` | 250 | 6×6 | Moderate | Very high bib count + error correction |

**Recommendation**: `DICT_4X4_100` for most schools. The 4×4 grid has the largest internal cells, giving the best detection range and reliability. Only switch to `DICT_4X4_250` if you need more than 100 bibs.

## Tag Physical Specifications

| Property | Value |
|----------|-------|
| Tag size | 12cm × 16cm |
| ArUco marker | 8cm × 8cm |
| ArUco quiet zone (white border) | 1.5cm around marker |
| Calibration strip | 10cm wide, 1cm tall, 1cm segments |
| Bib number font | ~1.8cm cap height (visible at 5m) |
| Print DPI | 300 |
| ArUco dictionary | DICT_4X4_100 (configurable) |
| Marker ID encoding | ArUco ID 0 = bib #1, ID 1 = bib #2, etc. |

## Customisation

```bash
# Larger marker for better long-range detection
python scripts/generate_bib_tags.py --marker-cm 10 --tag-width-cm 14 --tag-height-cm 18

# Start numbering from 51 (second batch)
python scripts/generate_bib_tags.py --count 50 --start-bib 51

# Different output directory
python scripts/generate_bib_tags.py --output-dir /path/to/output
```

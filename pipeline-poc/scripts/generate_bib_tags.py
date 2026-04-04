#!/usr/bin/env python3
"""
Generate printable ArUco bib tags with calibration strips for Vigour Test.

Each tag contains:
  - ArUco marker (known physical size → per-student px/cm calibration)
  - Human-readable bib number (large, visible to teacher)
  - Calibration strip (alternating black/white 1 cm segments → fallback scale)

Output:
  <output_dir>/
    individual/        ← one PNG per bib (300 DPI, exact physical size)
    sheets/            ← print-ready A4 pages (4 tags per sheet, crop marks)
    manifest.json      ← mapping of bib numbers → ArUco IDs, file paths

Usage:
  python generate_bib_tags.py                          # 100 bibs, default output
  python generate_bib_tags.py --count 60 --start-bib 1
  python generate_bib_tags.py --count 100 --marker-cm 8 --output-dir ./bib_tags
  python generate_bib_tags.py --assign manifest.json 7 "Liam van der Berg"

Dictionary: DICT_4X4_100 (100 unique IDs, 4×4 internal grid, best detection range).
For >100 bibs, use --dictionary DICT_4X4_250.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Physical dimensions (cm) — change these to resize the tag
# ---------------------------------------------------------------------------
DEFAULT_MARKER_CM = 8.0        # ArUco marker side length
DEFAULT_TAG_WIDTH_CM = 12.0    # total tag width
DEFAULT_TAG_HEIGHT_CM = 16.0   # total tag height
STRIP_SEGMENT_CM = 1.0         # calibration strip segment width
STRIP_HEIGHT_CM = 1.0          # calibration strip height
BORDER_CM = 1.5                # white border around marker (ArUco needs ≥1 cell)
DPI = 300                      # print resolution

# A4 dimensions (cm)
A4_WIDTH_CM = 21.0
A4_HEIGHT_CM = 29.7
A4_MARGIN_CM = 1.0             # margin around the printable area
CROP_MARK_CM = 0.5             # crop mark length

# ArUco dictionaries
ARUCO_DICTS = {
    "DICT_4X4_50":   cv2.aruco.DICT_4X4_50,
    "DICT_4X4_100":  cv2.aruco.DICT_4X4_100,
    "DICT_4X4_250":  cv2.aruco.DICT_4X4_250,
    "DICT_4X4_1000": cv2.aruco.DICT_4X4_1000,
    "DICT_5X5_100":  cv2.aruco.DICT_5X5_100,
    "DICT_5X5_250":  cv2.aruco.DICT_5X5_250,
    "DICT_6X6_100":  cv2.aruco.DICT_6X6_100,
    "DICT_6X6_250":  cv2.aruco.DICT_6X6_250,
}

# Font
FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "C:/Windows/Fonts/arialbd.ttf",
]


def cm_to_px(cm: float) -> int:
    """Convert centimetres to pixels at the configured DPI."""
    return int(round(cm * DPI / 2.54))


def _load_font(size_px: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in FONT_PATHS:
        try:
            return ImageFont.truetype(path, size_px)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def generate_aruco_marker(dictionary: int, marker_id: int, size_px: int) -> np.ndarray:
    """Generate a single ArUco marker as a numpy array (grayscale)."""
    aruco_dict = cv2.aruco.getPredefinedDictionary(dictionary)
    marker_img = cv2.aruco.generateImageMarker(aruco_dict, marker_id, size_px)
    return marker_img


def draw_calibration_strip(
    draw: ImageDraw.ImageDraw,
    x: int, y: int,
    width_px: int,
    segment_cm: float = STRIP_SEGMENT_CM,
    height_px: int | None = None,
) -> None:
    """Draw an alternating black/white calibration strip with cm markings."""
    seg_px = cm_to_px(segment_cm)
    h_px = height_px or cm_to_px(STRIP_HEIGHT_CM)
    n_segments = width_px // seg_px

    for i in range(n_segments):
        x0 = x + i * seg_px
        colour = "black" if i % 2 == 0 else "white"
        draw.rectangle([x0, y, x0 + seg_px - 1, y + h_px - 1], fill=colour, outline="black")

    # cm tick labels below the strip
    label_font = _load_font(cm_to_px(0.25))
    for i in range(0, n_segments + 1, 2):
        tick_x = x + i * seg_px
        cm_val = i * segment_cm
        label = f"{cm_val:.0f}"
        draw.text((tick_x, y + h_px + 2), label, fill="black", font=label_font, anchor="mt")


def generate_single_tag(
    bib_number: int,
    aruco_id: int,
    dictionary: int,
    marker_cm: float = DEFAULT_MARKER_CM,
    tag_width_cm: float = DEFAULT_TAG_WIDTH_CM,
    tag_height_cm: float = DEFAULT_TAG_HEIGHT_CM,
) -> Image.Image:
    """
    Generate a single bib tag image.

    Layout (top to bottom):
      - Top padding
      - ArUco marker (centred)
      - Bib number (large text, centred)
      - Calibration strip (centred, with cm markings)
      - Bottom padding
    """
    tag_w = cm_to_px(tag_width_cm)
    tag_h = cm_to_px(tag_height_cm)
    marker_px = cm_to_px(marker_cm)

    # Create white canvas
    img = Image.new("RGB", (tag_w, tag_h), "white")
    draw = ImageDraw.Draw(img)

    # Outer border (thin black rectangle for cutting guide)
    draw.rectangle([0, 0, tag_w - 1, tag_h - 1], outline="black", width=2)

    # --- ArUco marker ---
    marker_np = generate_aruco_marker(dictionary, aruco_id, marker_px)
    marker_rgb = cv2.cvtColor(marker_np, cv2.COLOR_GRAY2RGB)
    marker_pil = Image.fromarray(marker_rgb)

    # Add white border around marker (ArUco needs quiet zone)
    border_px = cm_to_px(BORDER_CM)
    marker_with_border = Image.new("RGB", (marker_px + 2 * border_px, marker_px + 2 * border_px), "white")
    marker_with_border.paste(marker_pil, (border_px, border_px))

    # Centre marker horizontally, place near top
    marker_total = marker_px + 2 * border_px
    mx = (tag_w - marker_total) // 2
    my = cm_to_px(0.5)  # small top padding
    img.paste(marker_with_border, (mx, my))

    # --- Layout zones (top-down, absolute positions) ---
    # Zone 1: marker  (my → my + marker_total)
    # Zone 2: bib number
    # Zone 3: ArUco ID label
    # Zone 4: calibration strip + cm ticks
    # Zone 5: bottom padding

    zone2_top = my + marker_total + cm_to_px(0.2)

    # Bib number
    bib_font = _load_font(cm_to_px(1.8))
    bib_text = f"#{bib_number:02d}"
    draw.text((tag_w // 2, zone2_top), bib_text, fill="black", font=bib_font, anchor="mt")

    # ArUco ID label
    zone3_top = zone2_top + cm_to_px(2.2)
    size_font = _load_font(cm_to_px(0.25))
    size_label = f"ArUco ID:{aruco_id}  |  {marker_cm:.0f} cm × {marker_cm:.0f} cm"
    draw.text((tag_w // 2, zone3_top), size_label, fill="gray", font=size_font, anchor="mt")

    # Calibration strip — anchored from bottom
    strip_width_cm = tag_width_cm - 2.0
    strip_w = cm_to_px(strip_width_cm)
    strip_x = (tag_w - strip_w) // 2
    strip_bottom_margin_cm = 1.2   # space below strip for cm tick labels
    strip_y = tag_h - cm_to_px(STRIP_HEIGHT_CM + strip_bottom_margin_cm)

    # Strip title
    strip_label_font = _load_font(cm_to_px(0.2))
    draw.text(
        (tag_w // 2, strip_y - cm_to_px(0.2)),
        f"CALIBRATION  ({STRIP_SEGMENT_CM:.0f} cm segments)",
        fill="gray", font=strip_label_font, anchor="mb",
    )

    draw_calibration_strip(draw, strip_x, strip_y, strip_w)

    # --- "VIGOUR TEST" branding at very top ---
    brand_font = _load_font(cm_to_px(0.35))
    draw.text((tag_w // 2, cm_to_px(0.15)), "VIGOUR TEST", fill="gray", font=brand_font, anchor="mt")

    return img


def draw_crop_marks(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, length: int) -> None:
    """Draw crop marks at the four corners of a rectangle."""
    mark_colour = "black"
    lw = 1
    corners = [(x, y), (x + w, y), (x, y + h), (x + w, y + h)]
    for cx, cy in corners:
        # Horizontal marks
        dx = -length if cx == x + w else length
        draw.line([(cx - (0 if dx > 0 else length), cy), (cx + (length if dx > 0 else 0), cy)],
                  fill=mark_colour, width=lw)
        # Vertical marks
        dy = -length if cy == y + h else length
        draw.line([(cx, cy - (0 if dy > 0 else length)), (cx, cy + (length if dy > 0 else 0))],
                  fill=mark_colour, width=lw)


def generate_print_sheet(
    tags: list[Image.Image],
    bib_numbers: list[int],
    sheet_index: int,
) -> Image.Image:
    """
    Arrange up to 4 tags on an A4 sheet (2 columns × 2 rows) with crop marks.
    """
    a4_w = cm_to_px(A4_WIDTH_CM)
    a4_h = cm_to_px(A4_HEIGHT_CM)
    margin = cm_to_px(A4_MARGIN_CM)
    crop_len = cm_to_px(CROP_MARK_CM)

    sheet = Image.new("RGB", (a4_w, a4_h), "white")
    draw = ImageDraw.Draw(sheet)

    # Grid: 2 columns × 2 rows
    cols, rows = 2, 2
    tag_w, tag_h = tags[0].size if tags else (0, 0)

    # Centre the grid on the page
    grid_w = cols * tag_w
    grid_h = rows * tag_h
    x_offset = (a4_w - grid_w) // 2
    y_offset = (a4_h - grid_h) // 2

    for idx, (tag, bib) in enumerate(zip(tags, bib_numbers)):
        col = idx % cols
        row = idx // cols
        x = x_offset + col * tag_w
        y = y_offset + row * tag_h
        sheet.paste(tag, (x, y))
        draw_crop_marks(draw, x, y, tag_w, tag_h, crop_len)

    # Sheet label
    label_font = _load_font(cm_to_px(0.3))
    bibs_str = ", ".join(f"#{b:02d}" for b in bib_numbers)
    draw.text(
        (a4_w // 2, a4_h - cm_to_px(0.3)),
        f"Sheet {sheet_index + 1}  |  Bibs: {bibs_str}",
        fill="gray", font=label_font, anchor="mb",
    )

    return sheet


def generate_all(
    count: int,
    start_bib: int,
    dictionary_name: str,
    marker_cm: float,
    tag_width_cm: float,
    tag_height_cm: float,
    output_dir: Path,
) -> dict:
    """Generate all tags, print sheets, and manifest."""
    dictionary = ARUCO_DICTS[dictionary_name]

    individual_dir = output_dir / "individual"
    sheets_dir = output_dir / "sheets"
    individual_dir.mkdir(parents=True, exist_ok=True)
    sheets_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator": "generate_bib_tags.py",
        "dictionary": dictionary_name,
        "marker_size_cm": marker_cm,
        "tag_size_cm": [tag_width_cm, tag_height_cm],
        "calibration_strip_segment_cm": STRIP_SEGMENT_CM,
        "dpi": DPI,
        "total_bibs": count,
        "start_bib": start_bib,
        "bibs": [],
    }

    all_tags: list[Image.Image] = []
    all_bib_numbers: list[int] = []

    for i in range(count):
        bib_number = start_bib + i
        aruco_id = i  # ArUco ID 0-indexed within dictionary

        tag_img = generate_single_tag(
            bib_number=bib_number,
            aruco_id=aruco_id,
            dictionary=dictionary,
            marker_cm=marker_cm,
            tag_width_cm=tag_width_cm,
            tag_height_cm=tag_height_cm,
        )

        # Save individual tag
        filename = f"bib_{bib_number:03d}.png"
        filepath = individual_dir / filename
        tag_img.save(str(filepath), dpi=(DPI, DPI))

        manifest["bibs"].append({
            "bib_number": bib_number,
            "aruco_id": aruco_id,
            "file": f"individual/{filename}",
            "student_name": None,
            "assigned_date": None,
        })

        all_tags.append(tag_img)
        all_bib_numbers.append(bib_number)

        if (i + 1) % 10 == 0 or i == count - 1:
            print(f"  Generated {i + 1}/{count} tags", flush=True)

    # Generate print sheets (4 per A4)
    tags_per_sheet = 4
    sheet_count = 0
    for s in range(0, count, tags_per_sheet):
        batch_tags = all_tags[s:s + tags_per_sheet]
        batch_bibs = all_bib_numbers[s:s + tags_per_sheet]
        sheet = generate_print_sheet(batch_tags, batch_bibs, sheet_count)

        sheet_filename = f"sheet_{sheet_count + 1:03d}.png"
        sheet.save(str(sheets_dir / sheet_filename), dpi=(DPI, DPI))
        sheet_count += 1

    manifest["sheet_count"] = sheet_count
    print(f"  Generated {sheet_count} print sheets (4 tags per A4)")

    # Save manifest
    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"  Manifest saved to {manifest_path}")

    return manifest


def assign_student(manifest_path: Path, bib_number: int, student_name: str) -> None:
    """Assign a student name to a bib in the manifest."""
    with open(manifest_path) as f:
        manifest = json.load(f)

    found = False
    for entry in manifest["bibs"]:
        if entry["bib_number"] == bib_number:
            entry["student_name"] = student_name
            entry["assigned_date"] = datetime.now(timezone.utc).isoformat()
            found = True
            break

    if not found:
        print(f"Error: bib #{bib_number} not found in manifest.", file=sys.stderr)
        sys.exit(1)

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"Assigned bib #{bib_number} → {student_name}")


def assign_bulk(manifest_path: Path, csv_path: Path) -> None:
    """Bulk-assign students from a CSV file (columns: bib_number, student_name)."""
    import csv

    with open(manifest_path) as f:
        manifest = json.load(f)

    bib_lookup = {e["bib_number"]: e for e in manifest["bibs"]}

    with open(csv_path) as f:
        reader = csv.DictReader(f)
        assigned = 0
        for row in reader:
            bib = int(row["bib_number"])
            name = row["student_name"]
            if bib in bib_lookup:
                bib_lookup[bib]["student_name"] = name
                bib_lookup[bib]["assigned_date"] = datetime.now(timezone.utc).isoformat()
                assigned += 1
            else:
                print(f"Warning: bib #{bib} not in manifest, skipping.", file=sys.stderr)

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"Assigned {assigned} students from {csv_path}")


def list_assignments(manifest_path: Path) -> None:
    """Print current bib → student assignments."""
    with open(manifest_path) as f:
        manifest = json.load(f)

    print(f"Manifest: {manifest_path}")
    print(f"Dictionary: {manifest['dictionary']}  |  Marker: {manifest['marker_size_cm']} cm")
    print(f"Total bibs: {manifest['total_bibs']}\n")
    print(f"{'Bib':>5}  {'ArUco ID':>8}  {'Student':<30}  {'Assigned'}")
    print("-" * 75)

    for entry in manifest["bibs"]:
        name = entry["student_name"] or "(unassigned)"
        date = entry["assigned_date"] or ""
        if date:
            date = date[:10]  # just the date part
        print(f"  #{entry['bib_number']:03d}  {entry['aruco_id']:>8}  {name:<30}  {date}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate ArUco bib tags with calibration strips for Vigour Test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    Generate 100 bibs (default)
  %(prog)s --count 60 --start-bib 1           Generate bibs #1–#60
  %(prog)s --count 200 --dictionary DICT_4X4_250   >100 bibs
  %(prog)s --assign manifest.json 7 "Liam van der Berg"
  %(prog)s --assign-csv manifest.json roster.csv
  %(prog)s --list manifest.json
        """,
    )

    # Generation args
    parser.add_argument("--count", type=int, default=100, help="Number of bibs to generate (default: 100)")
    parser.add_argument("--start-bib", type=int, default=1, help="Starting bib number (default: 1)")
    parser.add_argument("--marker-cm", type=float, default=DEFAULT_MARKER_CM, help=f"ArUco marker size in cm (default: {DEFAULT_MARKER_CM})")
    parser.add_argument("--tag-width-cm", type=float, default=DEFAULT_TAG_WIDTH_CM, help=f"Tag width in cm (default: {DEFAULT_TAG_WIDTH_CM})")
    parser.add_argument("--tag-height-cm", type=float, default=DEFAULT_TAG_HEIGHT_CM, help=f"Tag height in cm (default: {DEFAULT_TAG_HEIGHT_CM})")
    parser.add_argument("--dictionary", default="DICT_4X4_100", choices=list(ARUCO_DICTS.keys()), help="ArUco dictionary (default: DICT_4X4_100)")
    parser.add_argument("--output-dir", type=Path, default=Path("bib_tags"), help="Output directory (default: ./bib_tags)")

    # Assignment args
    parser.add_argument("--assign", nargs=3, metavar=("MANIFEST", "BIB", "NAME"), help="Assign a student to a bib: --assign manifest.json 7 'Name'")
    parser.add_argument("--assign-csv", nargs=2, metavar=("MANIFEST", "CSV"), help="Bulk assign from CSV: --assign-csv manifest.json roster.csv")
    parser.add_argument("--list", dest="list_manifest", metavar="MANIFEST", help="List all bib assignments")

    args = parser.parse_args()

    # Handle assignment commands
    if args.assign:
        assign_student(Path(args.assign[0]), int(args.assign[1]), args.assign[2])
        return

    if args.assign_csv:
        assign_bulk(Path(args.assign_csv[0]), Path(args.assign_csv[1]))
        return

    if args.list_manifest:
        list_assignments(Path(args.list_manifest))
        return

    # Validate
    aruco_dict_obj = cv2.aruco.getPredefinedDictionary(ARUCO_DICTS[args.dictionary])
    max_ids = aruco_dict_obj.bytesList.shape[0]
    if args.count > max_ids:
        print(
            f"Error: {args.dictionary} supports {max_ids} IDs but --count={args.count}. "
            f"Use a larger dictionary (e.g. --dictionary DICT_4X4_250).",
            file=sys.stderr,
        )
        sys.exit(1)

    # Generate
    print(f"Generating {args.count} bib tags (#{args.start_bib}–#{args.start_bib + args.count - 1})")
    print(f"  Dictionary:  {args.dictionary} ({max_ids} IDs available)")
    print(f"  Marker size: {args.marker_cm} cm × {args.marker_cm} cm")
    print(f"  Tag size:    {args.tag_width_cm} cm × {args.tag_height_cm} cm")
    print(f"  DPI:         {DPI}")
    print(f"  Output:      {args.output_dir.resolve()}\n")

    manifest = generate_all(
        count=args.count,
        start_bib=args.start_bib,
        dictionary_name=args.dictionary,
        marker_cm=args.marker_cm,
        tag_width_cm=args.tag_width_cm,
        tag_height_cm=args.tag_height_cm,
        output_dir=args.output_dir,
    )

    print(f"\nDone. Files in {args.output_dir.resolve()}/")
    print(f"  individual/  — {manifest['total_bibs']} PNG files (one per bib)")
    print(f"  sheets/      — {manifest['sheet_count']} A4 print sheets (4 per page, with crop marks)")
    print(f"  manifest.json — bib↔ArUco mapping + student assignment log")


if __name__ == "__main__":
    main()

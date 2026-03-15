#!/usr/bin/env python3
"""
Compare two cone POC JSON result files.

Expected JSON structure:
{
  "backend": "...",
  "detections": [
    {"frame_idx": 0, "timestamp_s": 0.0, "cones": [{"cx": ..., "cy": ..., ...}]}
  ],
  "summary": {...}
}
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Set

import numpy as np


def _load(path: Path) -> Dict:
    return json.loads(path.read_text())


def _index_by_frame(payload: Dict) -> Dict[int, List[Dict]]:
    out: Dict[int, List[Dict]] = {}
    for row in payload.get("detections", []):
        out[int(row["frame_idx"])] = row.get("cones", [])
    return out


def _greedy_match(a: List[Dict], b: List[Dict], dist_thr_px: float) -> int:
    if not a or not b:
        return 0
    used_b: Set[int] = set()
    matches = 0
    for ca in a:
        ax, ay = float(ca["cx"]), float(ca["cy"])
        best_j = -1
        best_d = float("inf")
        for j, cb in enumerate(b):
            if j in used_b:
                continue
            bx, by = float(cb["cx"]), float(cb["cy"])
            d = float(np.hypot(ax - bx, ay - by))
            if d < best_d:
                best_d = d
                best_j = j
        if best_j >= 0 and best_d <= dist_thr_px:
            matches += 1
            used_b.add(best_j)
    return matches


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare two cone POC JSON files")
    parser.add_argument("--a", required=True, help="First JSON (e.g. YOLOX output).")
    parser.add_argument("--b", required=True, help="Second JSON (e.g. SAM output).")
    parser.add_argument("--dist-threshold-px", type=float, default=25.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    a_payload = _load(Path(args.a))
    b_payload = _load(Path(args.b))

    a_name = a_payload.get("backend", "A")
    b_name = b_payload.get("backend", "B")

    a_frames = _index_by_frame(a_payload)
    b_frames = _index_by_frame(b_payload)
    common = sorted(set(a_frames) & set(b_frames))

    if not common:
        print("No overlapping frame_idx values between files.")
        return

    total_a = 0
    total_b = 0
    total_matches = 0
    per_frame_abs_count_diff = []

    for fidx in common:
        a_cones = a_frames[fidx]
        b_cones = b_frames[fidx]
        total_a += len(a_cones)
        total_b += len(b_cones)
        total_matches += _greedy_match(a_cones, b_cones, args.dist_threshold_px)
        per_frame_abs_count_diff.append(abs(len(a_cones) - len(b_cones)))

    precision_proxy = total_matches / max(total_a, 1)
    recall_proxy = total_matches / max(total_b, 1)
    f1_proxy = (
        2 * precision_proxy * recall_proxy / max(precision_proxy + recall_proxy, 1e-9)
    )

    print("=== Cone POC Comparison ===")
    print(f"Frames compared: {len(common)}")
    print(f"Backend A: {a_name}")
    print(f"Backend B: {b_name}")
    print("")
    print(f"A total cones: {total_a}")
    print(f"B total cones: {total_b}")
    print(f"Matched cones (<= {args.dist_threshold_px:.1f}px): {total_matches}")
    print(f"Agreement precision proxy ({a_name} vs {b_name}): {precision_proxy:.3f}")
    print(f"Agreement recall proxy ({a_name} vs {b_name}): {recall_proxy:.3f}")
    print(f"Agreement F1 proxy: {f1_proxy:.3f}")
    print(f"Mean |count diff| per frame: {float(np.mean(per_frame_abs_count_diff)):.3f}")
    print("")
    print("A summary:", a_payload.get("summary", {}))
    print("B summary:", b_payload.get("summary", {}))


if __name__ == "__main__":
    main()

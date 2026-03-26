#!/usr/bin/env python3
"""
POC: cone proposals from SAM2/SAM3 masks.

Supports two modes:
- Unprompted (default): Uses Ultralytics SAM to generate masks, then filters by
  cone-like color/shape. Works with SAM2 or SAM3 interactive checkpoints.
- Text prompt (SAM3 only): Uses SAM3 semantic model with a text prompt (e.g. "cone")
  for direct detection; optional HSV/shape filtering can still be applied.
  Requires a SAM3 checkpoint whose filename contains 'sam3' (e.g. sam3_b.pt) and
  the optional dependency: pip install "git+https://github.com/ultralytics/CLIP.git"
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from pipeline.ingest import extract_frames
from pipeline.visualise import _create_h264_writer


@dataclass
class ConeProposal:
    cx: float
    cy: float
    score: float
    bbox: Tuple[float, float, float, float]
    area_px: int
    hue_mean: float
    sat_mean: float
    val_mean: float


def _boxes_iou(a: np.ndarray, b: np.ndarray) -> float:
    x1 = max(float(a[0]), float(b[0]))
    y1 = max(float(a[1]), float(b[1]))
    x2 = min(float(a[2]), float(b[2]))
    y2 = min(float(a[3]), float(b[3]))
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area_a = max(0.0, float(a[2] - a[0])) * max(0.0, float(a[3] - a[1]))
    area_b = max(0.0, float(b[2] - b[0])) * max(0.0, float(b[3] - b[1]))
    return inter / (area_a + area_b - inter + 1e-6)


def _nms(boxes: List[np.ndarray], scores: List[float], iou_threshold: float) -> List[int]:
    if not boxes:
        return []
    order = np.argsort(np.asarray(scores))[::-1]
    keep: List[int] = []
    while order.size > 0:
        i = int(order[0])
        keep.append(i)
        if order.size == 1:
            break
        rest = order[1:]
        remaining = []
        for j in rest:
            if _boxes_iou(boxes[i], boxes[int(j)]) < iou_threshold:
                remaining.append(int(j))
        order = np.asarray(remaining, dtype=np.int64)
    return keep


class SamConeProposer:
    # Cone color priors in HSV (OpenCV range H=[0,179]).
    HUE_RANGES = {
        "yellow": (18, 35),
        "orange": (5, 18),
        "blue": (100, 130),
        "red_lo": (0, 5),
        "red_hi": (170, 180),
    }

    def __init__(
        self,
        model_path: str,
        prompt: Optional[str] = None,
        min_area: int = 100,
        max_area: int = 15000,
        min_saturation: int = 60,
        min_value: int = 60,
        iou_threshold: float = 0.5,
        use_color_filter: bool = True,
        use_proposal_filters: bool = True,
    ):
        try:
            from ultralytics import SAM  # type: ignore
        except Exception as exc:  # pragma: no cover - dependency/runtime dependent
            raise ImportError(
                "Ultralytics SAM is required. Try: pip install -U ultralytics"
            ) from exc

        self.model_path = model_path
        self.prompt = prompt
        resolved_path = self._resolve_model_path(model_path)
        self._use_semantic = bool(prompt and "sam3" in Path(resolved_path).stem)
        self.model = None
        self._semantic_predictor = None

        if self._use_semantic:
            from ultralytics.models.sam.predict import SAM3SemanticPredictor

            self._semantic_predictor = SAM3SemanticPredictor(
                overrides={"model": resolved_path, "imgsz": 1036}
            )
        else:
            self.model = SAM(resolved_path)

        self.min_area = min_area
        self.max_area = max_area
        self.min_saturation = min_saturation
        self.min_value = min_value
        self.iou_threshold = iou_threshold
        self.use_color_filter = use_color_filter
        self.use_proposal_filters = use_proposal_filters

    @staticmethod
    def _resolve_model_path(model_path: str) -> str:
        """Resolve model path: try Ultralytics asset download, then HF 1038lab/sam3 for sam3.pt."""
        path_obj = Path(model_path)
        if "/" in model_path or "\\" in model_path:
            return model_path
        if path_obj.exists():
            return model_path
        # Try Ultralytics assets (e.g. sam2_b.pt)
        try:
            from ultralytics.utils.downloads import attempt_download_asset
            resolved = attempt_download_asset(model_path)
            if resolved and Path(resolved).exists():
                return str(resolved)
        except Exception:
            pass
        # SAM3: try Hugging Face 1038lab/sam3 (public mirror with sam3.pt)
        stem = path_obj.stem.lower()
        if stem.startswith("sam3"):
            try:
                from huggingface_hub import hf_hub_download
                local = hf_hub_download(
                    repo_id="1038lab/sam3",
                    filename="sam3.pt",
                )
                if local and Path(local).exists():
                    return local
            except Exception:
                pass
        return model_path

    def _is_cone_colored(self, h_mean: float, s_mean: float, v_mean: float) -> bool:
        if s_mean < self.min_saturation or v_mean < self.min_value:
            return False
        for lo, hi in self.HUE_RANGES.values():
            if lo <= h_mean <= hi:
                return True
        return False

    def _extract_masks(self, frame: np.ndarray) -> np.ndarray:
        if self._use_semantic and self._semantic_predictor is not None:
            self._semantic_predictor.set_prompts({"text": [self.prompt]})
            results = self._semantic_predictor(source=frame, verbose=False)
        else:
            results = self.model.predict(source=frame, verbose=False)

        if not results:
            return np.zeros((0, frame.shape[0], frame.shape[1]), dtype=np.uint8)
        r0 = results[0]
        if getattr(r0, "masks", None) is None or r0.masks is None:
            return np.zeros((0, frame.shape[0], frame.shape[1]), dtype=np.uint8)
        data = r0.masks.data
        if hasattr(data, "cpu"):
            data = data.cpu().numpy()
        return (data > 0.5).astype(np.uint8)

    def propose(self, frame: np.ndarray) -> List[ConeProposal]:
        h, w = frame.shape[:2]
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        masks = self._extract_masks(frame)
        proposals: List[ConeProposal] = []

        for mask in masks:
            ys, xs = np.where(mask > 0)
            if xs.size == 0:
                continue
            area = int(xs.size)
            if self.use_proposal_filters and (area < self.min_area or area > self.max_area):
                continue

            x1, x2 = int(xs.min()), int(xs.max())
            y1, y2 = int(ys.min()), int(ys.max())
            bbox_w = x2 - x1 + 1
            bbox_h = y2 - y1 + 1
            if bbox_w <= 2 or bbox_h <= 2:
                continue

            # Mild cone-like shape filter: avoid very thin masks.
            aspect = bbox_w / max(bbox_h, 1)
            if self.use_proposal_filters and (aspect < 0.15 or aspect > 1.6):
                continue

            pix = hsv[ys, xs]
            h_mean = float(np.mean(pix[:, 0]))
            s_mean = float(np.mean(pix[:, 1]))
            v_mean = float(np.mean(pix[:, 2]))
            if self.use_color_filter and not self._is_cone_colored(h_mean, s_mean, v_mean):
                continue

            m = cv2.moments(mask)
            if m["m00"] <= 0:
                continue
            cx = float(m["m10"] / m["m00"])
            cy = float(m["m01"] / m["m00"])
            if not (0 <= cx < w and 0 <= cy < h):
                continue

            # SAM does not always expose calibrated per-mask confidence in this mode.
            # Use mask compactness proxy as weak confidence score.
            bbox_area = float((bbox_w) * (bbox_h))
            compactness = float(area / max(bbox_area, 1.0))
            proposals.append(
                ConeProposal(
                    cx=cx,
                    cy=cy,
                    score=compactness,
                    bbox=(float(x1), float(y1), float(x2), float(y2)),
                    area_px=area,
                    hue_mean=h_mean,
                    sat_mean=s_mean,
                    val_mean=v_mean,
                )
            )

        if not proposals:
            return []

        boxes = [np.array(p.bbox, dtype=np.float32) for p in proposals]
        scores = [p.score for p in proposals]
        keep = _nms(boxes, scores, self.iou_threshold)
        return [proposals[i] for i in keep]


def _draw(frame: np.ndarray, cones: List[ConeProposal]) -> np.ndarray:
    vis = frame.copy()
    for c in cones:
        x1, y1, x2, y2 = map(int, c.bbox)
        cv2.rectangle(vis, (x1, y1), (x2, y2), (255, 180, 0), 2)
        cv2.circle(vis, (int(c.cx), int(c.cy)), 4, (255, 180, 0), -1)
        cv2.putText(
            vis,
            f"{c.score:.2f}",
            (x1, max(0, y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 180, 0),
            1,
            cv2.LINE_AA,
        )
    return vis


def _build_summary(detections: List[Dict]) -> Dict:
    frame_count = len(detections)
    cone_counts = [len(d["cones"]) for d in detections]
    all_scores = [c["score"] for d in detections for c in d["cones"]]
    return {
        "frames_processed": frame_count,
        "total_cones": int(sum(cone_counts)),
        "avg_cones_per_frame": float(np.mean(cone_counts) if frame_count else 0.0),
        "non_empty_frame_ratio": float(np.mean([n > 0 for n in cone_counts]) if frame_count else 0.0),
        "mean_score": float(np.mean(all_scores) if all_scores else 0.0),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="POC cone proposals from SAM2/SAM3")
    parser.add_argument("--video", required=True, help="Path to input video.")
    parser.add_argument(
        "--model",
        required=True,
        help=(
            "SAM checkpoint name/path, e.g. sam2_b.pt or sam3_b.pt. "
            "For text-prompt mode use a SAM3 checkpoint (name containing 'sam3')."
        ),
    )
    parser.add_argument(
        "--prompt",
        default=None,
        help=(
            "Text prompt for SAM3 semantic detection (e.g. 'cone', 'traffic cone'). "
            "When set with a sam3 model, uses SAM3 semantic predictor instead of unprompted masks."
        ),
    )
    parser.add_argument("--target-fps", type=int, default=10)
    parser.add_argument("--max-frames", type=int, default=300)
    parser.add_argument("--min-area", type=int, default=120)
    parser.add_argument("--max-area", type=int, default=15000)
    parser.add_argument("--min-saturation", type=int, default=60)
    parser.add_argument("--min-value", type=int, default=60)
    parser.add_argument("--iou", type=float, default=0.5)
    parser.add_argument(
        "--no-color-filter",
        action="store_true",
        help="Disable HSV cone-color filtering; keep all mask proposals that pass area/shape.",
    )
    parser.add_argument(
        "--no-filter",
        action="store_true",
        help="Disable area/shape/color proposal filters (keeps raw SAM prompt proposals before NMS).",
    )
    parser.add_argument("--save-annotated", action="store_true")
    parser.add_argument("--output-json", default="data/cache/poc_sam_cones.json")
    parser.add_argument("--output-video", default="data/annotated/poc_sam_cones.mp4")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    video_path = Path(args.video)
    out_json = Path(args.output_json)
    out_video = Path(args.output_video)

    proposer = SamConeProposer(
        model_path=args.model,
        prompt=args.prompt,
        min_area=args.min_area,
        max_area=args.max_area,
        min_saturation=args.min_saturation,
        min_value=args.min_value,
        iou_threshold=args.iou,
        use_color_filter=(not args.no_color_filter) and (not args.no_filter),
        use_proposal_filters=not args.no_filter,
    )

    out_json.parent.mkdir(parents=True, exist_ok=True)
    if args.save_annotated:
        out_video.parent.mkdir(parents=True, exist_ok=True)

    detections: List[Dict] = []
    writer = None
    processed = 0

    try:
        for frame_idx, frame, timestamp_s in extract_frames(video_path, target_fps=args.target_fps):
            cones = proposer.propose(frame)
            detections.append(
                {
                    "frame_idx": int(frame_idx),
                    "timestamp_s": float(timestamp_s),
                    "cones": [asdict(c) for c in cones],
                }
            )

            if args.save_annotated:
                vis = _draw(frame, cones)
                if writer is None:
                    h, w = vis.shape[:2]
                    writer = _create_h264_writer(
                        Path(out_video), w, h, args.target_fps
                    )
                writer.write(np.ascontiguousarray(vis))

            processed += 1
            if processed >= args.max_frames:
                break
    finally:
        if writer is not None:
            writer.release()

    payload = {
        "backend": "sam",
        "video_path": str(video_path),
        "model_path": str(args.model),
        "prompt": args.prompt,
        "target_fps": args.target_fps,
        "detections": detections,
        "summary": _build_summary(detections),
    }
    out_json.write_text(json.dumps(payload, indent=2))
    print(f"[SAM] Wrote JSON: {out_json}")
    if args.save_annotated:
        print(f"[SAM] Wrote video: {out_video}")
    print(f"[SAM] Summary: {payload['summary']}")


if __name__ == "__main__":
    main()

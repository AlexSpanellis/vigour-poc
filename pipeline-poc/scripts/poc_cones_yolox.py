#!/usr/bin/env python3
"""
POC: cone detection with YOLOX ONNX.

This script runs YOLOX on sampled video frames and exports a JSON report
with per-frame cone centroids, boxes, and confidence values.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import cv2
import numpy as np

from pipeline.ingest import extract_frames
from pipeline.visualise import _create_h264_writer


@dataclass
class ConeDetection:
    cx: float
    cy: float
    score: float
    class_id: int
    bbox: Tuple[float, float, float, float]


def _xywh_to_xyxy(boxes_xywh: np.ndarray) -> np.ndarray:
    out = boxes_xywh.copy()
    out[:, 0] = boxes_xywh[:, 0] - boxes_xywh[:, 2] / 2.0
    out[:, 1] = boxes_xywh[:, 1] - boxes_xywh[:, 3] / 2.0
    out[:, 2] = boxes_xywh[:, 0] + boxes_xywh[:, 2] / 2.0
    out[:, 3] = boxes_xywh[:, 1] + boxes_xywh[:, 3] / 2.0
    return out


def _box_iou(box: np.ndarray, boxes: np.ndarray) -> np.ndarray:
    x1 = np.maximum(box[0], boxes[:, 0])
    y1 = np.maximum(box[1], boxes[:, 1])
    x2 = np.minimum(box[2], boxes[:, 2])
    y2 = np.minimum(box[3], boxes[:, 3])
    inter = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    area_a = np.maximum(0.0, box[2] - box[0]) * np.maximum(0.0, box[3] - box[1])
    area_b = np.maximum(0.0, boxes[:, 2] - boxes[:, 0]) * np.maximum(0.0, boxes[:, 3] - boxes[:, 1])
    union = area_a + area_b - inter + 1e-6
    return inter / union


def _nms(boxes: np.ndarray, scores: np.ndarray, iou_thr: float) -> List[int]:
    order = np.argsort(scores)[::-1]
    keep: List[int] = []
    while order.size > 0:
        i = int(order[0])
        keep.append(i)
        if order.size == 1:
            break
        ious = _box_iou(boxes[i], boxes[order[1:]])
        order = order[1:][ious < iou_thr]
    return keep


class YOLOXOnnxConeDetector:
    def __init__(
        self,
        model_path: str,
        input_size: int = 640,
        conf_threshold: float = 0.35,
        iou_threshold: float = 0.45,
        cone_class_ids: Optional[Set[int]] = None,
        use_cpu: bool = False,
    ):
        try:
            import onnxruntime as ort  # type: ignore
        except Exception as exc:
            raise ImportError("onnxruntime is required. Try: pip install onnxruntime-gpu") from exc

        providers = ["CPUExecutionProvider"] if use_cpu else ["CUDAExecutionProvider", "CPUExecutionProvider"]
        self.session = ort.InferenceSession(model_path, providers=providers)
        self.input_name = self.session.get_inputs()[0].name
        self.input_size = input_size
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.cone_class_ids = cone_class_ids or {0}

    def _preprocess(self, frame: np.ndarray) -> Tuple[np.ndarray, float, int, int]:
        h, w = frame.shape[:2]
        ratio = min(self.input_size / h, self.input_size / w)
        new_w, new_h = int(round(w * ratio)), int(round(h * ratio))
        resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        canvas = np.full((self.input_size, self.input_size, 3), 114, dtype=np.uint8)
        pad_x = (self.input_size - new_w) // 2
        pad_y = (self.input_size - new_h) // 2
        canvas[pad_y:pad_y + new_h, pad_x:pad_x + new_w] = resized
        blob = canvas.astype(np.float32) / 255.0
        blob = np.transpose(blob, (2, 0, 1))[None, ...]
        return blob, ratio, pad_x, pad_y

    def _decode_predictions(self, raw: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        # Common YOLOX ONNX format: [N, 85] -> [cx, cy, w, h, obj, cls...]
        if raw.ndim == 3:
            raw = raw[0]
        if raw.ndim != 2 or raw.shape[1] < 6:
            raise ValueError(f"Unexpected YOLOX output shape: {raw.shape}")

        if raw.shape[1] > 6:
            boxes = raw[:, :4]
            obj = raw[:, 4]
            class_probs = raw[:, 5:]
            class_ids = np.argmax(class_probs, axis=1).astype(np.int32)
            class_scores = np.max(class_probs, axis=1)
            scores = obj * class_scores
            boxes_xyxy = _xywh_to_xyxy(boxes)
        else:
            # Already decoded format: [x1, y1, x2, y2, score, class_id]
            boxes_xyxy = raw[:, :4]
            scores = raw[:, 4]
            class_ids = raw[:, 5].astype(np.int32)

        return boxes_xyxy, scores, class_ids

    def detect(self, frame: np.ndarray) -> List[ConeDetection]:
        h, w = frame.shape[:2]
        blob, ratio, pad_x, pad_y = self._preprocess(frame)
        output = self.session.run(None, {self.input_name: blob})[0]
        boxes_xyxy, scores, class_ids = self._decode_predictions(output)

        keep_mask = (
            (scores >= self.conf_threshold)
            & np.isin(class_ids, list(self.cone_class_ids))
        )
        boxes_xyxy = boxes_xyxy[keep_mask]
        scores = scores[keep_mask]
        class_ids = class_ids[keep_mask]
        if boxes_xyxy.size == 0:
            return []

        # Undo letterbox padding and scale back to original frame.
        boxes_xyxy[:, [0, 2]] = (boxes_xyxy[:, [0, 2]] - pad_x) / max(ratio, 1e-6)
        boxes_xyxy[:, [1, 3]] = (boxes_xyxy[:, [1, 3]] - pad_y) / max(ratio, 1e-6)
        boxes_xyxy[:, [0, 2]] = np.clip(boxes_xyxy[:, [0, 2]], 0, w - 1)
        boxes_xyxy[:, [1, 3]] = np.clip(boxes_xyxy[:, [1, 3]], 0, h - 1)

        keep = _nms(boxes_xyxy, scores, self.iou_threshold)
        cones: List[ConeDetection] = []
        for i in keep:
            x1, y1, x2, y2 = boxes_xyxy[i].tolist()
            cx = (x1 + x2) / 2.0
            cy = (y1 + y2) / 2.0
            cones.append(
                ConeDetection(
                    cx=float(cx),
                    cy=float(cy),
                    score=float(scores[i]),
                    class_id=int(class_ids[i]),
                    bbox=(float(x1), float(y1), float(x2), float(y2)),
                )
            )
        return cones


def _draw(frame: np.ndarray, cones: List[ConeDetection]) -> np.ndarray:
    vis = frame.copy()
    for c in cones:
        x1, y1, x2, y2 = map(int, c.bbox)
        cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 220, 255), 2)
        cv2.circle(vis, (int(c.cx), int(c.cy)), 4, (0, 220, 255), -1)
        cv2.putText(
            vis,
            f"{c.score:.2f}",
            (x1, max(0, y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 220, 255),
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
        "mean_confidence": float(np.mean(all_scores) if all_scores else 0.0),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="POC cone detection with YOLOX ONNX")
    parser.add_argument("--video", required=True, help="Path to input video.")
    parser.add_argument("--model", required=True, help="Path to YOLOX ONNX model.")
    parser.add_argument("--target-fps", type=int, default=10)
    parser.add_argument("--max-frames", type=int, default=300)
    parser.add_argument("--input-size", type=int, default=416)
    parser.add_argument("--conf", type=float, default=0.35)
    parser.add_argument("--iou", type=float, default=0.45)
    parser.add_argument(
        "--cone-class-ids",
        default="0",
        help="Comma-separated class IDs that represent cones (default: 0).",
    )
    parser.add_argument("--use-cpu", action="store_true", help="Force ONNXRuntime CPU.")
    parser.add_argument("--save-annotated", action="store_true")
    parser.add_argument("--output-json", default="data/cache/poc_yolox_cones.json")
    parser.add_argument("--output-video", default="data/annotated/poc_yolox_cones.mp4")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    video_path = Path(args.video)
    model_path = Path(args.model)
    out_json = Path(args.output_json)
    out_video = Path(args.output_video)

    cone_ids = {int(x) for x in args.cone_class_ids.split(",") if x.strip()}
    detector = YOLOXOnnxConeDetector(
        model_path=str(model_path),
        input_size=args.input_size,
        conf_threshold=args.conf,
        iou_threshold=args.iou,
        cone_class_ids=cone_ids,
        use_cpu=args.use_cpu,
    )

    out_json.parent.mkdir(parents=True, exist_ok=True)
    if args.save_annotated:
        out_video.parent.mkdir(parents=True, exist_ok=True)

    detections: List[Dict] = []
    writer = None
    processed = 0

    try:
        for frame_idx, frame, timestamp_s in extract_frames(video_path, target_fps=args.target_fps):
            cones = detector.detect(frame)
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
        "backend": "yolox",
        "video_path": str(video_path),
        "model_path": str(model_path),
        "target_fps": args.target_fps,
        "detections": detections,
        "summary": _build_summary(detections),
    }
    out_json.write_text(json.dumps(payload, indent=2))
    print(f"[YOLOX] Wrote JSON: {out_json}")
    if args.save_annotated:
        print(f"[YOLOX] Wrote video: {out_video}")
    print(f"[YOLOX] Summary: {payload['summary']}")


if __name__ == "__main__":
    main()

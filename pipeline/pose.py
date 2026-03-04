"""
Module 4 — Pose Estimation (Top-Down)
Interface: PoseEstimator.estimate(frame, tracks) → list[Pose]

Recommended approach: RTMPose-m (ONNX, top-down per-crop).
Alternatives: RTMPose-s, ViTPose-S, MediaPipe (balance only), YOLOv8-Pose.
See: notebooks/03_pose_eval.ipynb

Critical keypoints per test:
    Jump:          15=l_ankle, 16=r_ankle   (ankle height above floor)
    Balance:       15, 16 (ankles), 11, 12 (hips), 0 (nose)
    Sprint/Agility: 11, 12 (hips) — body centroid proxy
    Shuttle:       11, 12 (hips) — direction reversal detection

Decision log:
    Date | Model | Test Type | Keypoint Accuracy | Latency (12 students) | Verdict
    ——   | ——    | ——        | ——                | ——                    | ——
"""
from __future__ import annotations

import logging

import cv2
import numpy as np

from pipeline.models import Pose, Track

logger = logging.getLogger(__name__)

# COCO keypoint indices for reference
COCO_NOSE = 0
COCO_L_SHOULDER, COCO_R_SHOULDER = 5, 6
COCO_L_HIP, COCO_R_HIP = 11, 12
COCO_L_KNEE, COCO_R_KNEE = 13, 14
COCO_L_ANKLE, COCO_R_ANKLE = 15, 16


def expand_bbox(
    x1: float, y1: float, x2: float, y2: float,
    expand: float = 0.25,
    img_h: int = 1080,
    img_w: int = 1920,
) -> tuple[float, float, float, float]:
    """
    Expand bounding box by `expand` fraction on each side.
    Improves keypoint accuracy at body edges.
    """
    w, h = x2 - x1, y2 - y1
    x1 = max(0, x1 - w * expand / 2)
    y1 = max(0, y1 - h * expand / 2)
    x2 = min(img_w, x2 + w * expand / 2)
    y2 = min(img_h, y2 + h * expand / 2)
    return x1, y1, x2, y2


class PoseEstimator:
    """
    Top-down pose estimator: crops each tracked person bbox, runs RTMPose-m.

    Evaluation criteria:
        - Ankle keypoints accurate for ≥ 90% of frames in jump clip
        - Hip midpoint within ±5 px of manual annotation across sprint clip
        - Batch inference for 12 students < 80 ms per frame on L4
        - Pose confidence flag correctly identifies low-quality frames
    """

    def __init__(
        self,
        model_path: str = "rtmpose-m.onnx",
        device: str = "cuda",
        bbox_expand: float = 0.25,
    ):
        self.model_path = model_path
        self.device = device
        self.bbox_expand = bbox_expand
        self._session = None  # ONNX Runtime session

    def _load_model(self):
        try:
            import onnxruntime as ort  # type: ignore

            providers = (
                ["CUDAExecutionProvider", "CPUExecutionProvider"]
                if self.device == "cuda"
                else ["CPUExecutionProvider"]
            )
            self._session = ort.InferenceSession(self.model_path, providers=providers)
            logger.info("RTMPose ONNX session loaded: %s", self.model_path)
        except ImportError:
            raise ImportError("onnxruntime not installed. Run: pip install onnxruntime-gpu")

    def _preprocess_crop(self, crop: np.ndarray) -> np.ndarray:
        """Resize and normalise crop for RTMPose-m (256×192 input)."""
        resized = cv2.resize(crop, (192, 256))
        img = resized.astype(np.float32) / 255.0
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        img = (img - mean) / std
        return img.transpose(2, 0, 1)[np.newaxis]  # (1, 3, 256, 192)

    def _postprocess(
        self, output: np.ndarray, x1: float, y1: float, x2: float, y2: float
    ) -> tuple[np.ndarray, float]:
        """
        Convert heatmap output to (17, 3) keypoints in original frame coords.
        Returns (keypoints, mean_confidence).
        """
        # RTMPose outputs SimCC distribution — simplified stub
        # TODO: implement full SimCC decoding
        kps = np.zeros((17, 3), dtype=np.float32)
        w, h = x2 - x1, y2 - y1
        # Placeholder: centre of bbox for all keypoints
        for i in range(17):
            kps[i] = [x1 + w / 2, y1 + h / 2, 0.0]
        mean_conf = float(kps[:, 2].mean())
        return kps, mean_conf

    def estimate(self, frame: np.ndarray, tracks: list[Track]) -> list[Pose]:
        """
        Run pose estimation on all tracked persons in a single frame.
        Each track is cropped individually (top-down approach).
        """
        if self._session is None:
            self._load_model()

        poses: list[Pose] = []
        img_h, img_w = frame.shape[:2]

        for track in tracks:
            x1, y1, x2, y2 = expand_bbox(*track.bbox, self.bbox_expand, img_h, img_w)
            crop = frame[int(y1):int(y2), int(x1):int(x2)]
            if crop.size == 0:
                continue

            inp = self._preprocess_crop(crop)
            output = self._session.run(None, {self._session.get_inputs()[0].name: inp})[0]
            keypoints, conf = self._postprocess(output, x1, y1, x2, y2)

            poses.append(
                Pose(
                    track_id=track.track_id,
                    frame_idx=track.frame_idx,
                    keypoints=keypoints,
                    pose_confidence=conf,
                )
            )
        return poses

    def estimate_batch(self, frame: np.ndarray, tracks: list[Track]) -> list[Pose]:
        """
        Batch all crops into a single ONNX inference call for throughput.
        Preferred for frames with many students (shuttle/agility tests).
        """
        if self._session is None:
            self._load_model()

        if not tracks:
            return []

        img_h, img_w = frame.shape[:2]
        batch, meta = [], []

        for track in tracks:
            x1, y1, x2, y2 = expand_bbox(*track.bbox, self.bbox_expand, img_h, img_w)
            crop = frame[int(y1):int(y2), int(x1):int(x2)]
            if crop.size == 0:
                continue
            batch.append(self._preprocess_crop(crop)[0])  # (3, 256, 192)
            meta.append((track, x1, y1, x2, y2))

        if not batch:
            return []

        batch_np = np.stack(batch, axis=0)  # (N, 3, 256, 192)
        outputs = self._session.run(None, {self._session.get_inputs()[0].name: batch_np})[0]

        poses: list[Pose] = []
        for i, (track, x1, y1, x2, y2) in enumerate(meta):
            keypoints, conf = self._postprocess(outputs[i:i+1], x1, y1, x2, y2)
            poses.append(
                Pose(
                    track_id=track.track_id,
                    frame_idx=track.frame_idx,
                    keypoints=keypoints,
                    pose_confidence=conf,
                )
            )
        return poses

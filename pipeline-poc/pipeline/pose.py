"""
Module 4 — Pose Estimation (Top-Down)
Interface: PoseEstimator.estimate(frame, tracks) → list[Pose]

Uses mmpose inference (init_model + inference_topdown) for RTMPose-m.
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
from pathlib import Path

import numpy as np

from pipeline.models import Pose, Track

logger = logging.getLogger(__name__)

# COCO keypoint indices for reference
COCO_NOSE = 0
COCO_L_SHOULDER, COCO_R_SHOULDER = 5, 6
COCO_L_HIP, COCO_R_HIP = 11, 12
COCO_L_KNEE, COCO_R_KNEE = 13, 14
COCO_L_ANKLE, COCO_R_ANKLE = 15, 16

# mmpose RTMPose-m body (COCO 17 keypoints) — config + checkpoint
RTMPOSE_M_CONFIG = "body_2d_keypoint/rtmpose/coco/rtmpose-m_8xb256-420e_aic-coco-256x192.py"
RTMPOSE_M_CHECKPOINT = (
    "https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/"
    "rtmpose-m_simcc-aic-coco_pt-aic-coco_420e-256x192-63eb25f7_20230126.pth"
)


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


def _to_numpy(x):
    """Convert tensor or array to numpy."""
    if hasattr(x, "cpu"):
        return x.cpu().numpy()
    return np.asarray(x)


def _mmpose_result_to_pose(
    data_sample, track_id: int, frame_idx: int
) -> Pose | None:
    """Convert mmpose PoseDataSample to pipeline Pose."""
    if not hasattr(data_sample, "pred_instances") or data_sample.pred_instances is None:
        return None
    pred = data_sample.pred_instances
    kpts = _to_numpy(pred.keypoints)  # (1, 17, 2) or (1, 17, 3)
    if kpts.size == 0:
        return None
    kpts = kpts.reshape(-1, kpts.shape[-1])
    if kpts.shape[0] != 17:
        return None
    # Ensure (17, 3): x, y, confidence
    if kpts.shape[1] == 2:
        scores = _to_numpy(pred.keypoint_scores) if hasattr(pred, "keypoint_scores") else np.ones(17)
        if scores.ndim > 1:
            scores = scores.reshape(-1)
        kpts = np.column_stack([kpts[:, 0], kpts[:, 1], scores[:17]])
    keypoints = np.asarray(kpts, dtype=np.float32)
    mean_conf = float(np.mean(keypoints[:, 2]))
    return Pose(
        track_id=track_id,
        frame_idx=frame_idx,
        keypoints=keypoints,
        pose_confidence=mean_conf,
    )


class PoseEstimator:
    """
    Top-down pose estimator using mmpose RTMPose-m.

    Uses init_model + inference_topdown for proper SimCC decoding and
    keypoint visualization.
    """

    def __init__(
        self,
        config: str | None = None,
        checkpoint: str | None = None,
        device: str = "cuda",
        bbox_expand: float = 0.25,
    ):
        self.config = config or RTMPOSE_M_CONFIG
        self.checkpoint = checkpoint or RTMPOSE_M_CHECKPOINT
        self.device = device
        self.bbox_expand = bbox_expand
        self._model = None

    def _load_model(self):
        if self._model is not None:
            return
        try:
            from mmpose.apis import init_model
            import mmpose

            config_path = Path(mmpose.__file__).parent / ".mim" / "configs" / self.config
            if not config_path.is_file():
                raise FileNotFoundError(
                    f"mmpose config not found: {config_path}\n"
                    "Ensure mmpose is installed: pip install mmpose"
                )
            self._model = init_model(
                str(config_path),
                self.checkpoint,
                device=self.device,
            )
            logger.info(
                "RTMPose-m loaded via mmpose (config=%s, device=%s)",
                self.config,
                self.device,
            )
        except RuntimeError as e:
            if self.device == "cuda" and (
                "no kernel image" in str(e).lower() or "not compatible" in str(e).lower()
            ):
                logger.warning(
                    "CUDA not supported by this PyTorch build. Falling back to CPU for pose."
                )
                self.device = "cpu"
                self._load_model()
            else:
                raise
        except ImportError as err:
            raise ImportError(
                "mmpose not installed. Run: pip install mmpose && mim install mmcv mmengine"
            ) from err

    def estimate(self, frame: np.ndarray, tracks: list[Track]) -> list[Pose]:
        """Run pose estimation on all tracked persons in a single frame."""
        if not tracks:
            return []
        self._load_model()
        img_h, img_w = frame.shape[:2]
        bboxes = []
        valid_tracks = []
        for track in tracks:
            x1, y1, x2, y2 = expand_bbox(*track.bbox, self.bbox_expand, img_h, img_w)
            if x2 <= x1 or y2 <= y1:
                continue
            bboxes.append([x1, y1, x2, y2])
            valid_tracks.append(track)
        if not bboxes:
            return []
        bboxes_np = np.array(bboxes, dtype=np.float32)
        try:
            from mmpose.apis import inference_topdown

            results = inference_topdown(
                self._model, frame, bboxes=bboxes_np, bbox_format="xyxy"
            )
        except RuntimeError as e:
            if self.device == "cuda" and "no kernel image" in str(e).lower():
                logger.warning("Falling back to CPU for pose inference.")
                self.device = "cpu"
                self._model = None
                self._load_model()
                from mmpose.apis import inference_topdown

                results = inference_topdown(
                    self._model, frame, bboxes=bboxes_np, bbox_format="xyxy"
                )
            else:
                raise
        poses = []
        for i, (track, ds) in enumerate(zip(valid_tracks, results)):
            pose = _mmpose_result_to_pose(ds, track.track_id, track.frame_idx)
            if pose is not None:
                poses.append(pose)
        return poses

    def estimate_batch(self, frame: np.ndarray, tracks: list[Track]) -> list[Pose]:
        """
        Batch pose estimation — same as estimate for mmpose (it batches internally).
        Kept for API compatibility.
        """
        return self.estimate(frame, tracks)

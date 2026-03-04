"""
Module 2 — Person Detection
Interface: PersonDetector.detect(frame) → list[Detection]

Recommended approach: YOLOv8s exported to ONNX, person class only.
Alternatives: YOLOv8m, YOLOv8n, RT-DETR, YOLOv9, Detectron2.
See: notebooks/01_detection_eval.ipynb
"""
from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

from pipeline.models import Detection

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

class PersonDetector:
    """
    Wraps a YOLO-family model for person detection.

    Evaluation criteria:
        - Recall ≥ 95% across all 5 test clip types
        - Precision ≥ 90%
        - ≤ 6 ms per frame on L4 GPU for 1080p input
        - Handles partially occluded students

    Decision log:
        Date | Model | Precision | Recall | Latency | Verdict
        ——   | ——    | ——        | ——     | ——      | ——
    """

    PERSON_CLASS_ID = 0

    def __init__(
        self,
        model_path: str | Path = "yolov8s.pt",
        device: str = "cuda",
        conf_threshold: float = 0.5,
        nms_threshold: float = 0.4,
    ):
        self.model_path = str(model_path)
        self.device = device
        self.conf_threshold = conf_threshold
        self.nms_threshold = nms_threshold
        self._model = None  # lazy load

    def _load_model(self):
        """Lazy-load model on first inference call."""
        try:
            from ultralytics import YOLO  # type: ignore
            self._model = YOLO(self.model_path)
            logger.info("Loaded YOLOv8 model: %s on %s", self.model_path, self.device)
        except ImportError:
            raise ImportError(
                "ultralytics not installed. Run: pip install ultralytics"
            )

    def detect(self, frame: np.ndarray, conf_threshold: float | None = None) -> list[Detection]:
        """
        Run person detection on a single BGR frame.

        Args:
            frame: BGR numpy array (H, W, 3).
            conf_threshold: Override instance default if provided.

        Returns:
            List of Detection dataclasses, person class only.
        """
        if self._model is None:
            self._load_model()

        conf = conf_threshold if conf_threshold is not None else self.conf_threshold
        results = self._model.predict(
            source=frame,
            conf=conf,
            iou=self.nms_threshold,
            classes=[self.PERSON_CLASS_ID],
            verbose=False,
            device=self.device,
        )

        detections: list[Detection] = []
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                detections.append(
                    Detection(
                        bbox=(x1, y1, x2, y2),
                        confidence=float(box.conf[0]),
                        class_id=int(box.cls[0]),
                        frame_idx=-1,  # caller sets frame_idx
                    )
                )
        return detections

    def detect_batch(
        self, frames: list[np.ndarray], conf_threshold: float | None = None
    ) -> list[list[Detection]]:
        """
        Run detection on a batch of frames for throughput efficiency.

        Returns:
            List of per-frame Detection lists.
        """
        if self._model is None:
            self._load_model()

        conf = conf_threshold if conf_threshold is not None else self.conf_threshold
        results = self._model.predict(
            source=frames,
            conf=conf,
            iou=self.nms_threshold,
            classes=[self.PERSON_CLASS_ID],
            verbose=False,
            device=self.device,
        )

        batch_detections: list[list[Detection]] = []
        for result in results:
            frame_dets = []
            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                frame_dets.append(
                    Detection(
                        bbox=(x1, y1, x2, y2),
                        confidence=float(box.conf[0]),
                        class_id=int(box.cls[0]),
                        frame_idx=-1,
                    )
                )
            batch_detections.append(frame_dets)
        return batch_detections

    def export_onnx(self, output_path: str = "yolov8s.onnx") -> str:
        """Export loaded .pt model to ONNX for runtime inference."""
        if self._model is None:
            self._load_model()
        self._model.export(format="onnx")
        logger.info("ONNX exported to %s", output_path)
        return output_path

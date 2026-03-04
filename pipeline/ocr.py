"""
Module 5 — Bib Number OCR
Interface:
    BibOCR.read_frame(frame, tracks) → dict[track_id, bib_number | None]
    resolve_bibs(frame_readings, min_confidence) → dict[track_id, (bib_number, confidence)]

Recommended approach: PaddleOCR PP-OCRv4 with CLAHE contrast enhancement.
Alternatives: EasyOCR, Tesseract, custom YOLOv8 digit detector, template matching.

Sampling: read every 5th frame (clearer stills improve accuracy vs motion blur).
Majority vote: resolve_bibs() aggregates per-track reads across all frames.

Decision log:
    Date | Approach | Auto-Resolve % | False Positive Rate | Verdict
    ——   | ——       | ——             | ——                  | ——
"""
from __future__ import annotations

import collections
import logging

import cv2
import numpy as np

from pipeline.models import Track

logger = logging.getLogger(__name__)


class BibOCR:
    """
    Reads numbered bibs from the upper-torso region of each tracked person.

    Evaluation criteria:
        - Auto-resolve rate ≥ 80% of tracks without manual correction
        - Zero false positives (wrong bib number confidently assigned)
        - Majority vote confidence calibrated: 0.6 threshold → <10% wrong
        - bib_unresolved flag triggers correctly on ambiguous tracks
    """

    # Upper-torso crop = top N% of bounding box height
    TORSO_CROP_FRACTION = 0.40

    def __init__(self, min_bib: int = 1, max_bib: int = 30):
        self.min_bib = min_bib
        self.max_bib = max_bib
        self._ocr = None

    def _load_ocr(self):
        try:
            from paddleocr import PaddleOCR  # type: ignore

            self._ocr = PaddleOCR(
                use_angle_cls=True,
                lang="en",
                use_gpu=True,
                show_log=False,
            )
            logger.info("PaddleOCR PP-OCRv4 loaded.")
        except ImportError:
            raise ImportError(
                "paddleocr not installed. Run: pip install paddlepaddle-gpu paddleocr"
            )

    def _enhance_crop(self, crop_bgr: np.ndarray) -> np.ndarray:
        """CLAHE contrast enhancement on grayscale crop."""
        gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
        return clahe.apply(gray)

    def _read_bib(self, enhanced_crop: np.ndarray) -> int | None:
        """
        Run PaddleOCR on a single enhanced crop.
        Returns numeric bib value in [min_bib, max_bib] or None.
        """
        if self._ocr is None:
            self._load_ocr()

        result = self._ocr.ocr(enhanced_crop, cls=True)
        for line in (result or [[]]):
            for _box, (text, _conf) in (line or []):
                clean = text.strip().replace(" ", "")
                if clean.isdigit():
                    val = int(clean)
                    if self.min_bib <= val <= self.max_bib:
                        return val
        return None

    def read_frame(
        self, frame: np.ndarray, tracks: list[Track]
    ) -> dict[int, int | None]:
        """
        Read bib number for each track from the upper-torso crop.
        Returns single-frame reads — call resolve_bibs() to aggregate.

        Args:
            frame:  Full BGR video frame.
            tracks: Active tracks for this frame.

        Returns:
            {track_id: bib_number_or_None}
        """
        if self._ocr is None:
            self._load_ocr()

        readings: dict[int, int | None] = {}
        img_h, img_w = frame.shape[:2]

        for track in tracks:
            x1, y1, x2, y2 = track.bbox
            # Upper-torso crop
            torso_y2 = y1 + (y2 - y1) * self.TORSO_CROP_FRACTION
            crop = frame[
                int(max(0, y1)):int(min(img_h, torso_y2)),
                int(max(0, x1)):int(min(img_w, x2)),
            ]
            if crop.size == 0:
                readings[track.track_id] = None
                continue

            enhanced = self._enhance_crop(crop)
            readings[track.track_id] = self._read_bib(enhanced)

        return readings


def resolve_bibs(
    frame_readings: list[dict[int, int | None]],
    min_confidence: float = 0.6,
) -> dict[int, tuple[int | None, float]]:
    """
    Aggregate per-frame bib reads for each track via majority vote.

    Args:
        frame_readings:  List of per-frame {track_id: bib_number_or_None} dicts.
        min_confidence:  Minimum vote fraction to accept a bib assignment.

    Returns:
        {track_id: (resolved_bib_or_None, confidence_score)}
        Flags 'bib_unresolved' in calling code when resolved_bib is None.
    """
    # Accumulate votes per track
    vote_counts: dict[int, collections.Counter] = collections.defaultdict(
        collections.Counter
    )
    for frame_dict in frame_readings:
        for track_id, bib in frame_dict.items():
            if bib is not None:
                vote_counts[track_id][bib] += 1

    # Collect all track IDs seen
    all_track_ids: set[int] = set()
    for frame_dict in frame_readings:
        all_track_ids.update(frame_dict.keys())

    resolved: dict[int, tuple[int | None, float]] = {}
    for track_id in all_track_ids:
        counter = vote_counts.get(track_id)
        if not counter:
            resolved[track_id] = (None, 0.0)
            continue
        total_reads = sum(counter.values())
        best_bib, best_count = counter.most_common(1)[0]
        confidence = best_count / total_reads if total_reads > 0 else 0.0
        if confidence >= min_confidence:
            resolved[track_id] = (best_bib, confidence)
        else:
            resolved[track_id] = (None, confidence)

    return resolved

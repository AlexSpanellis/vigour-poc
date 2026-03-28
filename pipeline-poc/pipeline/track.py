"""
Module 3 — Multi-Person Tracking
Interface: PersonTracker.update(detections, frame_idx) → list[Track]

Recommended approach: ByteTrack.
Alternatives: OC-SORT, BoT-SORT, DeepSORT (Fast-ReID), Simple IOU tracker.
See: notebooks/02_tracking_eval.ipynb

Critical test — shuttle sprints: 10–12 students moving in same direction.
    - Two students crossing paths
    - Student briefly leaving + re-entering frame
    - Near-identical body sizes and uniforms

Decision log:
    Date | Tracker | Config | ID Switches | Track Continuity | Verdict
    ——   | ——      | ——     | ——          | ——               | ——
"""
from __future__ import annotations

import logging

from pipeline.models import Detection, Track

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Default ByteTrack config — tune per test type
# ---------------------------------------------------------------------------

DEFAULT_BYTETRACK_CONFIG = {
    "track_thresh": 0.5,    # confidence to activate a new track
    "track_buffer": 30,     # frames to keep lost track alive (2 s @ 15 fps)
    "match_thresh": 0.8,    # IOU threshold for track matching
    "min_box_area": 10,     # filter tiny detections
    "frame_rate": 15,       # must match ingestion fps
}


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

class PersonTracker:
    """
    Multi-person tracker wrapping ByteTrack.

    Evaluation criteria:
        - ID switch rate < 5% across full-length test clips
        - Track continuity: each student holds single ID for ≥ 90% of clip
        - Recovery after 30-frame occlusion (2 seconds @ 15fps)
        - Bib OCR majority vote can compensate for remaining ID switches
    """

    def __init__(self, config: dict | None = None):
        self.config = config or DEFAULT_BYTETRACK_CONFIG
        self._tracker = None
        self._load_tracker()

    def _load_tracker(self):
        """Initialise ByteTrack instance."""
        try:
            from bytetracker import BYTETracker  # type: ignore

            self._tracker = BYTETracker(
                track_thresh=self.config["track_thresh"],
                track_buffer=self.config["track_buffer"],
                match_thresh=self.config["match_thresh"],
                frame_rate=self.config["frame_rate"],
            )
            logger.info("ByteTrack initialised with config: %s", self.config)
        except ImportError:
            logger.warning(
                "bytetracker not installed. Install with: pip install bytetracker  "
                "Tracker will return empty lists until installed."
            )
            self._tracker = None

    def update(self, detections: list[Detection], frame_idx: int) -> list[Track]:
        """
        Feed one frame's detections; return active tracks with stable IDs.

        Args:
            detections: Output from PersonDetector.detect() for this frame.
            frame_idx:  Current frame index.

        Returns:
            List of Track dataclasses.
        """
        if self._tracker is None:
            logger.error("Tracker not initialised. Returning empty track list.")
            return []

        import numpy as np

        if not detections:
            # ByteTrack expects [x1, y1, x2, y2, score, class_id]; empty = 6 cols
            dets_np = np.empty((0, 6), dtype=np.float32)
        else:
            # ByteTrack expects [x1, y1, x2, y2, score, class_id]
            dets_np = np.array(
                [[*d.bbox, d.confidence, float(d.class_id)] for d in detections],
                dtype=np.float32,
            )
        # This bytetracker expects PyTorch tensors (it calls .numpy() on slices)
        import torch
        dets_tensor = torch.from_numpy(dets_np)
        online_outputs = self._tracker.update(dets_tensor, None)

        # BYTETracker returns np.array of shape (N, 7): [x1, y1, x2, y2, track_id, cls, score]
        tracks: list[Track] = []
        if online_outputs.size > 0:
            # ensure 2D: (0,) -> (0, 7)
            if online_outputs.ndim == 1:
                online_outputs = online_outputs.reshape(-1, 7)
            for row in online_outputs:
                x1, y1, x2, y2 = float(row[0]), float(row[1]), float(row[2]), float(row[3])
                track_id = int(row[4])
                is_confirmed = True  # output_stracks are activated only
                tracks.append(
                    Track(
                        track_id=track_id,
                        bbox=(x1, y1, x2, y2),
                        frame_idx=frame_idx,
                        is_confirmed=is_confirmed,
                        bib_number=None,
                        bib_confidence=0.0,
                    )
                )
        return tracks

    def reset(self):
        """Clear all track state between sessions / clips."""
        self._load_tracker()
        logger.info("Tracker state reset.")

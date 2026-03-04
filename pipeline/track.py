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
            # bytetracker pip package exposes BYTETracker
            from bytetracker import BYTETracker  # type: ignore

            class _Args:
                track_thresh = self.config["track_thresh"]
                track_buffer = self.config["track_buffer"]
                match_thresh = self.config["match_thresh"]
                min_box_area = self.config["min_box_area"]
                mot20 = False

            self._tracker = BYTETracker(_Args(), frame_rate=self.config["frame_rate"])
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
            online_targets = self._tracker.update(
                np.empty((0, 5)), [1080, 1920], [1080, 1920]
            )
        else:
            # ByteTrack expects [x1, y1, x2, y2, score]
            dets_np = np.array(
                [[*d.bbox, d.confidence] for d in detections], dtype=np.float32
            )
            online_targets = self._tracker.update(dets_np, [1080, 1920], [1080, 1920])

        tracks: list[Track] = []
        for t in online_targets:
            tlwh = t.tlwh
            x1, y1 = tlwh[0], tlwh[1]
            x2, y2 = x1 + tlwh[2], y1 + tlwh[3]
            tracks.append(
                Track(
                    track_id=int(t.track_id),
                    bbox=(x1, y1, x2, y2),
                    frame_idx=frame_idx,
                    is_confirmed=t.is_activated,
                    bib_number=None,
                    bib_confidence=0.0,
                )
            )
        return tracks

    def reset(self):
        """Clear all track state between sessions / clips."""
        self._load_tracker()
        logger.info("Tracker state reset.")

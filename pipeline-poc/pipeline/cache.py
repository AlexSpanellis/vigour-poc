"""
Module 9 — Pipeline Stage Cache
Saves and loads intermediate pipeline outputs per job ID, enabling:

  1. Replay / review without re-running upstream stages
     e.g. Tweak the metric extractor config and re-run only Stage 7,
          loading cached tracks/poses from disk.

  2. Test fixtures — load real pipeline outputs as ground-truth inputs
     for unit and integration tests.

  3. Notebook inspection — load any cached stage into a notebook
     for frame-by-frame analysis.

Directory layout:
    data/cache/
    └── {job_id}/
        ├── manifest.json          ← stage list, timestamps, metadata
        ├── stage_ingest.json      ← frame index + timestamp list
        ├── stage_detect.npz       ← per-frame detection arrays
        ├── stage_track.npz        ← per-frame track arrays + bib fields
        ├── stage_pose.npz         ← per-frame keypoint arrays
        ├── stage_ocr.json         ← per-frame bib readings + resolved map
        ├── stage_calibrate.npz    ← calibration result
        └── stage_results.json     ← final TestResult list

Usage:

    from pipeline.cache import PipelineCache

    cache = PipelineCache(job_id="abc123")

    # Save after detection
    cache.save_detections(all_detections)

    # Check before running tracking (skip if already cached)
    if cache.has("track"):
        all_tracks = cache.load_tracks()
    else:
        all_tracks = tracker.update(...)
        cache.save_tracks(all_tracks)

    # Load as test fixtures in pytest
    cache = PipelineCache.from_path("data/cache/abc123")
    tracks = cache.load_tracks()
    poses  = cache.load_poses()
"""
from __future__ import annotations

import json
import logging
import os
import pickle
import shutil
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from pipeline.models import (
    CalibrationResult,
    Detection,
    Pose,
    TestResult,
    Track,
)

logger = logging.getLogger(__name__)

CACHE_ROOT = Path(os.getenv("CACHE_DIR", "data/cache"))

# Stages in pipeline order
STAGES = ["ingest", "detect", "track", "pose", "ocr", "calibrate", "results"]


class PipelineCache:
    """
    File-based cache for all intermediate pipeline stage outputs.

    Each stage is saved atomically: a temp file is written first,
    then renamed, so a crashed worker never leaves a corrupt cache entry.
    """

    def __init__(self, job_id: str, cache_root: str | Path | None = None):
        self.job_id = job_id
        self.root = Path(cache_root or CACHE_ROOT) / job_id
        self.root.mkdir(parents=True, exist_ok=True)
        self._manifest_path = self.root / "manifest.json"
        self._manifest = self._load_manifest()

    # ── Factory ──────────────────────────────────────────────────────────────

    @classmethod
    def from_path(cls, path: str | Path) -> "PipelineCache":
        """Load cache from an absolute directory path."""
        p = Path(path)
        return cls(job_id=p.name, cache_root=p.parent)

    @classmethod
    def list_jobs(cls, cache_root: str | Path | None = None) -> list[dict]:
        """
        Return a summary of all cached jobs.

        Returns:
            List of dicts: {job_id, stages_cached, created_at, size_mb}
        """
        root = Path(cache_root or CACHE_ROOT)
        jobs = []
        if not root.exists():
            return jobs
        for job_dir in sorted(root.iterdir()):
            if not job_dir.is_dir():
                continue
            manifest_file = job_dir / "manifest.json"
            if not manifest_file.exists():
                continue
            with open(manifest_file) as f:
                manifest = json.load(f)
            size_bytes = sum(f.stat().st_size for f in job_dir.rglob("*") if f.is_file())
            jobs.append({
                "job_id":       job_dir.name,
                "stages_cached": list(manifest.get("stages", {}).keys()),
                "created_at":    manifest.get("created_at"),
                "test_type":     manifest.get("test_type"),
                "size_mb":       round(size_bytes / (1024 * 1024), 2),
            })
        return jobs

    # ── has / invalidate ──────────────────────────────────────────────────────

    def has(self, stage: str) -> bool:
        """Return True if this stage has a valid cached entry."""
        return stage in self._manifest.get("stages", {})

    def invalidate(self, stage: str) -> None:
        """Remove a stage from the cache (and all downstream stages)."""
        stage_idx = STAGES.index(stage) if stage in STAGES else len(STAGES)
        to_remove = STAGES[stage_idx:]
        for s in to_remove:
            self._manifest.get("stages", {}).pop(s, None)
            for f in self.root.glob(f"stage_{s}.*"):
                f.unlink(missing_ok=True)
            logger.info("[cache] Invalidated stage '%s' for job %s", s, self.job_id)
        self._save_manifest()

    def clear(self) -> None:
        """Delete the entire cache for this job."""
        shutil.rmtree(self.root, ignore_errors=True)
        logger.info("[cache] Cleared all cache for job %s", self.job_id)

    def summary(self) -> dict:
        """Return cache metadata and per-stage info."""
        size_bytes = sum(f.stat().st_size for f in self.root.rglob("*") if f.is_file())
        return {
            "job_id":        self.job_id,
            "cache_dir":     str(self.root),
            "stages_cached": list(self._manifest.get("stages", {}).keys()),
            "test_type":     self._manifest.get("test_type"),
            "created_at":    self._manifest.get("created_at"),
            "size_mb":       round(size_bytes / (1024 * 1024), 2),
        }

    # ── Ingest ────────────────────────────────────────────────────────────────

    def save_ingest(
        self,
        frame_indices: list[int],
        timestamps_s: list[float],
        test_type: str = "",
    ) -> None:
        """Cache frame index / timestamp metadata (not raw frames — too large)."""
        data = {"frame_indices": frame_indices, "timestamps_s": timestamps_s}
        self._write_json("stage_ingest.json", data)
        self._manifest.setdefault("stages", {})["ingest"] = _ts()
        self._manifest["test_type"] = test_type
        self._manifest.setdefault("created_at", _ts())
        self._save_manifest()
        logger.info("[cache] Saved ingest: %d frames (job=%s)", len(frame_indices), self.job_id)

    def load_ingest(self) -> tuple[list[int], list[float]]:
        data = self._read_json("stage_ingest.json")
        return data["frame_indices"], data["timestamps_s"]

    # ── Detections ────────────────────────────────────────────────────────────

    def save_detections(self, all_detections: list[list[Detection]]) -> None:
        """
        Serialise per-frame detection lists to a compressed .npz file.
        Schema:
            dets_{frame_i}  → float32 array (N, 5): x1, y1, x2, y2, confidence
            conf_{frame_i}  → float32 array (N,)   confidence scores
            fidx_{frame_i}  → int: frame_idx
        """
        arrays: dict[str, Any] = {}
        for i, dets in enumerate(all_detections):
            if dets:
                bboxes = np.array([[*d.bbox, d.confidence] for d in dets], dtype=np.float32)
                fidxs = np.array([d.frame_idx for d in dets], dtype=np.int32)
            else:
                bboxes = np.empty((0, 5), dtype=np.float32)
                fidxs  = np.empty((0,), dtype=np.int32)
            arrays[f"bboxes_{i}"] = bboxes
            arrays[f"fidxs_{i}"]  = fidxs
        arrays["n_frames"] = np.array([len(all_detections)], dtype=np.int32)
        self._write_npz("stage_detect.npz", arrays)
        self._manifest.setdefault("stages", {})["detect"] = _ts()
        self._save_manifest()
        logger.info("[cache] Saved detections: %d frames (job=%s)", len(all_detections), self.job_id)

    def load_detections(self) -> list[list[Detection]]:
        data = self._read_npz("stage_detect.npz")
        n = int(data["n_frames"][0])
        result = []
        for i in range(n):
            bboxes = data[f"bboxes_{i}"]
            fidxs  = data[f"fidxs_{i}"]
            dets = [
                Detection(
                    bbox=(float(b[0]), float(b[1]), float(b[2]), float(b[3])),
                    confidence=float(b[4]),
                    class_id=0,
                    frame_idx=int(fidxs[j]) if j < len(fidxs) else -1,
                )
                for j, b in enumerate(bboxes)
            ]
            result.append(dets)
        return result

    # ── Tracks ────────────────────────────────────────────────────────────────

    def save_tracks(self, all_tracks: list[list[Track]]) -> None:
        arrays: dict[str, Any] = {}
        for i, tracks in enumerate(all_tracks):
            if tracks:
                bboxes = np.array([[*t.bbox] for t in tracks], dtype=np.float32)
                ids    = np.array([t.track_id for t in tracks], dtype=np.int32)
                fidxs  = np.array([t.frame_idx for t in tracks], dtype=np.int32)
                bibs   = np.array([t.bib_number if t.bib_number is not None else -1 for t in tracks], dtype=np.int32)
                bconfs = np.array([t.bib_confidence for t in tracks], dtype=np.float32)
                confs  = np.array([int(t.is_confirmed) for t in tracks], dtype=np.int8)
            else:
                bboxes = np.empty((0, 4), dtype=np.float32)
                ids    = np.empty((0,), dtype=np.int32)
                fidxs  = np.empty((0,), dtype=np.int32)
                bibs   = np.empty((0,), dtype=np.int32)
                bconfs = np.empty((0,), dtype=np.float32)
                confs  = np.empty((0,), dtype=np.int8)
            arrays[f"bboxes_{i}"] = bboxes
            arrays[f"ids_{i}"]    = ids
            arrays[f"fidxs_{i}"]  = fidxs
            arrays[f"bibs_{i}"]   = bibs
            arrays[f"bconfs_{i}"] = bconfs
            arrays[f"confs_{i}"]  = confs
        arrays["n_frames"] = np.array([len(all_tracks)], dtype=np.int32)
        self._write_npz("stage_track.npz", arrays)
        self._manifest.setdefault("stages", {})["track"] = _ts()
        self._save_manifest()
        logger.info("[cache] Saved tracks: %d frames (job=%s)", len(all_tracks), self.job_id)

    def load_tracks(self) -> list[list[Track]]:
        data = self._read_npz("stage_track.npz")
        n = int(data["n_frames"][0])
        result = []
        for i in range(n):
            bboxes = data[f"bboxes_{i}"]
            ids    = data[f"ids_{i}"]
            fidxs  = data[f"fidxs_{i}"]
            bibs   = data[f"bibs_{i}"]
            bconfs = data[f"bconfs_{i}"]
            confs  = data[f"confs_{i}"]
            frame_tracks = [
                Track(
                    track_id=int(ids[j]),
                    bbox=(float(bboxes[j, 0]), float(bboxes[j, 1]), float(bboxes[j, 2]), float(bboxes[j, 3])),
                    frame_idx=int(fidxs[j]),
                    is_confirmed=bool(confs[j]),
                    bib_number=int(bibs[j]) if bibs[j] >= 0 else None,
                    bib_confidence=float(bconfs[j]),
                )
                for j in range(len(ids))
            ]
            result.append(frame_tracks)
        return result

    # ── Poses ─────────────────────────────────────────────────────────────────

    def save_poses(self, all_poses: list[list[Pose]]) -> None:
        arrays: dict[str, Any] = {}
        for i, poses in enumerate(all_poses):
            if poses:
                kps      = np.stack([p.keypoints for p in poses], axis=0)   # (N, 17, 3)
                ids      = np.array([p.track_id for p in poses], dtype=np.int32)
                fidxs    = np.array([p.frame_idx for p in poses], dtype=np.int32)
                pconfs   = np.array([p.pose_confidence for p in poses], dtype=np.float32)
            else:
                kps    = np.empty((0, 17, 3), dtype=np.float32)
                ids    = np.empty((0,), dtype=np.int32)
                fidxs  = np.empty((0,), dtype=np.int32)
                pconfs = np.empty((0,), dtype=np.float32)
            arrays[f"kps_{i}"]    = kps
            arrays[f"ids_{i}"]    = ids
            arrays[f"fidxs_{i}"]  = fidxs
            arrays[f"pconfs_{i}"] = pconfs
        arrays["n_frames"] = np.array([len(all_poses)], dtype=np.int32)
        self._write_npz("stage_pose.npz", arrays)
        self._manifest.setdefault("stages", {})["pose"] = _ts()
        self._save_manifest()
        logger.info("[cache] Saved poses: %d frames (job=%s)", len(all_poses), self.job_id)

    def load_poses(self) -> list[list[Pose]]:
        data = self._read_npz("stage_pose.npz")
        n = int(data["n_frames"][0])
        result = []
        for i in range(n):
            kps    = data[f"kps_{i}"]
            ids    = data[f"ids_{i}"]
            fidxs  = data[f"fidxs_{i}"]
            pconfs = data[f"pconfs_{i}"]
            frame_poses = [
                Pose(
                    track_id=int(ids[j]),
                    frame_idx=int(fidxs[j]),
                    keypoints=kps[j].astype(np.float32),
                    pose_confidence=float(pconfs[j]),
                )
                for j in range(len(ids))
            ]
            result.append(frame_poses)
        return result

    # ── OCR ───────────────────────────────────────────────────────────────────

    def save_ocr(
        self,
        frame_readings: list[dict[int, int | None]],
        resolved: dict[int, tuple[int | None, float]],
    ) -> None:
        data = {
            "frame_readings": [
                {str(k): v for k, v in r.items()} for r in frame_readings
            ],
            "resolved": {str(k): list(v) for k, v in resolved.items()},
        }
        self._write_json("stage_ocr.json", data)
        self._manifest.setdefault("stages", {})["ocr"] = _ts()
        self._save_manifest()
        logger.info("[cache] Saved OCR: %d frame readings (job=%s)", len(frame_readings), self.job_id)

    def load_ocr(self) -> tuple[list[dict[int, int | None]], dict[int, tuple[int | None, float]]]:
        data = self._read_json("stage_ocr.json")
        frame_readings = [
            {int(k): v for k, v in r.items()} for r in data["frame_readings"]
        ]
        resolved = {
            int(k): (v[0], float(v[1])) for k, v in data["resolved"].items()
        }
        return frame_readings, resolved

    # ── Calibration ───────────────────────────────────────────────────────────

    def save_calibration(self, calib: CalibrationResult) -> None:
        arrays: dict[str, Any] = {
            "pixels_per_cm": np.array(
                [calib.pixels_per_cm if calib.pixels_per_cm is not None else -1.0],
                dtype=np.float64,
            ),
            "reprojection_error_cm": np.array([calib.reprojection_error_cm], dtype=np.float64),
            "is_valid": np.array([int(calib.is_valid)], dtype=np.int8),
            "cone_positions_px": np.array(calib.cone_positions_px or [], dtype=np.float32).reshape(-1, 2) if calib.cone_positions_px else np.empty((0, 2), dtype=np.float32),
            "cone_positions_world": np.array(calib.cone_positions_world or [], dtype=np.float32).reshape(-1, 2) if calib.cone_positions_world else np.empty((0, 2), dtype=np.float32),
        }
        if calib.homography_matrix is not None:
            arrays["homography_matrix"] = calib.homography_matrix.astype(np.float64)
        meta = {"method": calib.method}
        self._write_npz("stage_calibrate.npz", arrays)
        self._write_json("stage_calibrate_meta.json", meta)
        self._manifest.setdefault("stages", {})["calibrate"] = _ts()
        self._save_manifest()
        logger.info("[cache] Saved calibration (method=%s, job=%s)", calib.method, self.job_id)

    def load_calibration(self) -> CalibrationResult:
        data = self._read_npz("stage_calibrate.npz")
        meta = self._read_json("stage_calibrate_meta.json")
        ppc_raw = float(data["pixels_per_cm"][0])
        H = data["homography_matrix"].astype(np.float64) if "homography_matrix" in data else None
        cones_px = [tuple(row) for row in data["cone_positions_px"].tolist()]
        cones_world = [tuple(row) for row in data["cone_positions_world"].tolist()]
        return CalibrationResult(
            method=meta["method"],
            homography_matrix=H,
            pixels_per_cm=ppc_raw if ppc_raw >= 0 else None,
            cone_positions_px=cones_px,
            cone_positions_world=cones_world,
            reprojection_error_cm=float(data["reprojection_error_cm"][0]),
            is_valid=bool(data["is_valid"][0]),
        )

    # ── Results ───────────────────────────────────────────────────────────────

    def save_results(self, results: list[TestResult]) -> None:
        data = [asdict(r) for r in results]
        self._write_json("stage_results.json", data)
        self._manifest.setdefault("stages", {})["results"] = _ts()
        self._save_manifest()
        logger.info("[cache] Saved %d results (job=%s)", len(results), self.job_id)

    def load_results(self) -> list[TestResult]:
        data = self._read_json("stage_results.json")
        results = []
        for d in data:
            results.append(TestResult(
                student_bib=d["student_bib"],
                track_id=d["track_id"],
                test_type=d["test_type"],
                metric_value=d["metric_value"],
                metric_unit=d["metric_unit"],
                attempt_number=d["attempt_number"],
                confidence_score=d["confidence_score"],
                flags=d.get("flags", []),
                raw_data=d.get("raw_data", {}),
            ))
        return results

    # ── Low-level I/O ─────────────────────────────────────────────────────────

    def _write_json(self, filename: str, data: Any) -> None:
        tmp = self.root / f".tmp_{filename}"
        final = self.root / filename
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        tmp.rename(final)

    def _read_json(self, filename: str) -> Any:
        with open(self.root / filename, encoding="utf-8") as f:
            return json.load(f)

    def _write_npz(self, filename: str, arrays: dict[str, Any]) -> None:
        tmp = self.root / f".tmp_{filename}"
        final = self.root / filename
        np.savez_compressed(str(tmp), **arrays)
        # savez adds .npz if not present
        tmp_actual = tmp if tmp.exists() else Path(str(tmp) + ".npz")
        tmp_actual.rename(final)

    def _read_npz(self, filename: str) -> Any:
        return np.load(str(self.root / filename), allow_pickle=False)

    def _load_manifest(self) -> dict:
        if self._manifest_path.exists():
            with open(self._manifest_path) as f:
                return json.load(f)
        return {"stages": {}}

    def _save_manifest(self) -> None:
        with open(self._manifest_path, "w") as f:
            json.dump(self._manifest, f, indent=2)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()

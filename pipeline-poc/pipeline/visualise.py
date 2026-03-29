"""
Module 8 — Rich Pipeline Visualisation
Renders per-test overlays, HUD scoreboard, calibration grid, and flag badges
on top of raw frames or into an annotated video file.

Usage — as a context manager writing an annotated video:

    from pipeline.visualise import PipelineVisualiser

    with PipelineVisualiser(
        output_path="data/annotated/job123_vis.mp4",
        test_type="explosiveness",
        fps=15,
    ) as vis:
        for frame, tracks, poses, calib, results in frame_iter:
            vis.write_frame(frame, tracks, poses, calib, results)

Usage — annotate a single frame (e.g. in a notebook):

    canvas = PipelineVisualiser.annotate_frame(
        frame, tracks, poses, calib, results, test_type="explosiveness"
    )
    plt.imshow(canvas[:, :, ::-1])  # BGR → RGB

Overlay layers (all individually togglable via VisOptions):
    - Bounding boxes + track ID + bib number
    - Pose skeleton (COCO keypoints)
    - Calibration grid (projected cone positions, world axes, homography grid)
    - Top-down world-coords view (cone + person positions in cm, inset)
    - Per-test overlays:
        explosiveness  — baseline floor line, jump apex marker, height annotation
        speed          — start/finish crossing lines, split timer
        fitness        — top-down world-X trajectory trace per student
        agility        — world-plane path trace, cone proximity circles
        balance        — lean angle indicator, elapsed balance timer, foot lift marker
    - HUD scoreboard (top-right: current metric per student/bib)
    - Frame counter + timestamp (top-left)
    - Flag badges (bib_unresolved, low_pose_confidence, invalid_calibration)
"""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import cv2
import numpy as np

from pipeline.calibrate import Calibrator
from pipeline.models import CalibrationResult, Pose, TestResult, Track

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Colour palette (BGR)
# ──────────────────────────────────────────────────────────────────────────────
COL = {
    "confirmed_box":   (0, 220, 0),       # green — confirmed track
    "tentative_box":   (0, 165, 255),     # orange — unconfirmed track
    "skeleton":        (255, 80, 80),     # blue-ish
    "keypoint":        (0, 0, 220),       # red dots
    "floor_line":      (200, 200, 0),     # cyan — baseline for jump
    "apex_marker":     (0, 255, 255),     # yellow — jump apex
    "sprint_line":     (255, 0, 200),     # magenta — timing lines
    "path_trace":      (255, 200, 0),     # sky blue — motion trail
    "cone":            (0, 200, 255),     # yellow-orange — cone circles
    "world_axis_x":    (0, 0, 255),       # red — world X axis
    "world_axis_y":    (0, 255, 0),       # green — world Y axis
    "hud_bg":          (20, 20, 20),      # dark HUD background
    "hud_text":        (240, 240, 240),   # light HUD text
    "flag_bib":        (0, 0, 200),       # red — bib unresolved badge
    "flag_pose":       (0, 140, 255),     # orange — low pose confidence badge
    "flag_calib":      (0, 0, 200),       # red — invalid calibration badge
    "lean_ok":         (0, 200, 0),       # green — lean within threshold
    "lean_warn":       (0, 50, 200),      # red — lean exceeded
    "balance_timer":   (0, 255, 255),     # yellow — balance duration
}

KEYPOINT_PAIRS = [
    (5, 6),           # shoulders
    (5, 7), (7, 9),   # left arm
    (6, 8), (8, 10),  # right arm
    (11, 12),          # hips
    (5, 11), (6, 12), # torso sides
    (11, 13), (13, 15),  # left leg
    (12, 14), (14, 16),  # right leg
]


# ──────────────────────────────────────────────────────────────────────────────
# H.264 video writer (universal encoding via ffmpeg)
# ──────────────────────────────────────────────────────────────────────────────

def _create_h264_writer(output_path: Path, width: int, height: int, fps: int):
    """
    Create a video writer that encodes to H.264 (Baseline, yuv420p) via ffmpeg.
    Returns an object with write(frame) and release() methods.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-pix_fmt", "bgr24",
        "-s", f"{width}x{height}", "-r", str(fps),
        "-i", "pipe:0",
        "-c:v", "libx264", "-profile:v", "baseline", "-level", "3.1",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(output_path),
    ]
    proc = subprocess.Popen(
        cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
    )
    if proc.stdin is None:
        raise RuntimeError("ffmpeg stdin is None")

    class H264Writer:
        def write(self, frame: np.ndarray) -> bool:
            if proc.poll() is not None:
                return False
            proc.stdin.write(np.ascontiguousarray(frame).tobytes())
            return True

        def release(self) -> None:
            try:
                proc.stdin.close()
            except (BrokenPipeError, OSError):
                pass
            proc.wait()
            if proc.returncode != 0 and proc.stderr:
                try:
                    stderr = proc.stderr.read().decode(errors="replace")[:500]
                    logger.warning("ffmpeg stderr: %s", stderr)
                except Exception:
                    pass

    return H264Writer()


# ──────────────────────────────────────────────────────────────────────────────
# Visualisation options
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class VisOptions:
    """Toggle individual overlay layers."""
    show_boxes: bool = True
    show_skeleton: bool = True
    show_calibration_grid: bool = True
    show_test_overlay: bool = True
    show_hud: bool = True
    show_frame_counter: bool = True
    show_flags: bool = True
    show_top_down_view: bool = False
    skeleton_conf_threshold: float = 0.3
    # Path trace: how many frames of history to show per student
    trace_history_frames: int = 60
    # Top-down view: size of the inset panel (width, height)
    top_down_view_size: tuple[int, int] = (220, 220)


# ──────────────────────────────────────────────────────────────────────────────
# Main visualiser
# ──────────────────────────────────────────────────────────────────────────────

class PipelineVisualiser:
    """
    Stateful frame-by-frame annotator.  Maintains per-track histories
    (path traces, jump baselines, balance timers) across frames.
    """

    def __init__(
        self,
        output_path: str | Path,
        test_type: str,
        fps: int = 15,
        options: VisOptions | None = None,
    ):
        self.output_path = Path(output_path)
        self.test_type = test_type
        self.fps = fps
        self.opts = options or VisOptions()

        self._writer: object | None = None  # H.264 writer (ffmpeg) or None
        self._frame_idx: int = 0

        # Per-track state
        self._path_history: dict[int, list[tuple[int, int]]] = {}   # track_id → pixel positions
        self._ankle_baselines: dict[int, float] = {}                  # track_id → baseline Y
        self._balance_start: dict[int, int | None] = {}               # track_id → start frame
        self._balance_elapsed: dict[int, float] = {}                  # track_id → seconds

    # ── Context manager ──────────────────────────────────────────────────────

    def __enter__(self) -> "PipelineVisualiser":
        self.open()
        return self

    def __exit__(self, *_):
        self.close()

    def open(self):
        """Open the output video writer (auto-detect frame size on first frame)."""
        logger.info("PipelineVisualiser ready. Output: %s", self.output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

    def close(self):
        if self._writer:
            self._writer.release()
            logger.info("PipelineVisualiser closed: %s", self.output_path)

    # ── Primary interface ─────────────────────────────────────────────────────

    def write_frame(
        self,
        frame: np.ndarray,
        tracks: list[Track],
        poses: list[Pose],
        calibration: CalibrationResult,
        results: list[TestResult],
        timestamp_s: float | None = None,
    ) -> np.ndarray:
        """
        Annotate one frame and write it to the output video.

        Returns the annotated canvas (useful for notebook display).
        """
        # Lazy-open writer once we know frame dimensions (H.264 via ffmpeg for universal compatibility)
        if self._writer is None:
            h, w = frame.shape[:2]
            self._writer = _create_h264_writer(self.output_path, w, h, self.fps)

        canvas = self.annotate_frame(
            frame=frame,
            tracks=tracks,
            poses=poses,
            calibration=calibration,
            results=results,
            test_type=self.test_type,
            frame_idx=self._frame_idx,
            timestamp_s=timestamp_s,
            opts=self.opts,
            _state=self._get_state(),
        )
        self._update_state(tracks, poses)
        self._writer.write(canvas)
        self._frame_idx += 1
        return canvas

    # ── Static annotator (usable without writer, e.g. notebooks) ─────────────

    @staticmethod
    def annotate_frame(
        frame: np.ndarray,
        tracks: list[Track],
        poses: list[Pose],
        calibration: CalibrationResult,
        results: list[TestResult],
        test_type: str,
        frame_idx: int = 0,
        timestamp_s: float | None = None,
        opts: VisOptions | None = None,
        _state: dict | None = None,
    ) -> np.ndarray:
        """
        Pure function: annotate a single frame without side effects.
        _state is internal; pass None for one-shot notebook use.
        """
        opts = opts or VisOptions()
        canvas = frame.copy()
        pose_map = {p.track_id: p for p in poses}

        # Layer 1: calibration grid
        if opts.show_calibration_grid and calibration.is_valid:
            canvas = _draw_calibration_overlay(canvas, calibration)

        # Layer 2: per-test overlay (drawn under boxes so labels stay readable)
        if opts.show_test_overlay:
            canvas = _draw_test_overlay(
                canvas, tracks, poses, calibration, results, test_type, _state or {}
            )

        # Layer 3: bounding boxes + track labels
        if opts.show_boxes:
            for track in tracks:
                canvas = _draw_track_box(canvas, track, pose_map, opts)

        # Layer 4: pose skeletons
        if opts.show_skeleton:
            for pose in poses:
                canvas = _draw_skeleton(canvas, pose, opts.skeleton_conf_threshold)

        # Layer 5: flag badges
        if opts.show_flags:
            canvas = _draw_flags(canvas, tracks, calibration)

        # Layer 6: HUD scoreboard
        if opts.show_hud and results:
            canvas = _draw_hud(canvas, results, test_type)

        # Layer 7: frame counter + timestamp
        if opts.show_frame_counter:
            canvas = _draw_frame_counter(canvas, frame_idx, timestamp_s)

        # Layer 8: top-down world-coords view (inset)
        if opts.show_top_down_view and calibration.is_valid:
            top_down = render_top_down_view(
                calibration, tracks, poses, size=opts.top_down_view_size
            )
            canvas = _composite_top_down_inset(canvas, top_down)

        return canvas

    # ── Internal state helpers ────────────────────────────────────────────────

    def _get_state(self) -> dict:
        return {
            "path_history":     self._path_history,
            "ankle_baselines":  self._ankle_baselines,
            "balance_start":    self._balance_start,
            "balance_elapsed":  self._balance_elapsed,
            "frame_idx":        self._frame_idx,
            "fps":              self.fps,
            "trace_history":    self.opts.trace_history_frames,
        }

    def _update_state(self, tracks: list[Track], poses: list[Pose]):
        pose_map = {p.track_id: p for p in poses}
        for track in tracks:
            # Update path history (hip midpoint)
            pose = pose_map.get(track.track_id)
            if pose is not None:
                kps = pose.keypoints
                if kps[11, 2] > 0.3 and kps[12, 2] > 0.3:
                    hx = int((kps[11, 0] + kps[12, 0]) / 2)
                    hy = int((kps[11, 1] + kps[12, 1]) / 2)
                    hist = self._path_history.setdefault(track.track_id, [])
                    hist.append((hx, hy))
                    # Trim history
                    if len(hist) > self.opts.trace_history_frames:
                        self._path_history[track.track_id] = hist[-self.opts.trace_history_frames:]

            # Ankle baseline (first 30 frames)
            if self._frame_idx < 30 and pose is not None:
                kps = pose.keypoints
                ankle_ys = []
                if kps[15, 2] > 0.3:
                    ankle_ys.append(kps[15, 1])
                if kps[16, 2] > 0.3:
                    ankle_ys.append(kps[16, 1])
                if ankle_ys:
                    prev = self._ankle_baselines.get(track.track_id, float("nan"))
                    if np.isnan(prev):
                        self._ankle_baselines[track.track_id] = float(np.mean(ankle_ys))
                    else:
                        # Rolling mean
                        self._ankle_baselines[track.track_id] = (prev + float(np.mean(ankle_ys))) / 2


# ──────────────────────────────────────────────────────────────────────────────
# Top-down world-coords view
# ──────────────────────────────────────────────────────────────────────────────

def render_top_down_view(
    calibration: CalibrationResult,
    tracks: list[Track],
    poses: list[Pose],
    size: tuple[int, int] = (220, 220),
    expected_cone_positions_world: list[tuple[float, float]] | None = None,
) -> np.ndarray:
    """
    Render a top-down view in world coordinates (cm).
    Shows cone positions and person positions (hip midpoint) using calibration.

    If expected_cone_positions_world is provided (e.g. full grid from layout), those
    are drawn as open circles and calibration.cone_positions_world as filled (matched cones).

    Returns a BGR canvas of the given size. Usable standalone (e.g. in notebooks)
    or as an inset overlay.
    """
    calibrator = Calibrator()
    w_canvas, h_canvas = size

    # Gather world positions for cones (matched / used for calibration)
    cone_world: list[tuple[float, float]] = []
    if calibration.cone_positions_world:
        cone_world = list(calibration.cone_positions_world)
    elif calibration.cone_positions_px:
        try:
            for cx, cy in calibration.cone_positions_px:
                wx, wy = calibrator.pixel_to_world((float(cx), float(cy)), calibration)
                cone_world.append((wx, wy))
        except (ValueError, Exception):
            pass

    # Gather world positions for persons (hip midpoint)
    pose_map = {p.track_id: p for p in poses}
    person_world: list[tuple[float, float, int]] = []  # (x, y, track_id)
    for track in tracks:
        pose = pose_map.get(track.track_id)
        if pose is None:
            continue
        kps = pose.keypoints
        if kps[11, 2] > 0.3 and kps[12, 2] > 0.3:
            hx = (kps[11, 0] + kps[12, 0]) / 2
            hy = (kps[11, 1] + kps[12, 1]) / 2
            try:
                wx, wy = calibrator.pixel_to_world((float(hx), float(hy)), calibration)
                person_world.append((wx, wy, track.track_id))
            except (ValueError, Exception):
                pass

    # Bounding box in world coords (include expected grid so full layout is visible)
    all_pts = cone_world + [(x, y) for x, y, _ in person_world]
    if expected_cone_positions_world:
        all_pts = all_pts + list(expected_cone_positions_world)
    if not all_pts:
        # No data: create a default view (e.g. 0–500 cm)
        x_min, x_max = 0.0, 500.0
        y_min, y_max = 0.0, 500.0
    else:
        xs = [p[0] for p in all_pts]
        ys = [p[1] for p in all_pts]
        pad = max(50.0, (max(xs) - min(xs) + max(ys) - min(ys)) * 0.15)
        x_min, x_max = min(xs) - pad, max(xs) + pad
        y_min, y_max = min(ys) - pad, max(ys) + pad
        if x_max - x_min < 100:
            x_max = x_min + 100
        if y_max - y_min < 100:
            y_max = y_min + 100

    def world_to_canvas(x: float, y: float) -> tuple[int, int]:
        # World Y increases "up" in typical court layout; canvas Y increases down
        # Map world (x,y) to canvas: X→right, Y→down (flip world Y for top-down)
        u = (x - x_min) / (x_max - x_min) if x_max > x_min else 0.5
        v = (y_max - y) / (y_max - y_min) if y_max > y_min else 0.5  # flip Y
        margin = 25
        cw = w_canvas - 2 * margin
        ch = h_canvas - 2 * margin
        cx = int(margin + u * cw)
        cy = int(margin + v * ch)
        return (np.clip(cx, 0, w_canvas - 1), np.clip(cy, 0, h_canvas - 1))

    # Create canvas (dark background)
    canvas = np.full((h_canvas, w_canvas, 3), 35, dtype=np.uint8)

    # Grid lines
    for val in np.linspace(x_min, x_max, 6):
        if x_min <= val <= x_max:
            cx, cy = world_to_canvas(val, y_min)
            cx2, cy2 = world_to_canvas(val, y_max)
            cv2.line(canvas, (cx, cy), (cx2, cy2), (50, 50, 50), 1)
    for val in np.linspace(y_min, y_max, 6):
        if y_min <= val <= y_max:
            cx, cy = world_to_canvas(x_min, val)
            cx2, cy2 = world_to_canvas(x_max, val)
            cv2.line(canvas, (cx, cy), (cx2, cy2), (50, 50, 50), 1)

    # Axis labels
    cv2.putText(canvas, "X (cm)", (w_canvas - 45, h_canvas - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, COL["world_axis_x"], 1)
    cv2.putText(canvas, "Y (cm)", (5, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.35, COL["world_axis_y"], 1)

    # Draw expected grid (open circles) when provided
    if expected_cone_positions_world:
        for x, y in expected_cone_positions_world:
            cx, cy = world_to_canvas(x, y)
            cv2.circle(canvas, (cx, cy), 6, (170, 170, 170), 1)

    # Draw cones (matched / used for calibration — filled)
    for x, y in cone_world:
        cx, cy = world_to_canvas(x, y)
        cv2.circle(canvas, (cx, cy), 6, COL["cone"], -1)
        cv2.circle(canvas, (cx, cy), 8, COL["cone"], 1)

    # Draw persons
    for x, y, tid in person_world:
        cx, cy = world_to_canvas(x, y)
        cv2.circle(canvas, (cx, cy), 8, COL["confirmed_box"], -1)
        cv2.circle(canvas, (cx, cy), 10, COL["confirmed_box"], 1)
        cv2.putText(canvas, str(tid), (cx + 10, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.4, COL["hud_text"], 1)

    # Title
    cv2.putText(canvas, "Top-down (world)", (8, h_canvas - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 180, 180), 1)
    if expected_cone_positions_world:
        cv2.putText(
            canvas,
            f"expected={len(expected_cone_positions_world)} matched={len(cone_world)}",
            (8, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (190, 190, 190),
            1,
        )

    return canvas


def _composite_top_down_inset(main_canvas: np.ndarray, top_down: np.ndarray) -> np.ndarray:
    """Composite the top-down view as an inset in the bottom-left of the main canvas."""
    h, w = main_canvas.shape[:2]
    th, tw = top_down.shape[:2]
    margin = 12
    # Scale down top-down if it doesn't fit
    if th + 2 * margin > h or tw + 2 * margin > w:
        scale = min((h - 2 * margin) / th, (w - 2 * margin) / tw)
        if scale <= 0:
            return main_canvas
        new_tw = max(1, int(tw * scale))
        new_th = max(1, int(th * scale))
        top_down = cv2.resize(top_down, (new_tw, new_th))
        th, tw = new_th, new_tw
    x0 = margin
    y0 = max(margin, h - th - margin)
    # Semi-transparent border
    cv2.rectangle(main_canvas, (x0 - 2, y0 - 2), (x0 + tw + 2, y0 + th + 2), (80, 80, 80), 2)
    # Paste
    roi = main_canvas[y0 : y0 + th, x0 : x0 + tw]
    np.copyto(roi, top_down)
    return main_canvas


# ──────────────────────────────────────────────────────────────────────────────
# Layer rendering helpers (module-level private functions)
# ──────────────────────────────────────────────────────────────────────────────

def _draw_track_box(
    canvas: np.ndarray, track: Track, pose_map: dict, opts: VisOptions
) -> np.ndarray:
    x1, y1, x2, y2 = map(int, track.bbox)
    colour = COL["confirmed_box"] if track.is_confirmed else COL["tentative_box"]
    cv2.rectangle(canvas, (x1, y1), (x2, y2), colour, 2)

    # Label: ID + bib
    label = f"ID:{track.track_id}"
    if track.bib_number is not None:
        label += f"  #{track.bib_number}"
        if track.bib_confidence > 0:
            label += f" ({track.bib_confidence:.0%})"

    # Background pill for label
    (tw, th), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
    cv2.rectangle(canvas, (x1, y1 - th - 8), (x1 + tw + 6, y1), colour, -1)
    cv2.putText(canvas, label, (x1 + 3, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1)

    return canvas


def _draw_skeleton(canvas: np.ndarray, pose: Pose, conf_thresh: float) -> np.ndarray:
    kps = pose.keypoints
    for i in range(17):
        if kps[i, 2] > conf_thresh:
            cv2.circle(canvas, (int(kps[i, 0]), int(kps[i, 1])), 4, COL["keypoint"], -1)
    for a, b in KEYPOINT_PAIRS:
        if kps[a, 2] > conf_thresh and kps[b, 2] > conf_thresh:
            cv2.line(
                canvas,
                (int(kps[a, 0]), int(kps[a, 1])),
                (int(kps[b, 0]), int(kps[b, 1])),
                COL["skeleton"], 2,
            )
    return canvas


def _draw_calibration_overlay(canvas: np.ndarray, calib: CalibrationResult) -> np.ndarray:
    h, w = canvas.shape[:2]

    # Draw detected cone centres
    for cx, cy in calib.cone_positions_px:
        cv2.circle(canvas, (int(cx), int(cy)), 12, COL["cone"], 2)
        cv2.circle(canvas, (int(cx), int(cy)), 3, COL["cone"], -1)

    # Draw world axis arrows if homography available
    if calib.method == "homography" and calib.homography_matrix is not None:
        H_inv = np.linalg.inv(calib.homography_matrix)
        origin_world = np.array([[[0.0, 0.0]]], dtype=np.float32)
        x_tip_world  = np.array([[[100.0, 0.0]]], dtype=np.float32)
        y_tip_world  = np.array([[[0.0, 100.0]]], dtype=np.float32)

        try:
            o  = cv2.perspectiveTransform(origin_world, H_inv)[0][0]
            xt = cv2.perspectiveTransform(x_tip_world,  H_inv)[0][0]
            yt = cv2.perspectiveTransform(y_tip_world,  H_inv)[0][0]

            def _clip(pt):
                return (int(np.clip(pt[0], 0, w - 1)), int(np.clip(pt[1], 0, h - 1)))

            cv2.arrowedLine(canvas, _clip(o), _clip(xt), COL["world_axis_x"], 2, tipLength=0.15)
            cv2.arrowedLine(canvas, _clip(o), _clip(yt), COL["world_axis_y"], 2, tipLength=0.15)
            cv2.putText(canvas, "X(cm)", _clip(xt), cv2.FONT_HERSHEY_SIMPLEX, 0.5, COL["world_axis_x"], 1)
            cv2.putText(canvas, "Y(cm)", _clip(yt), cv2.FONT_HERSHEY_SIMPLEX, 0.5, COL["world_axis_y"], 1)
        except Exception:
            pass  # degenerate homography — skip axis drawing

    # Reprojection error badge (bottom-left)
    err_text = f"Reproj: {calib.reprojection_error_cm:.1f}cm"
    err_col = COL["lean_ok"] if calib.reprojection_error_cm < 1.5 else COL["lean_warn"]
    cv2.putText(canvas, err_text, (10, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.55, err_col, 2)

    return canvas


def _draw_test_overlay(
    canvas: np.ndarray,
    tracks: list[Track],
    poses: list[Pose],
    calib: CalibrationResult,
    results: list[TestResult],
    test_type: str,
    state: dict,
) -> np.ndarray:
    if test_type == "explosiveness":
        canvas = _overlay_explosiveness(canvas, tracks, poses, state)
    elif test_type == "speed":
        canvas = _overlay_sprint(canvas, state)
    elif test_type == "fitness":
        canvas = _overlay_shuttle(canvas, tracks, poses, calib, state)
    elif test_type == "agility":
        canvas = _overlay_agility(canvas, tracks, calib, state)
    elif test_type == "balance":
        canvas = _overlay_balance(canvas, tracks, poses, state)
    return canvas


def _overlay_explosiveness(
    canvas: np.ndarray,
    tracks: list[Track],
    poses: list[Pose],
    state: dict,
) -> np.ndarray:
    """Draw baseline floor line + apex marker + height annotation per student."""
    w = canvas.shape[1]
    pose_map = {p.track_id: p for p in poses}
    baselines = state.get("ankle_baselines", {})

    for track in tracks:
        baseline_y = baselines.get(track.track_id)
        if baseline_y is None:
            continue

        # Floor baseline (full-width, semi-transparent strip)
        overlay = canvas.copy()
        by = int(baseline_y)
        cv2.line(overlay, (0, by), (w, by), COL["floor_line"], 2)
        cv2.addWeighted(overlay, 0.6, canvas, 0.4, 0, canvas)

        # Apex marker: lowest ankle Y for this track
        pose = pose_map.get(track.track_id)
        if pose is not None:
            kps = pose.keypoints
            ankle_ys = [kps[i, 1] for i in (15, 16) if kps[i, 2] > 0.3]
            if ankle_ys:
                apex_y = min(ankle_ys)
                height_px = baseline_y - apex_y
                if height_px > 10:  # only draw if actually jumping
                    ax = int((track.bbox[0] + track.bbox[2]) / 2)
                    ay = int(apex_y)
                    # Vertical dashed line from floor to apex
                    for y in range(by, ay, -8):
                        cv2.line(canvas, (ax, y), (ax, max(ay, y - 5)), COL["apex_marker"], 2)
                    cv2.circle(canvas, (ax, ay), 8, COL["apex_marker"], -1)
                    # Height label
                    ppc = state.get("pixels_per_cm")
                    if ppc and ppc > 0:
                        label = f"{height_px / ppc:.1f} cm"
                    else:
                        label = f"{int(height_px)}px"
                    cv2.putText(canvas, label, (ax + 10, ay + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, COL["apex_marker"], 2)
    return canvas


def _overlay_sprint(canvas: np.ndarray, state: dict) -> np.ndarray:
    """Draw start and finish crossing lines."""
    h = canvas.shape[0]
    start_x = state.get("start_line_x_px", 400)
    finish_x = state.get("finish_line_x_px", 1500)
    # Start line (green)
    cv2.line(canvas, (start_x, 0), (start_x, h), COL["lean_ok"], 2)
    cv2.putText(canvas, "START", (start_x + 5, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, COL["lean_ok"], 2)
    # Finish line (magenta)
    cv2.line(canvas, (finish_x, 0), (finish_x, h), COL["sprint_line"], 2)
    cv2.putText(canvas, "FINISH", (finish_x + 5, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, COL["sprint_line"], 2)
    return canvas


def _overlay_shuttle(
    canvas: np.ndarray,
    tracks: list[Track],
    poses: list[Pose],
    calib: CalibrationResult,
    state: dict,
) -> np.ndarray:
    """Draw motion trail (path trace) for shuttle run."""
    path_history = state.get("path_history", {})
    for track in tracks:
        hist = path_history.get(track.track_id, [])
        if len(hist) < 2:
            continue
        pts = np.array(hist, dtype=np.int32)
        # Fading trail: older points more transparent
        for i in range(1, len(pts)):
            alpha = i / len(pts)
            colour = tuple(int(c * alpha) for c in COL["path_trace"])
            cv2.line(canvas, tuple(pts[i - 1]), tuple(pts[i]), colour, 2)
    return canvas


def _overlay_agility(
    canvas: np.ndarray,
    tracks: list[Track],
    calib: CalibrationResult,
    state: dict,
) -> np.ndarray:
    """Draw path trace + cone proximity circles (T-drill layout)."""
    canvas = _overlay_shuttle(canvas, tracks, [], calib, state)  # reuse trail logic

    # Draw T-drill cone positions from calibration
    if calib.is_valid and calib.method == "homography":
        for cx, cy in calib.cone_positions_px:
            cv2.circle(canvas, (int(cx), int(cy)), 30, COL["cone"], 1)
    return canvas


def _overlay_balance(
    canvas: np.ndarray,
    tracks: list[Track],
    poses: list[Pose],
    state: dict,
) -> np.ndarray:
    """Draw lean angle indicator + elapsed balance timer per student."""
    pose_map = {p.track_id: p for p in poses}
    fps = state.get("fps", 15)
    balance_start = state.get("balance_start", {})
    balance_elapsed = state.get("balance_elapsed", {})
    frame_idx = state.get("frame_idx", 0)

    for track in tracks:
        pose = pose_map.get(track.track_id)
        if pose is None:
            continue
        kps = pose.keypoints

        # Lean angle: nose relative to hip midpoint
        nose_conf = kps[0, 2]
        hip_l_conf = kps[11, 2]
        hip_r_conf = kps[12, 2]

        if nose_conf > 0.3 and hip_l_conf > 0.3 and hip_r_conf > 0.3:
            nx, ny = kps[0, 0], kps[0, 1]
            hx = (kps[11, 0] + kps[12, 0]) / 2
            hy = (kps[11, 1] + kps[12, 1]) / 2
            dx = nx - hx
            dy = hy - ny  # positive upward in image coords

            lean_angle = abs(np.degrees(np.arctan2(abs(dx), max(dy, 1))))
            lean_threshold = 15  # degrees
            lean_col = COL["lean_ok"] if lean_angle < lean_threshold else COL["lean_warn"]

            # Draw lean line from hip to nose
            cv2.line(canvas, (int(hx), int(hy)), (int(nx), int(ny)), lean_col, 3)
            cv2.putText(
                canvas,
                f"{lean_angle:.0f}\u00b0",
                (int(nx) + 8, int(ny)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, lean_col, 2,
            )

        # Balance timer
        elapsed = balance_elapsed.get(track.track_id, 0.0)
        start_frame = balance_start.get(track.track_id)
        if start_frame is not None:
            elapsed = (frame_idx - start_frame) / fps

        if elapsed > 0.1:
            x1, _, x2, y2 = map(int, track.bbox)
            mid_x = (x1 + x2) // 2
            timer_text = f"BAL: {elapsed:.1f}s"
            cv2.putText(
                canvas, timer_text, (mid_x - 30, y2 + 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, COL["balance_timer"], 2,
            )
    return canvas


def _draw_flags(
    canvas: np.ndarray, tracks: list[Track], calib: CalibrationResult
) -> np.ndarray:
    """Draw small warning badges for quality issues."""
    badge_x = canvas.shape[1] - 200
    badge_y = 10

    if not calib.is_valid:
        _badge(canvas, "⚠ BAD CALIB", badge_x, badge_y, COL["flag_calib"])
        badge_y += 24

    for track in tracks:
        if track.bib_number is None:
            _badge(canvas, f"BIB? ID:{track.track_id}", badge_x, badge_y, COL["flag_bib"])
            badge_y += 24

    return canvas


def _draw_hud(
    canvas: np.ndarray, results: list[TestResult], test_type: str
) -> np.ndarray:
    """Top-right scoreboard showing latest metric per student bib."""
    h, w = canvas.shape[:2]
    hud_w = 220
    line_h = 24
    margin = 8

    # Deduplicate: keep best attempt per bib
    best: dict[int, TestResult] = {}
    for r in results:
        if r.student_bib not in best or r.metric_value > best[r.student_bib].metric_value:
            best[r.student_bib] = r

    rows = sorted(best.values(), key=lambda r: r.student_bib)
    hud_h = len(rows) * line_h + margin * 2 + 20

    # Semi-transparent background
    overlay = canvas.copy()
    x0 = w - hud_w - margin
    cv2.rectangle(overlay, (x0, margin), (w - margin, margin + hud_h), COL["hud_bg"], -1)
    cv2.addWeighted(overlay, 0.75, canvas, 0.25, 0, canvas)

    # Header
    cv2.putText(canvas, test_type.upper(), (x0 + 6, margin + 16),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, COL["hud_text"], 1)

    for i, r in enumerate(rows):
        y = margin + 20 + (i + 1) * line_h
        bib_str = f"#{r.student_bib:02d}" if r.student_bib > 0 else "??"
        val_str = f"{r.metric_value:.2f} {r.metric_unit}"
        flag_str = "⚠" if r.flags else ""
        row_text = f"{bib_str}  {val_str}  {flag_str}"
        col = COL["flag_bib"] if r.flags else COL["hud_text"]
        cv2.putText(canvas, row_text, (x0 + 6, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, col, 1)

    return canvas


def _draw_frame_counter(
    canvas: np.ndarray, frame_idx: int, timestamp_s: float | None
) -> np.ndarray:
    ts = f"  {timestamp_s:.2f}s" if timestamp_s is not None else ""
    text = f"Frame {frame_idx:05d}{ts}"
    cv2.putText(canvas, text, (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)
    return canvas


# ──────────────────────────────────────────────────────────────────────────────
# Utility
# ──────────────────────────────────────────────────────────────────────────────

def _badge(
    canvas: np.ndarray, text: str, x: int, y: int, colour: tuple
) -> None:
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
    cv2.rectangle(canvas, (x - 2, y), (x + tw + 4, y + th + 4), colour, -1)
    cv2.putText(canvas, text, (x + 2, y + th + 1), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

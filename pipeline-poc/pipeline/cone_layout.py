"""
Cone layout — generate world coordinates from spacing + first-cone specification.

Supports:
  - linear:  cones along one axis at even spacing
  - grid:    cones in rows × cols
  - clustered: cones in multiple clusters (e.g. around each person)
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


def generate_cone_world_coords(
    layout_config: dict[str, Any],
    num_cones: int,
) -> list[tuple[float, float]]:
    """
    Generate world coordinates (cm) for cones from a layout config.

    Order matches the (y, x) sort used by Calibrator (top→bottom, left→right).

    Args:
        layout_config: Dict with keys:
            - pattern: "linear" | "grid" | "clustered"
            - For linear: first_cone_cm, spacing_cm, direction ("x" | "y")
            - For grid: first_cone_cm, spacing_cm, rows, cols
            - For clustered: clusters list; each has origin_cm, spacing_cm, direction
        num_cones: Number of cones to generate (for linear/grid). For clustered,
                   inferred from cone_positions_px via generate_cone_world_coords_from_pixels.

    Returns:
        List of (x_cm, y_cm) tuples.

    Notes:
        Grid layout supports both symmetric spacing (``spacing_cm``) and
        asymmetric spacing (``spacing_cm_x`` / ``spacing_cm_y``).  The
        asymmetric keys take precedence; ``spacing_cm`` is the fallback.
    """
    pattern = layout_config.get("pattern", "linear")
    if pattern == "linear":
        coords = _generate_linear(layout_config, num_cones)
    elif pattern == "grid":
        coords = _generate_grid(layout_config, num_cones)
    else:
        raise ValueError(
            f"Pattern '{pattern}' requires cone_positions_px. "
            "Use generate_cone_world_coords_from_pixels() for clustered layout."
        )
    if layout_config.get("reverse_order"):
        coords = list(reversed(coords))
    return coords


def generate_cone_world_coords_from_pixels(
    layout_config: dict[str, Any],
    cone_positions_px: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """
    Generate world coords for clustered layout using detected pixel positions.

    Clusters cones by spatial proximity, then assigns world coords within each
    cluster from origin + even spacing.

    Args:
        layout_config: Dict with pattern="clustered" and clusters list.
        cone_positions_px: Detected cone centres (cx, cy) in pixels.

    Returns:
        List of (x_cm, y_cm) in same order as cone_positions_px after (y,x) sort.
    """
    pattern = layout_config.get("pattern", "linear")
    if pattern == "clustered":
        return _generate_clustered(layout_config, cone_positions_px)
    # For linear/grid, we don't need pixel positions
    cone_px_sorted = sorted(cone_positions_px, key=lambda p: (p[1], p[0]))
    return generate_cone_world_coords(layout_config, len(cone_px_sorted))


def _generate_linear(config: dict, num_cones: int) -> list[tuple[float, float]]:
    first = config.get("first_cone_cm", [0.0, 0.0])
    fx, fy = float(first[0]), float(first[1])
    spacing = float(config.get("spacing_cm", 100.0))
    direction = config.get("direction", "x")

    coords = []
    for i in range(num_cones):
        if direction == "x":
            coords.append((fx + i * spacing, fy))
        else:
            coords.append((fx, fy + i * spacing))
    return coords


def _generate_grid(config: dict, num_cones: int) -> list[tuple[float, float]]:
    first = config.get("first_cone_cm", [0.0, 0.0])
    fx, fy = float(first[0]), float(first[1])
    # Support separate x/y spacing; fall back to the single spacing_cm key.
    spacing_x = float(config.get("spacing_cm_x", config.get("spacing_cm", 100.0)))
    spacing_y = float(config.get("spacing_cm_y", config.get("spacing_cm", 100.0)))
    rows = int(config.get("rows", 2))
    cols = int(config.get("cols", 2))

    coords = []
    for r in range(rows):
        for c in range(cols):
            if len(coords) >= num_cones:
                break
            coords.append((fx + c * spacing_x, fy + r * spacing_y))
        if len(coords) >= num_cones:
            break
    return coords


def _generate_clustered(
    config: dict,
    cone_positions_px: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    clusters_cfg = config.get("clusters", [])
    if not clusters_cfg:
        raise ValueError("clustered pattern requires 'clusters' list in config")

    # Sort cones by (y, x) to match Calibrator ordering
    cone_px = sorted(cone_positions_px, key=lambda p: (p[1], p[0]))
    pts = np.array(cone_px, dtype=np.float64)

    # Simple distance-based clustering: group cones within cluster_radius_px
    cluster_radius_px = float(config.get("cluster_radius_px", 150.0))

    labels = _cluster_by_distance(pts, cluster_radius_px)
    n_clusters = int(labels.max()) + 1

    # Build cluster assignments: label -> list of indices
    cluster_indices: dict[int, list[int]] = {}
    for i, lab in enumerate(labels):
        cluster_indices.setdefault(int(lab), []).append(i)

    # Sort clusters by centroid (y, x) so order is top→bottom, left→right
    cluster_order = sorted(
        cluster_indices.keys(),
        key=lambda k: (
            pts[cluster_indices[k]].mean(axis=0)[1],
            pts[cluster_indices[k]].mean(axis=0)[0],
        ),
    )

    # Assign world coords to each cone in cone_px order (matches Calibrator sort)
    result: list[tuple[float, float]] = [(0.0, 0.0)] * len(cone_px)
    cluster_counters: dict[int, int] = {k: 0 for k in cluster_order}
    for idx in range(len(cone_px)):
        lab = int(labels[idx])
        ki = cluster_order.index(lab)
        cfg = clusters_cfg[ki] if ki < len(clusters_cfg) else clusters_cfg[-1]
        origin = cfg.get("origin_cm", [0.0, 0.0])
        ox, oy = float(origin[0]), float(origin[1])
        spacing = float(cfg.get("spacing_cm", 50.0))
        direction = cfg.get("direction", "x")
        j = cluster_counters[lab]
        cluster_counters[lab] += 1
        if direction == "x":
            result[idx] = (ox + j * spacing, oy)
        else:
            result[idx] = (ox, oy + j * spacing)
    return result


def _cluster_by_distance(pts: np.ndarray, radius: float) -> np.ndarray:
    """Assign cluster labels by grouping points within radius (simple linkage)."""
    n = len(pts)
    labels = np.full(n, -1, dtype=np.int32)
    next_label = 0
    for i in range(n):
        if labels[i] >= 0:
            continue
        labels[i] = next_label
        stack = [i]
        while stack:
            j = stack.pop()
            for k in range(n):
                if labels[k] >= 0:
                    continue
                if np.hypot(pts[j, 0] - pts[k, 0], pts[j, 1] - pts[k, 1]) <= radius:
                    labels[k] = next_label
                    stack.append(k)
        next_label += 1
    return labels

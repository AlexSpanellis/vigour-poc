"""
Unit tests for cone_layout — generate_cone_world_coords.
Run: pytest tests/unit/test_cone_layout.py
"""
import pytest

from pipeline.cone_layout import (
    generate_cone_world_coords,
    generate_cone_world_coords_from_pixels,
)


def test_linear():
    coords = generate_cone_world_coords(
        {"pattern": "linear", "first_cone_cm": [0, 0], "spacing_cm": 100, "direction": "x"},
        4,
    )
    assert coords == [(0, 0), (100, 0), (200, 0), (300, 0)]


def test_linear_reverse_order():
    coords = generate_cone_world_coords(
        {
            "pattern": "linear",
            "first_cone_cm": [0, 0],
            "spacing_cm": 100,
            "direction": "x",
            "reverse_order": True,
        },
        4,
    )
    assert coords == [(300, 0), (200, 0), (100, 0), (0, 0)]


def test_linear_direction_y():
    coords = generate_cone_world_coords(
        {"pattern": "linear", "first_cone_cm": [50, 50], "spacing_cm": 80, "direction": "y"},
        3,
    )
    assert coords == [(50, 50), (50, 130), (50, 210)]


def test_grid():
    coords = generate_cone_world_coords(
        {"pattern": "grid", "first_cone_cm": [0, 0], "spacing_cm": 50, "rows": 2, "cols": 3},
        6,
    )
    assert len(coords) == 6
    assert coords[0] == (0, 0)
    assert coords[2] == (100, 0)
    assert coords[3] == (0, 50)


def test_clustered():
    cone_px = [(5, 5), (15, 10), (105, 50), (115, 55)]
    coords = generate_cone_world_coords_from_pixels(
        {
            "pattern": "clustered",
            "cluster_radius_px": 30,
            "clusters": [
                {"origin_cm": [0, 0], "spacing_cm": 25, "direction": "x"},
                {"origin_cm": [200, 0], "spacing_cm": 25, "direction": "x"},
            ],
        },
        cone_px,
    )
    assert len(coords) == 4
    assert coords[0] == (0, 0)
    assert coords[1] == (25, 0)
    assert coords[2] == (200, 0)
    assert coords[3] == (225, 0)


def test_grid_asymmetric_spacing():
    """Fix 2: spacing_cm_x and spacing_cm_y are used independently (fitness.json layout)."""
    coords = generate_cone_world_coords(
        {
            "pattern": "grid",
            "first_cone_cm": [0, 0],
            "spacing_cm_x": 70,
            "spacing_cm_y": 300,
            "rows": 2,
            "cols": 3,
        },
        6,
    )
    assert len(coords) == 6
    # Row 0: x steps of 70 cm
    assert coords[0] == (0, 0)
    assert coords[1] == (70, 0)
    assert coords[2] == (140, 0)
    # Row 1: y step of 300 cm, x steps of 70 cm
    assert coords[3] == (0, 300)
    assert coords[4] == (70, 300)
    assert coords[5] == (140, 300)


def test_grid_symmetric_spacing_fallback():
    """spacing_cm fallback still works when spacing_cm_x/y absent."""
    coords = generate_cone_world_coords(
        {"pattern": "grid", "first_cone_cm": [0, 0], "spacing_cm": 50, "rows": 2, "cols": 3},
        6,
    )
    assert coords[3] == (0, 50)   # row 1, same step in both axes
    assert coords[4] == (50, 50)


def test_clustered_fallback_to_linear():
    cone_px = [(0, 0), (100, 0), (200, 0)]
    coords = generate_cone_world_coords_from_pixels(
        {"pattern": "linear", "first_cone_cm": [0, 0], "spacing_cm": 150, "direction": "x"},
        cone_px,
    )
    assert len(coords) == 3
    assert coords == [(0, 0), (150, 0), (300, 0)]

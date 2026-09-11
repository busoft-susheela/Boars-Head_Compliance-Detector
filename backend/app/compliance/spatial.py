"""Spatial utility functions for the compliance pipeline.

All functions operate on raw bounding-box tuples (x1, y1, x2, y2)
and plain (x, y) points — no YOLO or framework imports.

These functions mirror the spatial logic from the reference processing
script:  assign_person_to_sink, hand_is_near_sink, point_inside_expanded_box.
"""

from __future__ import annotations

import math


# ---------------------------------------------------------------------------
# Primitive helpers
# ---------------------------------------------------------------------------

def box_center(box: tuple[int, int, int, int]) -> tuple[int, int]:
    """Return the (x, y) pixel center of a bounding box."""
    x1, y1, x2, y2 = box
    return (x1 + x2) // 2, (y1 + y2) // 2


def point_distance(p1: tuple[int, int], p2: tuple[int, int]) -> float:
    """Euclidean distance between two (x, y) points."""
    dx = p1[0] - p2[0]
    dy = p1[1] - p2[1]
    return math.sqrt(dx * dx + dy * dy)


def point_inside_expanded_box(
    point: tuple[int, int],
    box: tuple[int, int, int, int],
    expand_x: float,
    expand_y: float,
) -> bool:
    """Return True if *point* falls inside *box* expanded by the given ratios.

    expand_x and expand_y are relative to the box width/height respectively.
    E.g. expand_x=0.15 extends each horizontal side by 15 % of the box width.
    """
    x1, y1, x2, y2 = box
    w = x2 - x1
    h = y2 - y1
    return (
        point[0] >= x1 - w * expand_x
        and point[0] <= x2 + w * expand_x
        and point[1] >= y1 - h * expand_y
        and point[1] <= y2 + h * expand_y
    )


# ---------------------------------------------------------------------------
# Person → Sink assignment
# ---------------------------------------------------------------------------

def assign_person_to_sink(
    person_box: tuple[int, int, int, int],
    sink_boxes: list[tuple[tuple[int, int, int, int], float]],
    max_distance_ratio: float = 2.0,
) -> int | None:
    """Return the index of the nearest sink to the person's lower-center point.

    Distance is normalised against the sink's diagonal so that camera scale
    does not require manual threshold tuning.

    Args:
        person_box:         Person bounding box (x1, y1, x2, y2).
        sink_boxes:         List of (sink_box, confidence) pairs.
        max_distance_ratio: Accept the sink only when its normalised distance
                            is <= this value.

    Returns:
        Index into *sink_boxes*, or None if no sink is within range.
    """
    if not sink_boxes:
        return None

    x1, y1, x2, y2 = person_box
    # Lower-center of the person (feet/waist) as the proximity anchor.
    person_anchor: tuple[int, int] = ((x1 + x2) // 2, y2)

    best_index: int | None = None
    best_distance = float("inf")

    for i, (sink_box, _) in enumerate(sink_boxes):
        sx1, sy1, sx2, sy2 = sink_box
        sink_center: tuple[int, int] = ((sx1 + sx2) // 2, (sy1 + sy2) // 2)
        sink_diag = point_distance((sx1, sy1), (sx2, sy2))
        if sink_diag == 0:
            continue
        dist = point_distance(person_anchor, sink_center)
        normalised = dist / sink_diag
        if normalised < best_distance:
            best_distance = normalised
            best_index = i

    if best_index is not None and best_distance <= max_distance_ratio:
        return best_index
    return None


# ---------------------------------------------------------------------------
# Hand → Sink proximity
# ---------------------------------------------------------------------------

def hand_is_near_sink(
    hand_box: tuple[int, int, int, int],
    sink_box: tuple[int, int, int, int],
    horizontal_margin: float = 0.30,
    top_margin: float = 1.50,
    bottom_margin: float = 0.20,
) -> bool:
    """Return True if *hand_box* overlaps the sink's expanded proximity zone.

    Margins are relative to the sink's own width/height:
        horizontal_margin: extend each side by this ratio × sink width
        top_margin:        extend upward by this ratio × sink height
                           (hands typically reach above the sink bowl)
        bottom_margin:     extend downward by this ratio × sink height

    Args:
        hand_box:           Hand bounding box (x1, y1, x2, y2).
        sink_box:           Sink bounding box (x1, y1, x2, y2).
        horizontal_margin:  Lateral expansion factor.
        top_margin:         Upward expansion factor (SINK_TOP_MARGIN).
        bottom_margin:      Downward expansion factor (SINK_BOTTOM_MARGIN).
    """
    sx1, sy1, sx2, sy2 = sink_box
    sw = sx2 - sx1
    sh = sy2 - sy1

    zone_x1 = sx1 - int(sw * horizontal_margin)
    zone_x2 = sx2 + int(sw * horizontal_margin)
    zone_y1 = sy1 - int(sh * top_margin)
    zone_y2 = sy2 + int(sh * bottom_margin)

    hx1, hy1, hx2, hy2 = hand_box
    # Axis-aligned overlap check.
    return (
        hx1 <= zone_x2
        and hx2 >= zone_x1
        and hy1 <= zone_y2
        and hy2 >= zone_y1
    )

from __future__ import annotations

from dataclasses import dataclass
from math import acos, degrees, hypot


@dataclass(frozen=True)
class StrokePoint:
    x: float
    y: float
    pressure: float
    t_ms: int


@dataclass(frozen=True)
class VectorShapeCandidate:
    shape_type: str
    confidence: float
    vertices_3d: tuple[tuple[float, float, float], ...]
    editable_handles: tuple[tuple[float, float], ...]


def extract_geometric_features(points: list[StrokePoint]) -> dict[str, float | int | bool]:
    if len(points) < 3:
        raise ValueError("At least three stroke points are required")
    xs, ys = [point.x for point in points], [point.y for point in points]
    corners = 0
    for previous, current, following in zip(points, points[1:], points[2:]):
        first = (current.x - previous.x, current.y - previous.y)
        second = (following.x - current.x, following.y - current.y)
        denominator = hypot(*first) * hypot(*second)
        if denominator and degrees(acos(max(-1, min(1, (first[0] * second[0] + first[1] * second[1]) / denominator)))) > 35:
            corners += 1
    return {
        "corner_count": corners,
        "bounding_box_ratio": (max(xs) - min(xs)) / max(max(ys) - min(ys), 1e-9),
        "closed_loop": hypot(points[0].x - points[-1].x, points[0].y - points[-1].y) < 25,
    }


def classify_shape(features: dict[str, float | int | bool]) -> VectorShapeCandidate:
    corners = int(features["corner_count"])
    closed = bool(features["closed_loop"])
    if closed and 3 <= corners <= 14:
        return VectorShapeCandidate("cube", 0.82, ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)), ((0, 0), (1, 1)))
    if closed and corners <= 2:
        return VectorShapeCandidate("cone", 0.70, ((0, 0, 1), (0, 0, 0)), ((0.5, 0),))
    return VectorShapeCandidate("unrecognized", 0.0, (), ())
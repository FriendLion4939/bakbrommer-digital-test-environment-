"""Route geometry: turns scenario segments into a densely sampled path.

The route is a list of samples at a fixed spacing along the path. Each sample
carries position, heading, curvature and the attributes of its segment
(target speed, surfaces, gradient, fixed throttle/brake). Per-step lookups
are simple list indexing.

Frames: the route starts at the world origin heading along +X. Each segment
is first described in its own local frame (x forward, y left) and then
attached to the end of the previous one.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray
from scipy.interpolate import CubicSpline

from bakbrommer_twin.scenarios.scenario import Segment

_OVERSAMPLE = 4  # local polylines are sampled this much finer than the final spacing
Array = NDArray[np.float64]


def _smoothstep(u: Array) -> Array:
    """0 → 1 with zero slope at both ends (3u² − 2u³), clamped."""
    u = np.clip(u, 0.0, 1.0)
    return np.asarray(u * u * (3.0 - 2.0 * u))


def _local_polyline(segment: Segment, step: float) -> tuple[Array, Array, float]:
    """Points of one segment in its local frame and the heading change at its end."""
    if segment.type == "straight":
        length = float(segment.length_m or 0.0)
        x = np.linspace(0.0, length, max(2, math.ceil(length / step) + 1))
        return x, np.zeros_like(x), 0.0
    if segment.type == "arc":
        radius = float(segment.radius_m or 0.0)
        angle = math.radians(segment.angle_deg or 0.0)
        count = max(2, math.ceil(radius * abs(angle) / step) + 1)
        a = np.linspace(0.0, abs(angle), count)
        side = 1.0 if angle >= 0.0 else -1.0
        return radius * np.sin(a), side * radius * (1.0 - np.cos(a)), angle
    if segment.type == "lane_change":
        length = float(segment.length_m or 0.0)
        x = np.linspace(0.0, length, max(2, math.ceil(length / step) + 1))
        # Cosine blend: zero slope at both ends, sideways shift = lateral_offset.
        y = 0.5 * float(segment.lateral_offset_m or 0.0) * (1.0 - np.cos(np.pi * x / length))
        return x, y, 0.0
    if segment.type == "slalom":
        spacing = float(segment.cone_spacing_m or 0.0)
        length = spacing * ((segment.cones or 1) + 1)
        x = np.linspace(0.0, length, max(2, math.ceil(length / step) + 1))
        # Weave with one half-wave per cone spacing; blended in and out over half
        # a spacing so the path starts and ends straight.
        window = _smoothstep(x / (0.5 * spacing)) * _smoothstep((length - x) / (0.5 * spacing))
        y = float(segment.lateral_offset_m or 0.0) * np.sin(np.pi * x / spacing) * window
        return x, y, 0.0
    points = np.array([(0.0, 0.0), *(segment.points or [])], dtype=float)
    chord = np.concatenate(([0.0], np.cumsum(np.hypot(*np.diff(points, axis=0).T))))
    if np.any(np.diff(chord) <= 0.0):
        raise ValueError("waypoints must not repeat the same point")
    # Smooth curve through the waypoints; it leaves the start straight ahead.
    spline = CubicSpline(chord, points, bc_type=((1, (1.0, 0.0)), (2, (0.0, 0.0))))
    u = np.linspace(0.0, chord[-1], max(2, math.ceil(chord[-1] * 1.5 / step) + 1))
    xy = spline(u)
    end_slope = spline(chord[-1], 1)
    return xy[:, 0], xy[:, 1], math.atan2(end_slope[1], end_slope[0])


class Route:
    """A sampled path with per-sample attributes (all SI units)."""

    def __init__(self, segments: Sequence[Segment], spacing: float,
                 default_surface: str) -> None:
        self.spacing = spacing
        self.has_path = True
        xs: list[Array] = []
        ys: list[Array] = []
        ends: list[float] = []  # cumulative path length at the end of each segment
        x0 = y0 = heading = total = 0.0
        for segment in segments:
            lx, ly, turn = _local_polyline(segment, spacing / _OVERSAMPLE)
            cos_h, sin_h = math.cos(heading), math.sin(heading)
            wx = x0 + cos_h * lx - sin_h * ly
            wy = y0 + sin_h * lx + cos_h * ly
            total += float(np.sum(np.hypot(np.diff(wx), np.diff(wy))))
            ends.append(total)
            xs.append(wx[1:] if xs else wx)
            ys.append(wy[1:] if ys else wy)
            x0, y0, heading = float(wx[-1]), float(wy[-1]), heading + turn
        fine_x, fine_y = np.concatenate(xs), np.concatenate(ys)
        fine_s = np.concatenate(([0.0], np.cumsum(np.hypot(np.diff(fine_x), np.diff(fine_y)))))
        self.length = float(fine_s[-1])
        count = max(2, round(self.length / spacing) + 1)
        s = np.linspace(0.0, self.length, count)
        x = np.interp(s, fine_s, fine_x)
        y = np.interp(s, fine_s, fine_y)
        heading_arr = np.unwrap(np.arctan2(np.gradient(y, s), np.gradient(x, s)))
        curvature = np.gradient(heading_arr, s)

        segment_index = np.minimum(np.searchsorted(np.array(ends), s, side="left"),
                                   len(segments) - 1)
        # Plain Python floats from here on: NumPy scalars would leak into the
        # per-step physics and make it several times slower.
        starts = [0.0, *ends[:-1]]
        lengths = [end - start for start, end in zip(starts, ends, strict=True)]
        self.s: list[float] = s.tolist()
        self.x: list[float] = x.tolist()
        self.y: list[float] = y.tolist()
        self.heading: list[float] = heading_arr.tolist()
        self.curvature: list[float] = curvature.tolist()
        self.segment: list[int] = segment_index.tolist()
        self.speed: list[float] = []
        self.grade: list[float] = []
        self.throttle: list[float] = []  # nan = speed control
        self.brake: list[float] = []  # nan = speed control
        self.surface_left: list[str] = []
        self.surface_center: list[str] = []
        self.surface_right: list[str] = []
        for position, index in zip(self.s, self.segment, strict=True):
            segment = segments[index]
            fraction = min(1.0, max(0.0, (position - starts[index]) / lengths[index]))
            end_speed = segment.speed_kmh if segment.speed_end_kmh is None else (
                segment.speed_end_kmh)
            self.speed.append((segment.speed_kmh + fraction * (end_speed - segment.speed_kmh))
                              / 3.6)
            self.grade.append(segment.gradient_pct / 100.0)
            self.throttle.append(math.nan if segment.throttle is None else segment.throttle)
            self.brake.append(math.nan if segment.brake is None else segment.brake)
            surface = segment.surface or default_surface
            self.surface_center.append(surface)
            self.surface_left.append(segment.surface_left or surface)
            self.surface_right.append(segment.surface_right or surface)

    def __len__(self) -> int:
        return len(self.s)

    def locate(self, x: float, y: float, hint: int) -> int:
        """Index of the sample nearest to (x, y), searching outwards from ``hint``."""
        xs, ys = self.x, self.y
        last = len(xs) - 1
        index = hint
        best = (xs[index] - x) ** 2 + (ys[index] - y) ** 2
        while index < last:
            ahead = (xs[index + 1] - x) ** 2 + (ys[index + 1] - y) ** 2
            if ahead >= best:
                break
            index += 1
            best = ahead
        while index > 0:
            behind = (xs[index - 1] - x) ** 2 + (ys[index - 1] - y) ** 2
            if behind >= best:
                break
            index -= 1
            best = behind
        return index

    def project(self, index: int, x: float, y: float) -> tuple[float, float]:
        """Path distance and sideways offset (+ = left of the route) of point (x, y)."""
        heading = self.heading[index]
        dx, dy = x - self.x[index], y - self.y[index]
        cos_h, sin_h = math.cos(heading), math.sin(heading)
        return self.s[index] + dx * cos_h + dy * sin_h, dy * cos_h - dx * sin_h

    def index_at(self, distance: float) -> int:
        """Index of the sample at path distance ``distance`` (clamped to the route)."""
        return min(len(self.s) - 1, max(0, round(distance / self.spacing)))

"""Pure geographic geometry used for shape projection and distance math.

At metro-network scale (tens of kilometres) an equirectangular local-plane
approximation is accurate to well under a metre per segment, which is far below
GPS noise, so we use it for point-to-segment projection and reserve the
haversine formula for absolute distances.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

_EARTH_RADIUS_M = 6_371_008.8
_M_PER_DEG_LAT = 111_320.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two WGS84 coordinates."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


@dataclass(frozen=True, slots=True)
class ShapeProjection:
    """Result of projecting a point onto a shape polyline."""

    distance_along_m: float
    offset_m: float
    segment_index: int


class ShapeGeometry:
    """A shape polyline with cumulative distances and point projection.

    Built once per shape and cached; all methods are pure and thread-safe.
    """

    def __init__(self, points: Sequence[tuple[float, float]]) -> None:
        if len(points) < 2:
            raise ValueError("a shape needs at least two points")
        self._points: tuple[tuple[float, float], ...] = tuple(points)
        cumulative = [0.0]
        for (lat1, lon1), (lat2, lon2) in zip(self._points, self._points[1:]):
            cumulative.append(cumulative[-1] + haversine_m(lat1, lon1, lat2, lon2))
        self._cumulative: tuple[float, ...] = tuple(cumulative)

    @property
    def total_length_m(self) -> float:
        """Total polyline length in metres."""
        return self._cumulative[-1]

    @property
    def points(self) -> tuple[tuple[float, float], ...]:
        """The (lat, lon) vertices of the polyline."""
        return self._points

    def project(self, lat: float, lon: float, min_distance_m: float = 0.0) -> ShapeProjection:
        """Project a point onto the polyline, returning the closest position.

        ``min_distance_m`` restricts the search to positions at or beyond that
        distance along the shape. This keeps successive projections monotonic,
        which matters for out-and-back shapes where the geometrically nearest
        segment may belong to the return leg.
        """
        best: ShapeProjection | None = None
        for i in range(len(self._points) - 1):
            seg_start_dist = self._cumulative[i]
            seg_end_dist = self._cumulative[i + 1]
            if seg_end_dist < min_distance_m:
                continue
            lat1, lon1 = self._points[i]
            lat2, lon2 = self._points[i + 1]
            along, offset = _project_to_segment(lat, lon, lat1, lon1, lat2, lon2)
            distance_along = seg_start_dist + along
            if distance_along < min_distance_m:
                # Clamp within this segment to honour the monotonicity floor.
                distance_along = min_distance_m
                clamped_t = (min_distance_m - seg_start_dist) / max(
                    seg_end_dist - seg_start_dist, 1e-9
                )
                clamped_t = min(max(clamped_t, 0.0), 1.0)
                plat = lat1 + (lat2 - lat1) * clamped_t
                plon = lon1 + (lon2 - lon1) * clamped_t
                offset = haversine_m(lat, lon, plat, plon)
            if best is None or offset < best.offset_m:
                best = ShapeProjection(distance_along, offset, i)
        assert best is not None  # len(points) >= 2 guarantees one segment
        return best

    def point_at(self, distance_m: float) -> tuple[float, float]:
        """Interpolate the (lat, lon) at a given distance along the shape."""
        target = min(max(distance_m, 0.0), self.total_length_m)
        for i in range(len(self._cumulative) - 1):
            if self._cumulative[i + 1] >= target:
                seg_len = self._cumulative[i + 1] - self._cumulative[i]
                t = 0.0 if seg_len <= 0 else (target - self._cumulative[i]) / seg_len
                lat1, lon1 = self._points[i]
                lat2, lon2 = self._points[i + 1]
                return lat1 + (lat2 - lat1) * t, lon1 + (lon2 - lon1) * t
        return self._points[-1]


def _project_to_segment(
    lat: float, lon: float, lat1: float, lon1: float, lat2: float, lon2: float
) -> tuple[float, float]:
    """Project a point onto one segment.

    Returns ``(distance_along_segment_m, perpendicular_offset_m)`` using a
    local equirectangular plane centred on the segment.
    """
    k_lon = _M_PER_DEG_LAT * math.cos(math.radians((lat1 + lat2) / 2.0))
    px = (lon - lon1) * k_lon
    py = (lat - lat1) * _M_PER_DEG_LAT
    sx = (lon2 - lon1) * k_lon
    sy = (lat2 - lat1) * _M_PER_DEG_LAT
    seg_len_sq = sx * sx + sy * sy
    if seg_len_sq <= 1e-12:
        return 0.0, math.hypot(px, py)
    t = min(max((px * sx + py * sy) / seg_len_sq, 0.0), 1.0)
    dx = px - t * sx
    dy = py - t * sy
    return t * math.sqrt(seg_len_sq), math.hypot(dx, dy)

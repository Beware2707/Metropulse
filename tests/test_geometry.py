"""Tests for haversine distance and shape projection."""

from __future__ import annotations

import pytest

from metropulse.domain.geometry import ShapeGeometry, haversine_m

# A straight west-east line at latitude 28.60 from lon 77.00 to 77.03.
LINE = [(28.60, 77.00 + i * 0.005) for i in range(7)]


def test_haversine_known_distance() -> None:
    # One degree of latitude is ~111.2 km.
    distance = haversine_m(28.0, 77.0, 29.0, 77.0)
    assert distance == pytest.approx(111_200, rel=0.01)


def test_haversine_zero_for_same_point() -> None:
    assert haversine_m(28.6, 77.0, 28.6, 77.0) == 0.0


def test_shape_requires_two_points() -> None:
    with pytest.raises(ValueError):
        ShapeGeometry([(28.6, 77.0)])


def test_total_length_matches_haversine_sum() -> None:
    geometry = ShapeGeometry(LINE)
    expected = haversine_m(28.60, 77.00, 28.60, 77.03)
    assert geometry.total_length_m == pytest.approx(expected, rel=1e-3)


def test_projection_on_vertex() -> None:
    geometry = ShapeGeometry(LINE)
    projection = geometry.project(28.60, 77.01)
    expected = haversine_m(28.60, 77.00, 28.60, 77.01)
    assert projection.distance_along_m == pytest.approx(expected, rel=1e-3)
    assert projection.offset_m < 1.0


def test_projection_off_line_reports_offset() -> None:
    geometry = ShapeGeometry(LINE)
    # ~111 m north of the line at lon 77.015.
    projection = geometry.project(28.601, 77.015)
    assert projection.offset_m == pytest.approx(111.2, rel=0.05)
    expected_along = haversine_m(28.60, 77.00, 28.60, 77.015)
    assert projection.distance_along_m == pytest.approx(expected_along, rel=0.01)


def test_projection_respects_min_distance_floor() -> None:
    # Out-and-back: the return leg passes over the same coordinates.
    out_and_back = LINE + LINE[-2::-1]
    geometry = ShapeGeometry(out_and_back)
    outbound_length = ShapeGeometry(LINE).total_length_m
    # Same physical point, but the floor forces the return-leg match.
    projection = geometry.project(28.60, 77.01, min_distance_m=outbound_length)
    assert projection.distance_along_m >= outbound_length
    assert projection.offset_m < 1.0


def test_point_at_interpolates_and_clamps() -> None:
    geometry = ShapeGeometry(LINE)
    lat, lon = geometry.point_at(geometry.total_length_m / 2)
    assert lat == pytest.approx(28.60, abs=1e-6)
    assert lon == pytest.approx(77.015, abs=1e-3)
    assert geometry.point_at(-5) == LINE[0]
    assert geometry.point_at(geometry.total_length_m + 5) == LINE[-1]

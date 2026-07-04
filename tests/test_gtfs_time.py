"""Tests for GTFS time/date parsing."""

from __future__ import annotations

from datetime import date

import pytest

from metropulse.domain.gtfs_time import format_gtfs_time, parse_gtfs_date, parse_gtfs_time


def test_parses_regular_time() -> None:
    assert parse_gtfs_time("08:30:15") == 8 * 3600 + 30 * 60 + 15


def test_parses_after_midnight_time() -> None:
    assert parse_gtfs_time("25:01:02") == 25 * 3600 + 62


def test_parses_single_digit_hour() -> None:
    assert parse_gtfs_time("8:00:00") == 8 * 3600


@pytest.mark.parametrize("bad", ["", "8:00", "aa:bb:cc", "08:61:00", "08:00:60", "-1:00:00"])
def test_rejects_malformed_time(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_gtfs_time(bad)


def test_format_round_trips() -> None:
    assert format_gtfs_time(parse_gtfs_time("26:05:09")) == "26:05:09"


def test_format_rejects_negative() -> None:
    with pytest.raises(ValueError):
        format_gtfs_time(-1)


def test_parses_date() -> None:
    assert parse_gtfs_date("20260815") == date(2026, 8, 15)


@pytest.mark.parametrize("bad", ["", "2026-08-15", "202608", "abcdefgh", "20261345"])
def test_rejects_malformed_date(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_gtfs_date(bad)

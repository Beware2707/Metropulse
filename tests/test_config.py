"""Tests for settings parsing and the ID-mapping file loader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from metropulse.config import IdMappingRule, Settings


def test_defaults_are_sane() -> None:
    settings = Settings(_env_file=None)
    assert settings.poll_interval_seconds == 5.0
    assert settings.stale_after_seconds == 90.0
    assert settings.gtfs_rt_vehicle_positions_url.endswith("VehiclePositions.pb")


def test_env_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DMRC_API_KEY", "abc123")
    monkeypatch.setenv("POLL_INTERVAL_SECONDS", "2.5")
    monkeypatch.setenv(
        "ID_MAPPING_RULES",
        json.dumps([{"field": "trip_id", "pattern": "^RT_", "replacement": ""}]),
    )
    settings = Settings(_env_file=None)
    assert settings.dmrc_api_key == "abc123"
    assert settings.poll_interval_seconds == 2.5
    assert settings.id_mapping_rules == [
        IdMappingRule(field="trip_id", pattern="^RT_", replacement="")
    ]


def test_id_mapping_file_loading(tmp_path: Path) -> None:
    mapping_file = tmp_path / "mapping.json"
    mapping_file.write_text(
        json.dumps({"trip_id": {"RT_1": "T1"}, "route_id": {"RED": "R1"}}),
        encoding="utf-8",
    )
    settings = Settings(_env_file=None, id_mapping_file=mapping_file)
    trip_map, route_map = settings.load_static_id_maps()
    assert trip_map == {"RT_1": "T1"}
    assert route_map == {"RED": "R1"}


def test_id_mapping_file_absent_returns_empty_maps() -> None:
    settings = Settings(_env_file=None)
    assert settings.load_static_id_maps() == ({}, {})


def test_id_mapping_file_bad_structure_raises(tmp_path: Path) -> None:
    mapping_file = tmp_path / "bad.json"
    mapping_file.write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
    settings = Settings(_env_file=None, id_mapping_file=mapping_file)
    with pytest.raises(ValueError):
        settings.load_static_id_maps()


def test_invalid_poll_interval_rejected() -> None:
    with pytest.raises(Exception):
        Settings(_env_file=None, poll_interval_seconds=0)

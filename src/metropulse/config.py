"""Application settings.

All runtime configuration is read from environment variables (optionally via a
local ``.env`` file). The config module is a shared kernel: it may be imported
by wiring code (``main``/``cli``) but application services receive plain values
so they stay independent of the settings mechanism.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class IdMappingRule(BaseModel):
    """A regex rewrite rule applied to realtime IDs before static lookup."""

    field: Literal["trip_id", "route_id"]
    pattern: str
    replacement: str


class Settings(BaseSettings):
    """Environment-driven configuration for every MetroPulse process."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # External services
    database_url: str = "postgresql+asyncpg://metropulse:metropulse@localhost:5432/metropulse"
    redis_url: str = "redis://localhost:6379/0"

    # Delhi Open Transit Data realtime feed
    dmrc_api_key: str = ""
    gtfs_rt_vehicle_positions_url: str = (
        "https://otd.delhi.gov.in/api/realtime/VehiclePositions.pb"
    )

    # Realtime engine
    poll_interval_seconds: float = Field(default=5.0, gt=0)
    http_timeout_seconds: float = Field(default=10.0, gt=0)
    fetch_max_attempts: int = Field(default=3, ge=1)
    stale_after_seconds: float = Field(default=90.0, gt=0)
    history_retention_hours: float = Field(default=72.0, gt=0)

    # Route resolution / ETA
    station_radius_m: float = Field(default=75.0, gt=0)
    default_speed_mps: float = Field(default=9.0, gt=0)
    min_speed_mps: float = Field(default=2.0, gt=0)
    max_speed_mps: float = Field(default=25.0, gt=0)
    dwell_time_seconds: float = Field(default=25.0, ge=0)
    id_mapping_rules: list[IdMappingRule] = Field(default_factory=list)
    id_mapping_file: Path | None = None

    # WebSocket
    ws_heartbeat_seconds: float = Field(default=20.0, gt=0)
    ws_replay_buffer_size: int = Field(default=512, ge=1)

    # Commuter features
    admin_api_key: str = ""  # empty disables all admin endpoints
    timezone: str = "Asia/Kolkata"
    reminder_eval_interval_seconds: float = Field(default=60.0, gt=0)
    journey_max_age_hours: float = Field(default=6.0, gt=0)
    analytics_retention_days: float = Field(default=90.0, gt=0)
    analytics_max_batch: int = Field(default=500, ge=1)
    default_coach_count: int = Field(default=8, ge=1)
    crowd_lookback_days: int = Field(default=28, ge=1)
    crowd_hour_window: int = Field(default=1, ge=0)

    log_level: str = "INFO"

    def load_static_id_maps(self) -> tuple[dict[str, str], dict[str, str]]:
        """Load explicit ``(trip_id_map, route_id_map)`` from ``id_mapping_file``.

        Returns empty maps when no file is configured. Raises ``ValueError`` if
        the file exists but does not contain the expected structure.
        """
        if self.id_mapping_file is None:
            return {}, {}
        raw = json.loads(self.id_mapping_file.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("id mapping file must contain a JSON object")
        trip_map = raw.get("trip_id", {})
        route_map = raw.get("route_id", {})
        if not isinstance(trip_map, dict) or not isinstance(route_map, dict):
            raise ValueError("id mapping file keys 'trip_id'/'route_id' must map to objects")
        return (
            {str(k): str(v) for k, v in trip_map.items()},
            {str(k): str(v) for k, v in route_map.items()},
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()

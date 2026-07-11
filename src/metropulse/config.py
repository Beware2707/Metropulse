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

from pydantic import BaseModel, Field, SecretStr
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

    # Delhi Open Transit Data realtime feed. SecretStr keeps the key out of
    # reprs, logs and tracebacks; unwrap with .get_secret_value() at use sites.
    dmrc_api_key: SecretStr = SecretStr("")
    gtfs_rt_vehicle_positions_url: str = (
        "https://otd.delhi.gov.in/api/realtime/VehiclePositions.pb"
    )
    # False by default: this URL is Delhi's citywide bus GPS feed, not a
    # verified Delhi Metro train feed (confirmed by inspecting real feed
    # entities -- vehicle IDs are road registration plates, ~4,000
    # simultaneous vehicles, coordinates spread across ordinary roads, none
    # of which match a metro network). Leaving this off makes the worker use
    # ScheduleEstimatedPositionSource (schedule-interpolated positions,
    # honestly labelled "schedule_estimate") instead of polling this feed and
    # mislabelling bus GPS as train GPS. Flip to true only once a feed is
    # confirmed to actually be Delhi Metro rolling stock.
    gtfs_rt_enabled: bool = False

    # DMRC's static GTFS feed, and an optional background job that
    # periodically checks it for updates and auto-loads a new one when found
    # (see application/gtfs_static_updater.py). Off by default: the endpoint
    # only accepts a POST with a CSRF cookie/token pair, satisfied today by
    # a documented but unofficial workaround (see
    # infrastructure/gtfs_static/dmrc_client.py) that could break if DMRC
    # changes their site -- so this is an explicit opt-in, not something
    # silently polling a third-party site by default. When enabled, the
    # worker POSTs to this URL every gtfs_static_check_interval_seconds and
    # only re-validates/reloads when the response's ETag actually differs
    # from the last one seen (see infrastructure/db DatasetVersion rows of
    # kind "gtfs_static_remote_etag").
    gtfs_static_url: str = "https://otd.delhi.gov.in/data/staticDMRC/"
    gtfs_static_auto_update_enabled: bool = False
    gtfs_static_check_interval_seconds: float = Field(default=86400.0, gt=0)

    # Realtime engine
    poll_interval_seconds: float = Field(default=5.0, gt=0)
    http_timeout_seconds: float = Field(default=10.0, gt=0)
    fetch_max_attempts: int = Field(default=3, ge=1)
    stale_after_seconds: float = Field(default=90.0, gt=0)
    history_retention_hours: float = Field(default=72.0, gt=0)

    # Feed health: /health reports the feed stale beyond this age.
    feed_health_max_age_seconds: float = Field(default=60.0, gt=0)

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
    admin_api_key: SecretStr = SecretStr("")  # empty disables all admin endpoints
    timezone: str = "Asia/Kolkata"
    reminder_eval_interval_seconds: float = Field(default=60.0, gt=0)
    journey_max_age_hours: float = Field(default=6.0, gt=0)
    journey_delay_notify_seconds: float = Field(default=300.0, gt=0)
    analytics_retention_days: float = Field(default=90.0, gt=0)
    analytics_max_batch: int = Field(default=500, ge=1)
    default_coach_count: int = Field(default=8, ge=1)
    crowd_lookback_days: int = Field(default=28, ge=1)
    crowd_hour_window: int = Field(default=1, ge=0)

    # Metro Intelligence: commute prediction and delay estimation lookback
    # windows (see application/intelligence/).
    commute_prediction_lookback_days: float = Field(default=90.0, gt=0)
    delay_prediction_lookback_days: float = Field(default=60.0, gt=0)

    # Metro Intelligence: proactive "time to leave" nudges, derived from
    # CommutePredictionService rather than a user-created reminder (see
    # application/intelligence/proactive_scheduler.py).
    proactive_commute_eval_interval_seconds: float = Field(default=300.0, gt=0)
    proactive_commute_lead_minutes: float = Field(default=15.0, gt=0)
    proactive_commute_min_confidence: float = Field(default=0.5, ge=0, le=1)

    # Metro Intelligence: optional LLM-assisted delay-estimate refinement
    # (see application/intelligence/llm_delay_refiner.py). Any subset of the
    # three provider keys may be set; configured providers are tried in
    # priority order (Claude, then OpenAI, then Gemini) with automatic
    # fallover on failure (see infrastructure/llm_fallback.py). All three
    # empty leaves this feature completely inert — DelayPredictionService's
    # plain historical estimate is used everywhere, unchanged. SecretStr
    # keeps each key out of reprs, logs and tracebacks; unwrap with
    # .get_secret_value() at the one call site that constructs each client.
    anthropic_api_key: SecretStr = SecretStr("")
    claude_model: str = "claude-sonnet-5"
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = "gpt-5.5"
    google_api_key: SecretStr = SecretStr("")
    # An alias, not a dated snapshot -- Google moves this to point at
    # whatever the current GA Flash release is, which matters more here
    # than pinning a specific version: this refiner just needs "a
    # reasonably capable, current model," not a fixed evaluation target.
    gemini_model: str = "gemini-flash-latest"
    llm_delay_refinement_eval_interval_seconds: float = Field(default=1800.0, gt=0)
    llm_delay_refinement_min_sample_size: int = Field(default=10, ge=1)
    llm_delay_refinement_max_buckets_per_cycle: int = Field(default=20, ge=1)
    llm_delay_refinement_max_age_seconds: float = Field(default=3600.0, gt=0)
    llm_delay_refinement_max_adjustment_fraction: float = Field(default=0.5, gt=0)

    # Commute Replay: the rolling window summed into the "This Month" card
    # (see application/intelligence/commute_impact.py).
    commute_replay_window_days: float = Field(default=30.0, gt=0)

    # Ops: rate limiting is per-replica defence in depth (0 disables); real
    # deployments should still enforce global limits at the edge/gateway.
    rate_limit_per_minute: int = Field(default=600, ge=0)
    rate_limit_burst: int = Field(default=100, ge=1)

    log_level: str = "INFO"
    log_format: Literal["text", "json"] = "text"

    # CORS: browsers preflight every cross-origin request the Flutter web
    # client makes (dev server on its own port, or a separately hosted PWA).
    # Native (Android/iOS) callers are unaffected since they don't do CORS.
    cors_allow_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )

    def load_static_id_maps(self) -> tuple[dict[str, str], dict[str, str]]:
        """Load explicit ``(trip_id_map, route_id_map)`` from ``id_mapping_file``.

        Returns empty maps when no file is configured. Raises ``ValueError`` if
        the file exists but does not contain the expected structure.
        """
        raw = self._read_mapping_file()
        if raw is None:
            return {}, {}
        trip_map = raw.get("trip_id", {})
        route_map = raw.get("route_id", {})
        if not isinstance(trip_map, dict) or not isinstance(route_map, dict):
            raise ValueError("id mapping file keys 'trip_id'/'route_id' must map to objects")
        return (
            {str(k): str(v) for k, v in trip_map.items()},
            {str(k): str(v) for k, v in route_map.items()},
        )

    def load_id_mapping_rules(self) -> list[IdMappingRule]:
        """All configured rewrite rules: environment rules plus file rules.

        A single agency-profile JSON file can therefore fully configure the
        resolver: explicit maps under ``trip_id``/``route_id`` and regex
        rewrites under ``rules`` — one deployment per agency, zero code.
        """
        rules = list(self.id_mapping_rules)
        raw = self._read_mapping_file()
        if raw is not None:
            file_rules = raw.get("rules", [])
            if not isinstance(file_rules, list):
                raise ValueError("id mapping file key 'rules' must be a list")
            rules.extend(IdMappingRule.model_validate(rule) for rule in file_rules)
        return rules

    def _read_mapping_file(self) -> dict[str, object] | None:
        if self.id_mapping_file is None:
            return None
        raw = json.loads(self.id_mapping_file.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("id mapping file must contain a JSON object")
        return raw


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()

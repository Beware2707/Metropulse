"""Door-to-door multimodal journeys via the Delhi Transport Stack API.

DTS's Journey Planner combines DTC/DIMTS buses, the metro and walking into
ranked door-to-door options — the bus data MetroPulse deliberately deferred
until a licensed source existed. This proxies it server-side:

* The API key stays HERE, read from settings (env ``DTS_API_KEY``) — never in
  the client binary, never in the repo. With no key configured the feature is
  off and the endpoint says so plainly.
* License (Transport Stack, Schedule 1): attribution required — the
  normalized response carries ``attribution`` and the client must show it.
  Use in a multi-source app is explicitly permitted.
* Honesty: DTS self-declares per response whether live bus data shaped it
  (``response_type``: "static" | realtime). That label is passed through
  verbatim — MetroPulse must not upgrade "static" to anything livelier.

Upstream shapes (probed 2026-07-24): ``data[]`` options, each with
``directions.routes[]`` legs (type walk|bus|metro, agency, routes[],
long_name headsign, departure_time, trip_time minutes, fare, stops[]) and
top-level ``trip_time``/``total_fare``/``reach_by``/``response_type``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

_MAX_OPTIONS = 5

ATTRIBUTION = "Journey options: Delhi Transport Stack"


@dataclass(frozen=True, slots=True)
class MultimodalLeg:
    """One leg of a door-to-door option, normalized for the client."""

    kind: str  # walk|bus|metro|...
    agency: str
    route: str
    headsign: str
    departure_time: str
    minutes: float
    fare: float
    from_name: str
    to_name: str
    stop_count: int


@dataclass(frozen=True, slots=True)
class MultimodalOption:
    """One ranked door-to-door journey option."""

    total_minutes: float
    total_fare: float
    fare_unit: str
    reach_by: str
    response_type: str  # DTS's own static/realtime label, passed through
    legs: list[MultimodalLeg]


@dataclass(frozen=True, slots=True)
class MultimodalResult:
    """The normalized answer, or the reason there isn't one."""

    options: list[MultimodalOption] = field(default_factory=list)
    attribution: str = ATTRIBUTION
    error: str | None = None  # 'not_configured' | 'upstream_error' | 'no_route'


def _leg_from(raw: dict[str, Any]) -> MultimodalLeg:
    stops = [s for s in (raw.get("stops") or []) if isinstance(s, dict)]
    routes = [str(r) for r in (raw.get("routes") or []) if r]
    return MultimodalLeg(
        kind=str(raw.get("type") or "unknown"),
        agency=str(raw.get("agency") or ""),
        route=routes[0] if routes else "",
        headsign=str(raw.get("long_name") or "").strip(),
        departure_time=str(raw.get("departure_time") or ""),
        minutes=float(raw.get("trip_time") or 0),
        fare=float(raw.get("fare") or 0),
        from_name=str(stops[0].get("name")) if stops else "",
        to_name=str(stops[-1].get("name")) if stops else "",
        stop_count=len(stops),
    )


def normalize_options(payload: dict[str, Any]) -> list[MultimodalOption]:
    """Upstream response -> ranked options (upstream order kept, capped)."""
    options: list[MultimodalOption] = []
    for opt in payload.get("data") or []:
        if not isinstance(opt, dict):
            continue
        raw_legs = ((opt.get("directions") or {}).get("routes")) or []
        legs = [_leg_from(leg) for leg in raw_legs if isinstance(leg, dict)]
        if not legs:
            continue
        options.append(
            MultimodalOption(
                total_minutes=float(opt.get("trip_time") or 0),
                total_fare=float(opt.get("total_fare") or 0),
                fare_unit=str(opt.get("fare_unit") or "₹"),
                reach_by=str(opt.get("reach_by") or ""),
                response_type=str(opt.get("response_type") or "static"),
                legs=legs,
            )
        )
        if len(options) >= _MAX_OPTIONS:
            break
    return options


class MultimodalPlanService:
    """Server-side proxy over the DTS multi-modal journey planner."""

    def __init__(self, api_key: str, base_url: str, timeout_seconds: float = 30.0) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._client: httpx.AsyncClient | None = None

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout),
                limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
                headers={
                    "User-Agent": "MetroPulse/1.0",
                    "x-api-key": self._api_key,
                },
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def plan(
        self,
        src_lat: float,
        src_lon: float,
        dst_lat: float,
        dst_lon: float,
        depart_hhmmss: str | None = None,
    ) -> MultimodalResult:
        """Door-to-door options between two coordinates.

        ``depart_hhmmss`` is local (IST) 'HH:MM:SS'; omitted means "now" as
        interpreted upstream. Failures degrade to an explicit error marker —
        the client shows "unavailable", never a guessed route.
        """
        if not self.configured:
            return MultimodalResult(error="not_configured")
        params: dict[str, str] = {
            "src": f"[{src_lat},{src_lon}]",
            "src_type": "place",
            "dst": f"[{dst_lat},{dst_lon}]",
            "dst_type": "place",
            "mode": "multi",
        }
        if depart_hhmmss:
            params["time"] = depart_hhmmss
        try:
            response = await self._http().get(
                f"{self._base_url}/api/serviceset/journey-planner/multi_modal",
                params=params,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return MultimodalResult(error="upstream_error")
        options = normalize_options(payload if isinstance(payload, dict) else {})
        if not options:
            return MultimodalResult(error="no_route")
        return MultimodalResult(options=options)

"""Tests for the Delhi Transport Stack multimodal proxy.

Pinned behaviours:
* the normalizer handles the REAL upstream shape (fixture trimmed from a live
  2026-07-24 response) — legs keep order, headsigns and fares survive;
* DTS's own ``response_type`` label passes through verbatim — "static" must
  never be upgraded to something livelier;
* no key configured => explicit 'not_configured', never a guessed route;
* upstream failure => 'upstream_error'; empty data => 'no_route';
* the attribution string required by the license rides on every result.
"""

from __future__ import annotations

import httpx

from metropulse.application.commuter.multimodal import (
    ATTRIBUTION,
    MultimodalPlanService,
    normalize_options,
)

# Trimmed from a real response (option 0 of 11): walk -> DTC bus -> walk ->
# Yellow Line metro -> walk.
_REAL_SHAPE = {
    "message": "Success",
    "version": "v2",
    "description": "Route found",
    "data": [
        {
            "fare_unit": "₹",
            "trip_time": 73.0,
            "total_fare": 10.0,
            "response_type": "static",
            "reach_by": "10:45:07",
            "directions": {
                "routes": [
                    {
                        "type": "walk", "agency": "Last Mile", "routes": ["walk"],
                        "long_name": "", "departure_time": "09:31:30",
                        "trip_time": 7, "fare": 0,
                        "stops": [
                            {"id": -1, "name": "Your location"},
                            {"id": 2876, "name": "Batra Hospital (Satya Narayan Mandir)"},
                        ],
                    },
                    {
                        "type": "bus", "agency": "DTC", "routes": ["448DOWN"],
                        "long_name": " towards Punjabi Bagh Terminal",
                        "departure_time": "09:42:33", "trip_time": 20, "fare": 0,
                        "stops": [{"id": 1, "name": "Batra Hospital (Satya Narayan Mandir)"}]
                        + [{"id": n, "name": f"stop{n}"} for n in range(2, 24)]
                        + [{"id": 24, "name": "AIIMS Gate No.1"}],
                    },
                    {
                        "type": "metro", "agency": "DMRC", "routes": ["YELLOW"],
                        "long_name": " towards Vishwavidyalaya",
                        "departure_time": "10:19:57", "trip_time": 24, "fare": 10,
                        "stops": [{"id": 1, "name": "AIIMS"}]
                        + [{"id": n, "name": f"s{n}"} for n in range(2, 13)]
                        + [{"id": 13, "name": "Vishwavidyalaya"}],
                    },
                ]
            },
        }
    ],
}


def test_normalizer_handles_the_real_shape() -> None:
    options = normalize_options(_REAL_SHAPE)
    assert len(options) == 1
    opt = options[0]
    assert opt.total_minutes == 73.0 and opt.total_fare == 10.0
    assert opt.reach_by == "10:45:07"
    assert opt.response_type == "static", (
        "DTS's own label passes through verbatim — never upgraded"
    )
    kinds = [(leg.kind, leg.agency) for leg in opt.legs]
    assert kinds == [("walk", "Last Mile"), ("bus", "DTC"), ("metro", "DMRC")]
    bus = opt.legs[1]
    assert bus.route == "448DOWN"
    assert bus.headsign == "towards Punjabi Bagh Terminal"
    assert bus.from_name == "Batra Hospital (Satya Narayan Mandir)"
    assert bus.to_name == "AIIMS Gate No.1"
    metro = opt.legs[2]
    assert metro.route == "YELLOW" and metro.fare == 10.0


def test_normalizer_drops_malformed_options_quietly() -> None:
    payload = {"data": ["junk", {"directions": {"routes": []}}, None]}
    assert normalize_options(payload) == []


async def test_unconfigured_service_says_so() -> None:
    service = MultimodalPlanService(api_key="", base_url="https://example.invalid")
    result = await service.plan(28.5, 77.2, 28.6, 77.25)
    assert result.error == "not_configured"
    assert result.options == []
    assert result.attribution == ATTRIBUTION, (
        "the license's attribution requirement rides on every result"
    )


def _service_with(handler: httpx.MockTransport) -> MultimodalPlanService:
    service = MultimodalPlanService(api_key="test-key", base_url="https://dts.test")
    service._client = httpx.AsyncClient(  # noqa: SLF001 - test seam
        transport=handler, headers={"x-api-key": "test-key"}
    )
    return service


async def test_plan_calls_upstream_and_normalizes() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("x-api-key")
        return httpx.Response(200, json=_REAL_SHAPE)

    service = _service_with(httpx.MockTransport(handler))
    result = await service.plan(28.507767, 77.242589, 28.5829873, 77.2416624, "09:31:30")
    assert result.error is None and len(result.options) == 1
    assert seen["key"] == "test-key"
    assert "mode=multi" in seen["url"] and "time=09%3A31%3A30" in seen["url"]
    assert "%5B28.507767%2C77.242589%5D" in seen["url"], (
        "coordinates travel as the [lat,lon] form the API requires"
    )


async def test_upstream_failure_is_an_explicit_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    service = _service_with(httpx.MockTransport(handler))
    result = await service.plan(28.5, 77.2, 28.6, 77.25)
    assert result.error == "upstream_error" and result.options == []


async def test_route_not_found_is_no_route() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": "Success", "data": []})

    service = _service_with(httpx.MockTransport(handler))
    result = await service.plan(28.5, 77.2, 28.6, 77.25)
    assert result.error == "no_route"


def test_schema_serializes_slotted_legs() -> None:
    """Caught live: MultimodalLeg is a slots dataclass, and vars() on it
    raised TypeError in production -- from_domain was the one untested seam."""
    from metropulse.api.schemas_commuter import MultimodalPlanOut

    result_options = normalize_options(_REAL_SHAPE)
    from metropulse.application.commuter.multimodal import MultimodalResult

    out = MultimodalPlanOut.from_domain(MultimodalResult(options=result_options))
    assert out.error is None
    assert out.options[0].legs[1].route == "448DOWN"
    assert out.attribution == ATTRIBUTION

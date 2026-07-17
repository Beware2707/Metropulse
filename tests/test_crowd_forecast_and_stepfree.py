"""Tests for the crowd forecast service and step-free gate reachability.

The honesty-relevant behaviours pinned:
* crowding levels compare a station against ITS OWN peak (a small station's
  rush hour reads busy for that station);
* stations without data are reported, contribute nothing, and a quieter-time
  suggestion is disqualified if any stop loses data at the candidate hour;
* a suggestion only appears when meaningfully quieter (>= 0.15 gain);
* a gate with no mapped edges is NOT step-free-qualified (absence of data),
  and a gate connected to a lift+platform component through a concourse node
  IS — most real chains route through concourses.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from metropulse.application.commuter.accessibility_graph import step_free_gate_ids
from metropulse.application.commuter.crowd_forecast import CrowdForecastService
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.commuter_models import StationHourlyLoad

IST = ZoneInfo("Asia/Kolkata")

# Hour convention: index 0 = 04:00. 18:00 -> index 14.
_EVENING = datetime(2026, 7, 15, 18, 0, tzinfo=IST)  # a Wednesday


def _profile(peak_index: int, peak: int, base: int) -> dict:
    entries = [base] * 24
    entries[peak_index] = peak
    return {"weekday": {"entries": entries, "exits": entries, "days": 100}}


async def _seed(session_factory: SessionFactory, rows: list[StationHourlyLoad]) -> None:
    async with session_factory() as session:
        async with session.begin():
            session.add_all(rows)


async def test_levels_are_relative_to_each_stations_own_peak(
    session_factory: SessionFactory,
) -> None:
    # S1 peaks at 18:00 (the query hour); S2's peak is at 08:00 so 18:00 is quiet.
    await _seed(session_factory, [
        StationHourlyLoad(stop_id="S1", period="p", match_method="code",
                          profiles=_profile(peak_index=14, peak=1000, base=100)),
        StationHourlyLoad(stop_id="S2", period="p", match_method="code",
                          profiles=_profile(peak_index=4, peak=5000, base=500)),
    ])
    service = CrowdForecastService()
    async with session_factory() as session:
        forecast = await service.forecast(session, ["S1", "S2"], _EVENING)
    by_id = {s.stop_id: s for s in forecast.stops}
    assert by_id["S1"].level == "peak" and by_id["S1"].ratio == 1.0
    assert by_id["S2"].level == "quiet", (
        "5000 absolute riders at S2's 08:00 peak must not make its 18:00 busy"
    )
    assert forecast.busiest is not None and forecast.busiest.stop_id == "S1"
    assert forecast.period == "p"


async def test_missing_stations_are_reported_not_guessed(
    session_factory: SessionFactory,
) -> None:
    await _seed(session_factory, [
        StationHourlyLoad(stop_id="S1", period="p", match_method="code",
                          profiles=_profile(peak_index=14, peak=1000, base=100)),
    ])
    service = CrowdForecastService()
    async with session_factory() as session:
        forecast = await service.forecast(session, ["S1", "S9"], _EVENING)
    assert forecast.no_data_stop_ids == ["S9"]
    assert [s.stop_id for s in forecast.stops] == ["S1"]


async def test_quieter_departure_suggested_when_meaningfully_quieter(
    session_factory: SessionFactory,
) -> None:
    # Peak at 18:00; two hours later it is back to base (10% of peak).
    await _seed(session_factory, [
        StationHourlyLoad(stop_id="S1", period="p", match_method="code",
                          profiles=_profile(peak_index=14, peak=1000, base=100)),
    ])
    service = CrowdForecastService()
    async with session_factory() as session:
        forecast = await service.forecast(session, ["S1"], _EVENING)
    assert forecast.quieter is not None
    assert forecast.quieter.busiest_ratio < 0.2
    assert forecast.quieter.gain > 0.7


async def test_flat_profile_yields_no_suggestion(
    session_factory: SessionFactory,
) -> None:
    """Uniform load all day: shifting the trip gains nothing — say nothing."""
    await _seed(session_factory, [
        StationHourlyLoad(stop_id="S1", period="p", match_method="code",
                          profiles={"weekday": {"entries": [500] * 24,
                                                "exits": [500] * 24, "days": 10}}),
    ])
    service = CrowdForecastService()
    async with session_factory() as session:
        forecast = await service.forecast(session, ["S1"], _EVENING)
    assert forecast.quieter is None, (
        "advice that saves nothing is noise, not honesty"
    )


def test_step_free_gate_through_a_concourse_node() -> None:
    """Gate -> concourse -> lift -> platform: qualified, via an unknown node."""
    gates = [{"id": "G1"}, {"id": "G2"}]
    lifts = [{"id": "L1"}]
    platforms = [{"id": "P1"}]
    edges = [
        {"from": "G1", "to": "CONCOURSE_X"},  # concourse: appears only in edges
        {"from": "CONCOURSE_X", "to": "L1"},
        {"from": "L1", "to": "P1"},
        # G2 has no edges at all.
    ]
    assert step_free_gate_ids(gates, lifts, platforms, edges) == {"G1"}


def test_gate_connected_to_lift_but_no_platform_does_not_qualify() -> None:
    gates = [{"id": "G1"}]
    lifts = [{"id": "L1"}]
    platforms = [{"id": "P1"}]  # exists but disconnected
    edges = [{"from": "G1", "to": "L1"}]
    assert step_free_gate_ids(gates, lifts, platforms, edges) == set()


def test_self_loops_and_dangling_ids_do_not_crash_or_qualify() -> None:
    """The real feed has self-loop edges and mangled free-text endpoints."""
    gates = [{"id": "G1"}]
    lifts = [{"id": "L1"}]
    platforms = [{"id": "P1"}]
    edges = [
        {"from": "L1", "to": "L1"},                       # self-loop (real: PW1001)
        {"from": "G1", "to": "st_x_no_lift_at_gate_04"},  # mangled remark
    ]
    assert step_free_gate_ids(gates, lifts, platforms, edges) == set()


async def test_quiet_route_never_gets_moved_to_the_dead_of_night(
    session_factory: SessionFactory,
) -> None:
    """Caught live: at a quiet 22:00 the service suggested 01:00 -- 'quieter'
    only because the metro is closed then. Quiet routes get no suggestion."""
    late = datetime(2026, 7, 15, 22, 0, tzinfo=IST)
    entries = [0] * 24
    entries[14] = 1000   # 18:00 peak
    entries[18] = 220    # 22:00 -- quiet (ratio 0.22)
    # 00:00-03:59 (indices 20-23) stay 0: the metro is closed.
    await _seed(session_factory, [
        StationHourlyLoad(stop_id="S1", period="p", match_method="code",
                          profiles={"weekday": {"entries": entries,
                                                "exits": entries, "days": 100}}),
    ])
    service = CrowdForecastService()
    async with session_factory() as session:
        forecast = await service.forecast(session, ["S1"], late)
    assert forecast.busiest is not None and forecast.busiest.level == "quiet"
    assert forecast.quieter is None, (
        "a 1 AM 'improvement' over a quiet evening is advice to catch a train "
        "that does not exist"
    )

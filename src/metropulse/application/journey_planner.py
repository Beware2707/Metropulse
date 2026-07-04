"""Journey planner: shortest-path routing over the static GTFS network.

The network graph is built from route *patterns* (the representative trip per
route/direction, as metro trips of one direction share a station sequence):

- ride edges between consecutive pattern stops, weighted by scheduled travel
  time from stop_times;
- walking edges between distinct stations that share a parent_station or lie
  within walking range, weighted by distance plus a transfer overhead;
- a boarding penalty modelling expected platform wait, which also makes
  Dijkstra naturally minimise interchanges.

The graph is cached in-process and keyed by the loaded dataset version, so a
static reload invalidates it automatically.
"""

from __future__ import annotations

import asyncio
import heapq
import itertools
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.domain.entities import utcnow
from metropulse.domain.exceptions import NoRouteError, UnknownEntityError
from metropulse.domain.geometry import haversine_m
from metropulse.domain.journey import JourneyPlan, JourneyStop, RideLeg, WalkLeg
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.commuter_repositories import DatasetVersionRepository
from metropulse.infrastructure.db.models import Route, Stop, StopTime, Trip
from metropulse.infrastructure.db.repositories import StopRepository, TripRepository

logger = logging.getLogger(__name__)

PatternKey = tuple[str, int]  # (route_id, direction bucket)


@dataclass(frozen=True, slots=True)
class PatternStop:
    """One stop within a route pattern."""

    stop_id: str
    name: str
    arrival_seconds: int
    departure_seconds: int


@dataclass(frozen=True, slots=True)
class Pattern:
    """A route/direction's canonical station sequence."""

    key: PatternKey
    route_id: str
    direction_id: int | None
    headsign: str
    route_short_name: str | None
    route_long_name: str | None
    route_color: str | None
    stops: tuple[PatternStop, ...]


@dataclass(frozen=True, slots=True)
class WalkEdge:
    """A walkable connection between two stations."""

    to_stop_id: str
    distance_m: float
    walk_seconds: float


@dataclass
class NetworkGraph:
    """The routable network derived from one static dataset version."""

    version: str | None
    patterns: dict[PatternKey, Pattern]
    patterns_at: dict[str, list[tuple[PatternKey, int]]]
    walk_edges: dict[str, list[WalkEdge]]
    stop_names: dict[str, str]


@dataclass(frozen=True, slots=True)
class PlannerParameters:
    """Tunable weights for path search."""

    walk_max_m: float = 300.0
    walk_speed_mps: float = 1.3
    transfer_overhead_seconds: float = 120.0
    board_penalty_seconds: float = 300.0
    min_hop_seconds: float = 30.0


# Dijkstra states: ("at", stop_id) off-train, ("on", pattern_key, index) riding.
_State = tuple


class JourneyPlanner:
    """Plans origin→destination journeys over the loaded GTFS network."""

    def __init__(
        self,
        session_factory: SessionFactory,
        params: PlannerParameters | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._params = params or PlannerParameters()
        self._graph: NetworkGraph | None = None
        self._lock = asyncio.Lock()

    async def plan(
        self,
        origin_stop_id: str,
        destination_stop_id: str,
        departure_at: datetime | None = None,
    ) -> JourneyPlan:
        """Best journey between two stations.

        Raises :class:`UnknownEntityError` for unknown stops and
        :class:`NoRouteError` when the network offers no connection.
        """
        if origin_stop_id == destination_stop_id:
            raise NoRouteError("origin and destination are the same station")
        graph = await self._get_graph()
        for stop_id in (origin_stop_id, destination_stop_id):
            if stop_id not in graph.stop_names:
                raise UnknownEntityError(f"stop '{stop_id}' not found")

        actions = self._dijkstra(graph, origin_stop_id, destination_stop_id)
        if actions is None:
            raise NoRouteError(
                f"no route between '{origin_stop_id}' and '{destination_stop_id}'"
            )
        departure = departure_at or utcnow()
        return self._build_plan(graph, origin_stop_id, destination_stop_id,
                                departure, actions)

    async def invalidate(self) -> None:
        """Drop the cached graph (e.g. after an explicit reload)."""
        async with self._lock:
            self._graph = None

    # -- graph construction ---------------------------------------------------

    async def _get_graph(self) -> NetworkGraph:
        async with self._session_factory() as session:
            latest = await DatasetVersionRepository(session).latest("gtfs_static")
            version = latest.version if latest else None
            async with self._lock:
                if self._graph is not None and self._graph.version == version:
                    return self._graph
                graph = await self._build_graph(session, version)
                self._graph = graph
                logger.info(
                    "journey graph built: version=%s, %d patterns, %d stops",
                    version, len(graph.patterns), len(graph.stop_names),
                )
                return graph

    async def _build_graph(
        self, session: AsyncSession, version: str | None
    ) -> NetworkGraph:
        stops = await StopRepository(session).list_all()
        stop_names = {s.stop_id: s.stop_name for s in stops}

        patterns = await self._build_patterns(session)
        patterns_at: dict[str, list[tuple[PatternKey, int]]] = {}
        for pattern in patterns.values():
            for index, pattern_stop in enumerate(pattern.stops):
                patterns_at.setdefault(pattern_stop.stop_id, []).append(
                    (pattern.key, index)
                )

        walk_edges = self._build_walk_edges(stops)
        return NetworkGraph(
            version=version,
            patterns=patterns,
            patterns_at=patterns_at,
            walk_edges=walk_edges,
            stop_names=stop_names,
        )

    async def _build_patterns(self, session: AsyncSession) -> dict[PatternKey, Pattern]:
        routes = {
            r.route_id: r
            for r in (await session.execute(select(Route))).scalars().all()
        }
        counts = (
            await session.execute(
                select(
                    Trip.route_id,
                    Trip.direction_id,
                    Trip.trip_id,
                    func.count(StopTime.stop_sequence).label("stop_count"),
                )
                .join(StopTime, StopTime.trip_id == Trip.trip_id)
                .group_by(Trip.route_id, Trip.direction_id, Trip.trip_id)
            )
        ).all()
        representative: dict[PatternKey, tuple[str, int]] = {}
        for route_id, direction_id, trip_id, stop_count in counts:
            key = (route_id, direction_id if direction_id is not None else 0)
            current = representative.get(key)
            if current is None or stop_count > current[1]:
                representative[key] = (trip_id, stop_count)

        trips_repo = TripRepository(session)
        patterns: dict[PatternKey, Pattern] = {}
        for key, (trip_id, _) in representative.items():
            trip = await trips_repo.get(trip_id)
            pairs = await trips_repo.stop_times_with_stops(trip_id)
            if trip is None or len(pairs) < 2:
                continue
            route = routes.get(trip.route_id)
            stops = tuple(
                PatternStop(
                    stop_id=stop.stop_id,
                    name=stop.stop_name,
                    arrival_seconds=stop_time.arrival_seconds,
                    departure_seconds=stop_time.departure_seconds,
                )
                for stop_time, stop in pairs
            )
            patterns[key] = Pattern(
                key=key,
                route_id=trip.route_id,
                direction_id=trip.direction_id,
                headsign=trip.trip_headsign or f"Towards {stops[-1].name}",
                route_short_name=route.route_short_name if route else None,
                route_long_name=route.route_long_name if route else None,
                route_color=route.route_color if route else None,
                stops=stops,
            )
        return patterns

    def _build_walk_edges(self, stops: Sequence[Stop]) -> dict[str, list[WalkEdge]]:
        params = self._params
        edges: dict[str, list[WalkEdge]] = {}
        for a, b in itertools.combinations(stops, 2):
            distance = haversine_m(a.stop_lat, a.stop_lon, b.stop_lat, b.stop_lon)
            same_complex = (
                a.parent_station is not None and a.parent_station == b.parent_station
            )
            if distance > params.walk_max_m and not same_complex:
                continue
            seconds = distance / params.walk_speed_mps + params.transfer_overhead_seconds
            edges.setdefault(a.stop_id, []).append(WalkEdge(b.stop_id, distance, seconds))
            edges.setdefault(b.stop_id, []).append(WalkEdge(a.stop_id, distance, seconds))
        return edges

    # -- search ---------------------------------------------------------------

    def _dijkstra(
        self, graph: NetworkGraph, origin: str, destination: str
    ) -> list[tuple] | None:
        """Cheapest action sequence from origin to destination, or None."""
        params = self._params
        start: _State = ("at", origin)
        target: _State = ("at", destination)
        best: dict[_State, float] = {start: 0.0}
        prev: dict[_State, tuple[_State, tuple]] = {}
        counter = itertools.count()
        queue: list[tuple[float, int, _State]] = [(0.0, next(counter), start)]

        while queue:
            cost, _, state = heapq.heappop(queue)
            if cost > best.get(state, float("inf")):
                continue
            if state == target:
                return self._reconstruct(prev, start, target)

            if state[0] == "at":
                stop_id = state[1]
                for key, index in graph.patterns_at.get(stop_id, []):
                    pattern = graph.patterns[key]
                    if index >= len(pattern.stops) - 1:
                        continue  # boarding at the terminus is pointless
                    self._relax(
                        best, prev, queue, counter, state,
                        ("on", key, index),
                        cost + params.board_penalty_seconds,
                        ("board", key, index),
                    )
                for edge in graph.walk_edges.get(stop_id, []):
                    self._relax(
                        best, prev, queue, counter, state,
                        ("at", edge.to_stop_id),
                        cost + edge.walk_seconds,
                        ("walk", stop_id, edge.to_stop_id, edge.distance_m,
                         edge.walk_seconds),
                    )
            else:
                _, key, index = state
                pattern = graph.patterns[key]
                here = pattern.stops[index]
                self._relax(
                    best, prev, queue, counter, state,
                    ("at", here.stop_id), cost, ("alight", key, index),
                )
                if index < len(pattern.stops) - 1:
                    nxt = pattern.stops[index + 1]
                    hop = max(
                        nxt.arrival_seconds - here.departure_seconds,
                        params.min_hop_seconds,
                    )
                    self._relax(
                        best, prev, queue, counter, state,
                        ("on", key, index + 1), cost + hop, ("ride", key, index + 1, hop),
                    )
        return None

    @staticmethod
    def _relax(
        best: dict[_State, float],
        prev: dict[_State, tuple[_State, tuple]],
        queue: list[tuple[float, int, _State]],
        counter: "itertools.count[int]",
        from_state: _State,
        to_state: _State,
        new_cost: float,
        action: tuple,
    ) -> None:
        if new_cost < best.get(to_state, float("inf")):
            best[to_state] = new_cost
            prev[to_state] = (from_state, action)
            heapq.heappush(queue, (new_cost, next(counter), to_state))

    @staticmethod
    def _reconstruct(
        prev: dict[_State, tuple[_State, tuple]], start: _State, target: _State
    ) -> list[tuple]:
        actions: list[tuple] = []
        state = target
        while state != start:
            state, action = prev[state]
            actions.append(action)
        actions.reverse()
        return actions

    # -- plan assembly ----------------------------------------------------------

    def _build_plan(
        self,
        graph: NetworkGraph,
        origin: str,
        destination: str,
        departure: datetime,
        actions: list[tuple],
    ) -> JourneyPlan:
        params = self._params
        legs: list[RideLeg | WalkLeg] = []
        walking_total = 0.0
        total_seconds = 0.0
        board_index: int | None = None
        board_key: PatternKey | None = None
        ride_seconds = 0.0

        for action in actions:
            verb = action[0]
            if verb == "walk":
                _, from_id, to_id, distance, seconds = action
                legs.append(
                    WalkLeg(
                        board=_stop(graph, from_id),
                        alight=_stop(graph, to_id),
                        distance_m=distance,
                        walk_seconds=seconds,
                    )
                )
                walking_total += distance
                total_seconds += seconds
            elif verb == "board":
                _, board_key, board_index = action
                ride_seconds = 0.0
                total_seconds += params.board_penalty_seconds
            elif verb == "ride":
                _, _, _, hop = action
                ride_seconds += hop
                total_seconds += hop
            elif verb == "alight":
                _, key, alight_index = action
                assert board_key == key and board_index is not None
                pattern = graph.patterns[key]
                stations = tuple(
                    JourneyStop(ps.stop_id, ps.name)
                    for ps in pattern.stops[board_index : alight_index + 1]
                )
                legs.append(
                    RideLeg(
                        board=stations[0],
                        alight=stations[-1],
                        route_id=pattern.route_id,
                        route_short_name=pattern.route_short_name,
                        route_long_name=pattern.route_long_name,
                        route_color=pattern.route_color,
                        direction_id=pattern.direction_id,
                        platform_hint=pattern.headsign,
                        stations=stations,
                        ride_seconds=ride_seconds,
                        wait_seconds=params.board_penalty_seconds,
                    )
                )
                board_key = None
                board_index = None

        ride_legs = [leg for leg in legs if isinstance(leg, RideLeg)]
        return JourneyPlan(
            origin=_stop(graph, origin),
            destination=_stop(graph, destination),
            departure_at=departure,
            expected_arrival_at=departure + timedelta(seconds=total_seconds),
            expected_travel_seconds=total_seconds,
            interchange_count=max(len(ride_legs) - 1, 0),
            walking_distance_m=walking_total,
            legs=tuple(legs),
        )


def _stop(graph: NetworkGraph, stop_id: str) -> JourneyStop:
    return JourneyStop(stop_id=stop_id, name=graph.stop_names.get(stop_id, stop_id))

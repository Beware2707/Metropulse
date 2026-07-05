"""Typed domain events published on the internal Redis event stream.

Events carry only JSON-native fields (strings, numbers, bools) so they
serialize losslessly and remain readable by non-Python consumers. The
registry maps wire names to classes for parsing; unknown event names parse
to None, which lets old consumers coexist with newer producers.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any, Union


@dataclass(frozen=True, slots=True)
class VehicleUpdated:
    """A vehicle appeared in or moved within the realtime feed."""

    vehicle_id: str
    trip_id: str | None
    route_id: str | None
    latitude: float
    longitude: float
    timestamp: str  # ISO-8601
    change: str  # added|moved


@dataclass(frozen=True, slots=True)
class VehicleRemoved:
    """A vehicle disappeared from the realtime feed."""

    vehicle_id: str
    timestamp: str


@dataclass(frozen=True, slots=True)
class EtaUpdated:
    """A fresh ETA was computed and cached for a vehicle."""

    vehicle_id: str
    trip_id: str
    next_stop_id: str | None
    eta_seconds: float | None
    delay_seconds: float | None
    timestamp: str


@dataclass(frozen=True, slots=True)
class JourneyStarted:
    """A user began tracking a journey."""

    journey_id: int
    user_id: str
    origin_stop_id: str
    destination_stop_id: str
    vehicle_id: str | None
    timestamp: str


@dataclass(frozen=True, slots=True)
class JourneyCompleted:
    """A journey ended (arrived, or ended after a missed stop)."""

    journey_id: int
    user_id: str
    destination_stop_id: str
    auto: bool
    missed: bool
    timestamp: str


@dataclass(frozen=True, slots=True)
class ServiceAlertCreated:
    """A service disruption alert was published."""

    alert_id: int
    severity: str
    route_id: str | None
    stop_id: str | None
    title: str
    timestamp: str


@dataclass(frozen=True, slots=True)
class DestinationReached:
    """A destination alert fired: the train is at/near the target station."""

    user_id: str
    vehicle_id: str
    stop_id: str
    alert_id: int
    timestamp: str


DomainEvent = Union[
    VehicleUpdated,
    VehicleRemoved,
    EtaUpdated,
    JourneyStarted,
    JourneyCompleted,
    ServiceAlertCreated,
    DestinationReached,
]

_EVENT_CLASSES: dict[str, type] = {
    cls.__name__: cls
    for cls in (
        VehicleUpdated,
        VehicleRemoved,
        EtaUpdated,
        JourneyStarted,
        JourneyCompleted,
        ServiceAlertCreated,
        DestinationReached,
    )
}


def event_name(event: DomainEvent) -> str:
    """The wire name of an event (its class name)."""
    return type(event).__name__


def to_payload(event: DomainEvent) -> dict[str, Any]:
    """Serialize an event to its wire envelope."""
    return {"event": event_name(event), "data": dataclasses.asdict(event)}


def parse_event(payload: dict[str, Any]) -> DomainEvent | None:
    """Parse a wire envelope back into a typed event.

    Returns None for unknown names or malformed data — consumers skip what
    they don't understand instead of crashing on newer producers.
    """
    cls = _EVENT_CLASSES.get(payload.get("event", ""))
    data = payload.get("data")
    if cls is None or not isinstance(data, dict):
        return None
    try:
        return cls(**data)  # type: ignore[no-any-return]
    except TypeError:
        return None

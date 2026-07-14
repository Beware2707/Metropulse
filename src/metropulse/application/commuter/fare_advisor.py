"""Fare advisor: what a user's recent trips cost, and what a smart card and
off-peak travel would have saved.

Every figure is an ESTIMATE from DMRC's published fare slabs (the same slabs
the app shows elsewhere, see app/lib/domain/fare.dart and
commute_impact._slab_fare), applied to the straight-line distance of each
stored journey. DMRC publishes no fare API, so this cannot be exact — the
response note says so.

Discounts modelled (DMRC published policy):
- Smart card: 10% off every fare vs a token/QR ticket.
- Off-peak: a further 10% off for journeys that START in an off-peak window
  (before 08:00, 12:00-16:59, or 21:00 onward).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.application.intelligence.commute_impact import _slab_fare
from metropulse.domain.geometry import haversine_m
from metropulse.infrastructure.db.commuter_repositories import JourneyRepository
from metropulse.infrastructure.db.repositories import StopRepository

_WINDOW_DAYS = 30
_CARD_DISCOUNT = 0.10
_OFFPEAK_EXTRA_DISCOUNT = 0.10

_NOTE = (
    "Estimates from DMRC published fares — actual savings depend on your card, "
    "the exact trips, and current fares."
)
_EMPTY_NOTE = (
    "Take a few trips with MetroPulse and we'll estimate what a smart card and "
    "off-peak travel could save you."
)


@dataclass(frozen=True, slots=True)
class FareAdvice:
    """A rolling-window fare summary for one user."""

    window_days: int
    trips: int
    estimated_spend_inr: int
    card_saving_inr: int
    offpeak_extra_saving_inr: int
    note: str


def _is_offpeak(moment: datetime) -> bool:
    """True when a boarding time falls in a DMRC off-peak window."""
    hour = moment.hour
    return hour < 8 or (12 <= hour < 17) or hour >= 21


class FareAdvisorService:
    """Estimates a user's fares and potential card/off-peak savings."""

    async def summary(
        self, session: AsyncSession, user_id: str, now: datetime
    ) -> FareAdvice:
        """Fare advice over the user's completed journeys in the last 30 days.

        Never raises: zero trips returns a valid empty summary with an
        explanatory note.
        """
        since = now - timedelta(days=_WINDOW_DAYS)
        journeys = await JourneyRepository(session).completed_since_for_user(
            user_id, since
        )
        stops = StopRepository(session)
        coord_cache: dict[str, tuple[float, float] | None] = {}

        async def coords(stop_id: str) -> tuple[float, float] | None:
            if stop_id not in coord_cache:
                stop = await stops.get(stop_id)
                coord_cache[stop_id] = (
                    None if stop is None else (stop.stop_lat, stop.stop_lon)
                )
            return coord_cache[stop_id]

        trips = 0
        spend = 0.0
        card_saving = 0.0
        offpeak_saving = 0.0
        for journey in journeys:
            origin = await coords(journey.origin_stop_id)
            destination = await coords(journey.destination_stop_id)
            if origin is None or destination is None:
                continue  # a station that no longer exists; skip, don't guess
            distance_km = haversine_m(origin[0], origin[1], destination[0], destination[1]) / 1000.0
            base_fare = _slab_fare(distance_km)  # token/QR price
            trips += 1
            spend += base_fare
            card_saving += base_fare * _CARD_DISCOUNT
            if _is_offpeak(journey.started_at):
                # Applied on the already-card-discounted fare, matching how
                # DMRC stacks the off-peak rebate on the smart-card fare.
                offpeak_saving += base_fare * (1 - _CARD_DISCOUNT) * _OFFPEAK_EXTRA_DISCOUNT

        return FareAdvice(
            window_days=_WINDOW_DAYS,
            trips=trips,
            estimated_spend_inr=round(spend),
            card_saving_inr=round(card_saving),
            offpeak_extra_saving_inr=round(offpeak_saving),
            note=_NOTE if trips else _EMPTY_NOTE,
        )

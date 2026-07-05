"""Place-role inference: learns which stations are "Home" and a regular
weekday destination from a user's own journey history.

Movement data alone can't distinguish "Office" from "College" — both just
look like a place the user travels to and from on a regular weekday
schedule. So this infers exactly two roles (see
:class:`~metropulse.domain.intelligence.PlaceRole`) and leaves the real-world
label ("Work", "College", or anything else) to the user. It never writes a
favourite on the user's behalf — callers should offer the result as a
suggestion the user can confirm or dismiss.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.domain.intelligence import InferredPlace, PlaceRole
from metropulse.infrastructure.db.commuter_repositories import JourneyRepository
from metropulse.infrastructure.db.repositories import StopRepository

_HISTORY_LIMIT = 200

# Deliberately NOT the same constant as CommutePredictionService's
# _MIN_SAMPLES_FOR_CONFIDENCE (8): that counts trips matching one specific
# (origin, destination, day-type) pattern, a narrow signal. This counts
# every completed/missed trip FROM a station regardless of destination or
# day-type — a much easier count to rack up — so it needs a higher bar
# before confidence reads as "certain", or the two confidence fields
# wouldn't mean comparable things across /commute-prediction and
# /inferred-places even though both are a 0..1 float.
_MIN_SAMPLES_FOR_CONFIDENCE = 20


class PlaceRoleInferenceService:
    """Infers Home / weekday-anchor place roles from journey history."""

    def __init__(self, *, lookback_days: float = 90.0, history_limit: int = _HISTORY_LIMIT) -> None:
        self._lookback = timedelta(days=lookback_days)
        self._history_limit = history_limit

    async def infer(
        self, session: AsyncSession, user_id: str, now: datetime
    ) -> list[InferredPlace]:
        """Places inferred for this user, most confident first.

        Returns an empty list when there isn't enough history yet — this is
        a suggestion feed, not a required resource, so "nothing to suggest"
        is a normal empty result rather than a 404. ``now`` is injectable for
        deterministic tests; production callers pass ``utcnow()``.
        """
        history = await JourneyRepository(session).history_for_user(user_id, self._history_limit)
        cutoff = now - self._lookback
        matching = [
            journey
            for journey in history
            if journey.status in ("completed", "missed") and _ensure_aware(journey.started_at) >= cutoff
        ]
        if not matching:
            return []

        stops = StopRepository(session)
        places: list[InferredPlace] = []

        home_stop_id, home_count = _most_common(j.origin_stop_id for j in matching)
        home = await stops.get(home_stop_id)
        if home is not None:
            places.append(
                InferredPlace(
                    stop_id=home_stop_id,
                    stop_name=home.stop_name,
                    role=PlaceRole.HOME,
                    confidence=_confidence(home_count),
                    sample_size=home_count,
                    rationale=f"the station you start from most often ({home_count} trips)",
                )
            )

            weekday_from_home = [
                j
                for j in matching
                if j.origin_stop_id == home_stop_id
                and j.destination_stop_id != home_stop_id
                and _ensure_aware(j.started_at).weekday() < 5
            ]
            if weekday_from_home:
                anchor_stop_id, anchor_count = _most_common(
                    j.destination_stop_id for j in weekday_from_home
                )
                anchor = await stops.get(anchor_stop_id)
                if anchor is not None:
                    places.append(
                        InferredPlace(
                            stop_id=anchor_stop_id,
                            stop_name=anchor.stop_name,
                            role=PlaceRole.WEEKDAY_ANCHOR,
                            confidence=_confidence(anchor_count),
                            sample_size=anchor_count,
                            rationale=(
                                f"where you most often head on weekdays from your "
                                f"home station ({anchor_count} trips)"
                            ),
                        )
                    )

        return places


def _most_common(values: Iterable[str]) -> tuple[str, int]:
    """The most frequent value and its count.

    On an exact tie, ``Counter.most_common`` resolves by first-insertion
    order — since callers always feed this from
    ``JourneyRepository.history_for_user`` (newest journey first), a tie
    is broken in favour of whichever station's most recent matching trip
    is more recent. This is deliberate (a tie should favour the fresher
    signal over an arbitrary/alphabetical pick) and is pinned by
    ``test_place_roles_breaks_a_tie_in_favour_of_the_more_recent_trip``.
    """
    counts = Counter(values)
    stop_id, count = counts.most_common(1)[0]
    return stop_id, count


def _confidence(sample_size: int) -> float:
    return round(min(1.0, sample_size / _MIN_SAMPLES_FOR_CONFIDENCE), 3)


def _ensure_aware(value: datetime) -> datetime:
    """Treat a naive datetime as UTC (see commute_predictor._ensure_aware)."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

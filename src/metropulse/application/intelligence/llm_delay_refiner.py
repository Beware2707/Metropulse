"""Optional LLM-assisted refinement of delay predictions — Metro Intelligence.

:class:`~metropulse.application.intelligence.delay_predictor.DelayPredictionService`
already computes an honest, real delay estimate purely from GTFS schedules
and completed-journey history — its own docstring names this exact module
as "the natural place to blend in live-observed delay... once available."
This module is that blend, provider-agnostic (Claude, OpenAI, Gemini, or
several tried in priority order — see ``infrastructure/llm_fallback.py``),
with two deliberate safety properties:

1. Completely inert without any LLM provider key configured. Every
   consumer of :class:`LlmEnhancedDelayEstimator` (the read-side decorator
   every ``DelayEstimator`` consumer actually depends on) transparently
   falls back to the plain historical estimate on every cache miss, and
   :meth:`LlmDelayRefinementScheduler.evaluate` returns immediately without
   touching the network or the database when no client is configured. No
   code path anywhere assumes this feature is active.
2. The refinement can only ever *nudge* the historical estimate within a
   bounded range (see :class:`LlmEnhancedDelayEstimator`) and never
   changes the reported ``confidence``, which always reflects the real
   sample size. A malformed or overconfident model response can shift a
   number; it can never invert or replace its statistical grounding, or
   claim more certainty than the data supports.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.application.ports import DelayEstimator, LlmClient
from metropulse.domain.entities import utcnow
from metropulse.domain.exceptions import LlmRequestError
from metropulse.domain.intelligence import DelayEstimate
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.commuter_repositories import (
    JourneyRepository,
    LlmDelayRefinementRepository,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You refine a transit delay estimate that was already computed from "
    "real historical data. You are given the honest statistical baseline: "
    "a median observed delay in seconds, how many real completed trips it "
    "is based on, the hour of day, and whether it is a weekday or weekend. "
    "Using only general reasoning about transit and commuting patterns -- "
    "never inventing a specific incident, a real-time observation, or any "
    "fact you were not given -- decide whether the estimate should be "
    "nudged and by how much, and write one short, plain sentence a rider "
    "would find useful explaining why. If you have no real reason to "
    "adjust the baseline, return it unchanged with a brief confirming "
    "sentence. Reply with ONLY a JSON object, no other text: "
    '{"adjusted_delay_seconds": <number>, "confidence": <0 to 1>, '
    '"explanation": "<one short sentence>"}'
)


@dataclass(frozen=True, slots=True)
class _RouteBucket:
    route_id: str
    direction_id: None
    hour_of_day: int
    day_type: str  # "weekday" | "weekend"


class LlmDelayRefinementScheduler:
    """Periodically refines delay predictions for routes with enough real history.

    Mirrors :class:`~metropulse.application.intelligence.proactive_scheduler.ProactiveCommuteSchedulerService`'s
    shape exactly: an ``evaluate_safe``/``evaluate`` pair, constructed once
    in ``cli.py``'s worker entry point and driven by APScheduler.
    """

    def __init__(
        self,
        delay_predictor: DelayEstimator,
        llm: LlmClient | None,
        session_factory: SessionFactory,
        *,
        min_sample_size: int = 10,
        max_buckets_per_cycle: int = 20,
        lookback_days: float = 60.0,
    ) -> None:
        self._delay_predictor = delay_predictor
        self._llm = llm
        self._session_factory = session_factory
        self._min_sample_size = min_sample_size
        self._max_buckets_per_cycle = max_buckets_per_cycle
        self._lookback = timedelta(days=lookback_days)

    async def evaluate_safe(self) -> int | None:
        """Scheduler entry point: never raises."""
        try:
            return await self.evaluate()
        except Exception:
            logger.exception("LLM delay refinement evaluation failed")
            return None

    async def evaluate(self, now: datetime | None = None) -> int:
        """One refinement cycle; returns the number of buckets refined.

        A no-op (returns 0 immediately, touches neither the database nor
        the network) when no LLM client is configured — i.e. no provider
        key is set. ``now`` is injectable for deterministic tests.
        """
        if self._llm is None:
            return 0
        now = now or utcnow()
        refined = 0
        async with self._session_factory() as session:
            async with session.begin():
                buckets = await self._active_buckets(session, now)
                refinements = LlmDelayRefinementRepository(session)
                for bucket in buckets:
                    baseline = await self._delay_predictor.estimate(
                        session,
                        bucket.route_id,
                        bucket.direction_id,
                        _sample_datetime(now, bucket.hour_of_day),
                    )
                    if baseline.sample_size < self._min_sample_size:
                        continue
                    try:
                        result = await self._llm.complete_json(
                            system=_SYSTEM_PROMPT,
                            user=(
                                f"Route: {bucket.route_id}\n"
                                f"Hour of day: {bucket.hour_of_day}:00\n"
                                f"Day type: {bucket.day_type}\n"
                                f"Historical median delay: "
                                f"{baseline.expected_delay_seconds:.0f} seconds\n"
                                f"Based on {baseline.sample_size} real completed trips."
                            ),
                        )
                        adjusted = float(result["adjusted_delay_seconds"])
                        confidence = float(result["confidence"])
                        explanation = str(result["explanation"])[:280]
                    except (LlmRequestError, KeyError, TypeError, ValueError) as exc:
                        logger.warning(
                            "LLM refinement skipped for %s hour=%d: %s",
                            bucket.route_id, bucket.hour_of_day, exc,
                        )
                        continue
                    await refinements.upsert(
                        route_id=bucket.route_id,
                        direction_id=bucket.direction_id,
                        hour_of_day=bucket.hour_of_day,
                        day_type=bucket.day_type,
                        adjusted_delay_seconds=adjusted,
                        confidence=max(0.0, min(1.0, confidence)),
                        explanation=explanation,
                        computed_at=now,
                    )
                    refined += 1
        if refined:
            logger.info("refined %d route delay bucket(s) via LLM", refined)
        return refined

    async def _active_buckets(
        self, session: AsyncSession, now: datetime
    ) -> list[_RouteBucket]:
        """Route/hour/day-type buckets with real recent history, busiest
        first and capped at ``max_buckets_per_cycle`` — a real, deliberate
        bound on API cost per cycle regardless of how many distinct
        buckets the network happens to have.

        ``direction_id`` is always None: :class:`DelayPredictionService`
        itself doesn't resolve direction from journey history today (its
        own docstring notes this), so refining per-direction would imply a
        resolution the underlying data doesn't actually support.
        """
        journeys = JourneyRepository(session)
        route_ids = await journeys.distinct_route_ids_with_history(now - self._lookback)
        counts: dict[tuple[str, int, str], int] = {}
        for route_id in route_ids:
            for journey in await journeys.completed_by_route(
                route_id, since=now - self._lookback, limit=200
            ):
                key = (
                    route_id,
                    journey.started_at.hour,
                    "weekend" if journey.started_at.weekday() >= 5 else "weekday",
                )
                counts[key] = counts.get(key, 0) + 1
        busiest = sorted(counts.items(), key=lambda kv: -kv[1])[: self._max_buckets_per_cycle]
        return [
            _RouteBucket(route_id=route_id, direction_id=None, hour_of_day=hour, day_type=day_type)
            for (route_id, hour, day_type), _count in busiest
        ]


def _sample_datetime(now: datetime, hour_of_day: int) -> datetime:
    """A datetime on today's date at the given hour — ``DelayEstimator.estimate``
    only actually reads the ``.hour`` component of its ``at`` parameter."""
    return now.replace(hour=hour_of_day, minute=0, second=0, microsecond=0)


class LlmEnhancedDelayEstimator:
    """Wraps a plain ``DelayEstimator`` with an optional cached LLM refinement.

    Always computes the real historical baseline first via ``inner``; only
    overlays a cached refinement when one exists and is still fresh (see
    ``max_age``). On any cache miss — including the case where no LLM
    provider is configured at all — this returns ``inner``'s estimate
    completely unchanged. Implements the
    :class:`~metropulse.application.ports.DelayEstimator` Protocol, so it's
    a drop-in replacement wherever ``DelayEstimator`` is already consumed
    (``SmartRecommendationService``, the intelligence API router) — no
    caller needs to know this layer exists.
    """

    def __init__(
        self,
        inner: DelayEstimator,
        *,
        max_age: timedelta,
        max_adjustment_fraction: float,
    ) -> None:
        self._inner = inner
        self._max_age = max_age
        self._max_adjustment_fraction = max_adjustment_fraction

    async def estimate(
        self,
        session: AsyncSession,
        route_id: str,
        direction_id: int | None,
        at: datetime,
    ) -> DelayEstimate:
        baseline = await self._inner.estimate(session, route_id, direction_id, at)
        if baseline.sample_size == 0:
            return baseline  # nothing real to refine

        day_type = "weekend" if at.weekday() >= 5 else "weekday"
        cached = await LlmDelayRefinementRepository(session).get(
            route_id, None, at.hour, day_type, fresher_than=utcnow() - self._max_age,
        )
        if cached is None:
            return baseline

        # Sanity bound: the AI adjustment can only ever nudge the honest
        # baseline within a fraction of its own magnitude (with a small
        # fixed floor so a near-zero baseline can still be nudged at all) —
        # never replace it wholesale, however confident the reply sounded.
        max_delta = max(60.0, abs(baseline.expected_delay_seconds) * self._max_adjustment_fraction)
        raw_delta = cached.adjusted_delay_seconds - baseline.expected_delay_seconds
        bounded_delta = max(-max_delta, min(max_delta, raw_delta))

        return DelayEstimate(
            route_id=baseline.route_id,
            direction_id=baseline.direction_id,
            hour_of_day=baseline.hour_of_day,
            expected_delay_seconds=round(baseline.expected_delay_seconds + bounded_delta, 1),
            # Confidence always reflects the real sample size, never the
            # model's own self-reported confidence in its explanation.
            confidence=baseline.confidence,
            sample_size=baseline.sample_size,
            source="ai_enhanced",
            explanation=cached.explanation,
        )

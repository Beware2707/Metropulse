"""Tests for the optional LLM-assisted delay-estimate refinement layer.

Covers each provider's raw HTTP client independently, the fallover wrapper
that tries them in priority order, the read-side decorator's
bounding/freshness/honesty guarantees, and the scheduler's gating (inert
without any client, resilient to malformed replies, capped API cost per
cycle). The decorator/scheduler tests below use a scripted fake client
throughout -- they exercise the provider-agnostic ``LlmClient`` seam, not
any one provider's wire format, since that's already covered by the
per-client tests.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest

from metropulse.application.intelligence.llm_delay_refiner import (
    LlmDelayRefinementScheduler,
    LlmEnhancedDelayEstimator,
)
from metropulse.application.intelligence.delay_predictor import DelayPredictionService
from metropulse.application.journey_planner import JourneyPlanner
from metropulse.domain.exceptions import LlmRequestError
from metropulse.domain.intelligence import DelayEstimate
from metropulse.infrastructure.claude.client import ClaudeClient
from metropulse.infrastructure.gemini.client import GeminiClient
from metropulse.infrastructure.llm_fallback import MultiProviderLlmClient
from metropulse.infrastructure.openai.client import OpenAiClient
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.commuter_models import Journey
from metropulse.infrastructure.db.commuter_repositories import (
    LlmDelayRefinementRepository,
)

IST = ZoneInfo("Asia/Kolkata")
MONDAYS = [datetime(2026, 7, day, 8, 10, 0, tzinfo=IST) for day in (6, 13, 20)]


async def _register_user(api_client: httpx.AsyncClient) -> str:
    response = await api_client.post(
        "/api/v1/users", json={"device_id": f"device-{id(api_client)}", "platform": "test"}
    )
    assert response.status_code == 201
    return response.json()["user_id"]


async def _seed_journey(
    session_factory: SessionFactory,
    user_id: str,
    *,
    origin: str,
    destination: str,
    route_id: str | None,
    started_at: datetime,
    duration_seconds: float,
) -> None:
    async with session_factory() as session:
        async with session.begin():
            session.add(
                Journey(
                    user_id=user_id,
                    origin_stop_id=origin,
                    destination_stop_id=destination,
                    route_id=route_id,
                    status="completed",
                    started_at=started_at,
                    ended_at=started_at + timedelta(seconds=duration_seconds),
                )
            )


# --- ClaudeClient -------------------------------------------------------------------


def _claude_client_with(handler: httpx.MockTransport) -> ClaudeClient:
    http = httpx.AsyncClient(transport=handler)
    return ClaudeClient(http, "test-key", model="claude-sonnet-5")


def _claude_reply(payload: dict) -> httpx.Response:
    return httpx.Response(
        200,
        json={"content": [{"type": "text", "text": json.dumps(payload)}]},
    )


async def test_claude_client_success_sends_correct_headers_and_parses_reply() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _claude_reply({"adjusted_delay_seconds": 90, "confidence": 0.6, "explanation": "ok"})

    result = await _claude_client_with(httpx.MockTransport(handler)).complete_json(
        system="sys", user="usr"
    )
    assert result == {"adjusted_delay_seconds": 90, "confidence": 0.6, "explanation": "ok"}
    assert seen[0].headers["x-api-key"] == "test-key"
    assert seen[0].headers["anthropic-version"] == "2023-06-01"


async def test_claude_client_transport_error_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    with pytest.raises(LlmRequestError, match="transport error"):
        await _claude_client_with(httpx.MockTransport(handler)).complete_json(system="s", user="u")


async def test_claude_client_non_2xx_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="server exploded")

    with pytest.raises(LlmRequestError, match="HTTP 500"):
        await _claude_client_with(httpx.MockTransport(handler)).complete_json(system="s", user="u")


async def test_claude_client_non_json_text_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"content": [{"type": "text", "text": "not json at all"}]})

    with pytest.raises(LlmRequestError, match="malformed"):
        await _claude_client_with(httpx.MockTransport(handler)).complete_json(system="s", user="u")


async def test_claude_client_json_array_reply_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"content": [{"type": "text", "text": "[1, 2, 3]"}]})

    with pytest.raises(LlmRequestError, match="not an object"):
        await _claude_client_with(httpx.MockTransport(handler)).complete_json(system="s", user="u")


# --- OpenAiClient -------------------------------------------------------------------


def _openai_client_with(handler: httpx.MockTransport) -> OpenAiClient:
    http = httpx.AsyncClient(transport=handler)
    return OpenAiClient(http, "test-key", model="gpt-5.5")


def _openai_reply(payload: dict) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": json.dumps(payload)}}]},
    )


async def test_openai_client_success_sends_correct_headers_and_parses_reply() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _openai_reply({"adjusted_delay_seconds": 90, "confidence": 0.6, "explanation": "ok"})

    result = await _openai_client_with(httpx.MockTransport(handler)).complete_json(
        system="sys", user="usr"
    )
    assert result == {"adjusted_delay_seconds": 90, "confidence": 0.6, "explanation": "ok"}
    assert seen[0].headers["authorization"] == "Bearer test-key"


async def test_openai_client_transport_error_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    with pytest.raises(LlmRequestError, match="transport error"):
        await _openai_client_with(httpx.MockTransport(handler)).complete_json(system="s", user="u")


async def test_openai_client_non_2xx_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="server exploded")

    with pytest.raises(LlmRequestError, match="HTTP 500"):
        await _openai_client_with(httpx.MockTransport(handler)).complete_json(system="s", user="u")


async def test_openai_client_non_json_text_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "not json at all"}}]})

    with pytest.raises(LlmRequestError, match="malformed"):
        await _openai_client_with(httpx.MockTransport(handler)).complete_json(system="s", user="u")


async def test_openai_client_json_array_reply_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "[1, 2, 3]"}}]})

    with pytest.raises(LlmRequestError, match="not an object"):
        await _openai_client_with(httpx.MockTransport(handler)).complete_json(system="s", user="u")


# --- GeminiClient -------------------------------------------------------------------


def _gemini_client_with(handler: httpx.MockTransport) -> GeminiClient:
    http = httpx.AsyncClient(transport=handler)
    return GeminiClient(http, "test-key", model="gemini-flash-latest")


def _gemini_reply(payload: dict) -> httpx.Response:
    return httpx.Response(
        200,
        json={"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]},
    )


async def test_gemini_client_success_sends_correct_headers_and_parses_reply() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _gemini_reply({"adjusted_delay_seconds": 90, "confidence": 0.6, "explanation": "ok"})

    result = await _gemini_client_with(httpx.MockTransport(handler)).complete_json(
        system="sys", user="usr"
    )
    assert result == {"adjusted_delay_seconds": 90, "confidence": 0.6, "explanation": "ok"}
    assert seen[0].headers["x-goog-api-key"] == "test-key"
    assert "gemini-flash-latest" in str(seen[0].url)


async def test_gemini_client_transport_error_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    with pytest.raises(LlmRequestError, match="transport error"):
        await _gemini_client_with(httpx.MockTransport(handler)).complete_json(system="s", user="u")


async def test_gemini_client_non_2xx_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="server exploded")

    with pytest.raises(LlmRequestError, match="HTTP 500"):
        await _gemini_client_with(httpx.MockTransport(handler)).complete_json(system="s", user="u")


async def test_gemini_client_non_json_text_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": "not json at all"}]}}]}
        )

    with pytest.raises(LlmRequestError, match="malformed"):
        await _gemini_client_with(httpx.MockTransport(handler)).complete_json(system="s", user="u")


async def test_gemini_client_json_array_reply_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": "[1, 2, 3]"}]}}]}
        )

    with pytest.raises(LlmRequestError, match="not an object"):
        await _gemini_client_with(httpx.MockTransport(handler)).complete_json(system="s", user="u")


# --- MultiProviderLlmClient -----------------------------------------------------------


@dataclass
class _ScriptedLlm:
    """A fake provider client: replies are either a dict (success) or an
    exception instance (simulating a failure), consumed in order."""

    replies: list

    def __post_init__(self) -> None:
        self._calls = 0

    async def complete_json(self, *, system: str, user: str, max_tokens: int = 512) -> dict:
        reply = self.replies[min(self._calls, len(self.replies) - 1)]
        self._calls += 1
        if isinstance(reply, Exception):
            raise reply
        return reply


async def test_multi_provider_uses_first_provider_when_it_succeeds() -> None:
    first = _ScriptedLlm([{"ok": "first"}])
    second = _ScriptedLlm([{"ok": "second"}])
    client = MultiProviderLlmClient([("first", first), ("second", second)])
    result = await client.complete_json(system="s", user="u")
    assert result == {"ok": "first"}
    assert second._calls == 0


async def test_multi_provider_falls_over_to_next_on_failure() -> None:
    first = _ScriptedLlm([LlmRequestError("first is down")])
    second = _ScriptedLlm([{"ok": "second"}])
    client = MultiProviderLlmClient([("first", first), ("second", second)])
    result = await client.complete_json(system="s", user="u")
    assert result == {"ok": "second"}


async def test_multi_provider_raises_last_error_when_all_fail() -> None:
    first = _ScriptedLlm([LlmRequestError("first is down")])
    second = _ScriptedLlm([LlmRequestError("second is down too")])
    client = MultiProviderLlmClient([("first", first), ("second", second)])
    with pytest.raises(LlmRequestError, match="second is down too"):
        await client.complete_json(system="s", user="u")


def test_multi_provider_rejects_empty_provider_list() -> None:
    with pytest.raises(ValueError, match="at least one provider"):
        MultiProviderLlmClient([])


# --- LlmEnhancedDelayEstimator ------------------------------------------------------


@dataclass
class _FakeInner:
    """A stub DelayEstimator returning a fixed baseline, for isolating the
    decorator's own blending/bounding logic from DelayPredictionService."""

    baseline: DelayEstimate

    async def estimate(self, session, route_id, direction_id, at) -> DelayEstimate:
        return self.baseline


def _baseline(delay: float = 100.0, sample_size: int = 20) -> DelayEstimate:
    return DelayEstimate(
        route_id="R1", direction_id=None, hour_of_day=8,
        expected_delay_seconds=delay, confidence=0.8, sample_size=sample_size,
    )


async def test_decorator_passes_through_baseline_on_cache_miss(
    loaded_session_factory: SessionFactory,
) -> None:
    decorator = LlmEnhancedDelayEstimator(
        _FakeInner(_baseline()), max_age=timedelta(hours=1), max_adjustment_fraction=0.5,
    )
    async with loaded_session_factory() as session:
        result = await decorator.estimate(session, "R1", None, MONDAYS[0])
    assert result.expected_delay_seconds == 100.0
    assert result.confidence == 0.8
    assert result.source == "history"
    assert result.explanation is None


async def test_decorator_passes_through_when_sample_size_is_zero(
    loaded_session_factory: SessionFactory,
) -> None:
    decorator = LlmEnhancedDelayEstimator(
        _FakeInner(_baseline(delay=0.0, sample_size=0)),
        max_age=timedelta(hours=1), max_adjustment_fraction=0.5,
    )
    async with loaded_session_factory() as session:
        result = await decorator.estimate(session, "R1", None, MONDAYS[0])
    assert result.source == "history"


async def test_decorator_applies_bounded_fresh_refinement(
    loaded_session_factory: SessionFactory,
) -> None:
    now = datetime.now(UTC)
    async with loaded_session_factory() as session:
        async with session.begin():
            await LlmDelayRefinementRepository(session).upsert(
                route_id="R1", direction_id=None, hour_of_day=8, day_type="weekday",
                adjusted_delay_seconds=110.0, confidence=0.99, explanation="slightly busier",
                computed_at=now,
            )

    decorator = LlmEnhancedDelayEstimator(
        _FakeInner(_baseline(delay=100.0)), max_age=timedelta(hours=1), max_adjustment_fraction=0.5,
    )
    async with loaded_session_factory() as session:
        result = await decorator.estimate(session, "R1", None, MONDAYS[0])

    assert result.expected_delay_seconds == 110.0  # within bound (10s adjustment, well under 50s cap)
    assert result.source == "ai_enhanced"
    assert result.explanation == "slightly busier"
    # Confidence must reflect the real sample size, never the model's own
    # self-reported (and here, implausibly high) confidence.
    assert result.confidence == 0.8


async def test_decorator_clamps_an_excessive_adjustment(
    loaded_session_factory: SessionFactory,
) -> None:
    now = datetime.now(UTC)
    async with loaded_session_factory() as session:
        async with session.begin():
            # Baseline is 100s; max_adjustment_fraction=0.5 means the bound
            # is max(60, 50) = 60s, but this claims a wild +10000s swing.
            await LlmDelayRefinementRepository(session).upsert(
                route_id="R1", direction_id=None, hour_of_day=8, day_type="weekday",
                adjusted_delay_seconds=10100.0, confidence=1.0, explanation="huge shift",
                computed_at=now,
            )

    decorator = LlmEnhancedDelayEstimator(
        _FakeInner(_baseline(delay=100.0)), max_age=timedelta(hours=1), max_adjustment_fraction=0.5,
    )
    async with loaded_session_factory() as session:
        result = await decorator.estimate(session, "R1", None, MONDAYS[0])

    assert result.expected_delay_seconds == 160.0  # 100 + the 60s cap, not +10000
    assert result.source == "ai_enhanced"


async def test_decorator_ignores_a_stale_refinement(
    loaded_session_factory: SessionFactory,
) -> None:
    stale = datetime.now(UTC) - timedelta(hours=5)
    async with loaded_session_factory() as session:
        async with session.begin():
            await LlmDelayRefinementRepository(session).upsert(
                route_id="R1", direction_id=None, hour_of_day=8, day_type="weekday",
                adjusted_delay_seconds=999.0, confidence=0.9, explanation="old",
                computed_at=stale,
            )

    decorator = LlmEnhancedDelayEstimator(
        _FakeInner(_baseline(delay=100.0)), max_age=timedelta(hours=1), max_adjustment_fraction=0.5,
    )
    async with loaded_session_factory() as session:
        result = await decorator.estimate(session, "R1", None, MONDAYS[0])

    assert result.expected_delay_seconds == 100.0
    assert result.source == "history"


# --- LlmDelayRefinementScheduler ----------------------------------------------------


async def test_scheduler_is_a_full_noop_without_an_llm_client(
    loaded_session_factory: SessionFactory,
) -> None:
    planner = JourneyPlanner(loaded_session_factory)
    scheduler = LlmDelayRefinementScheduler(
        DelayPredictionService(planner), llm=None, session_factory=loaded_session_factory,
    )
    assert await scheduler.evaluate() == 0

    # Confirms it never even touched the cache table.
    async with loaded_session_factory() as session:
        cached = await LlmDelayRefinementRepository(session).get(
            "R1", None, 8, "weekday", fresher_than=datetime.now(UTC) - timedelta(days=1),
        )
    assert cached is None


async def test_scheduler_refines_a_bucket_with_enough_history(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    user_id = await _register_user(api_client)
    for when in MONDAYS:
        await _seed_journey(
            loaded_session_factory, user_id,
            origin="S1", destination="S4", route_id="R1",
            started_at=when, duration_seconds=450.0 + 120.0,
        )

    planner = JourneyPlanner(loaded_session_factory)
    llm = _ScriptedLlm(
        [{"adjusted_delay_seconds": 130.0, "confidence": 0.7, "explanation": "steady delay"}]
    )
    scheduler = LlmDelayRefinementScheduler(
        DelayPredictionService(planner), llm=llm,
        session_factory=loaded_session_factory, min_sample_size=len(MONDAYS),
    )

    refined = await scheduler.evaluate(now=MONDAYS[-1])
    assert refined == 1

    async with loaded_session_factory() as session:
        cached = await LlmDelayRefinementRepository(session).get(
            "R1", None, MONDAYS[-1].hour, "weekday",
            fresher_than=MONDAYS[-1] - timedelta(minutes=1),
        )
    assert cached is not None
    assert cached.adjusted_delay_seconds == 130.0
    assert cached.explanation == "steady delay"


async def test_scheduler_skips_buckets_below_the_sample_threshold(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    user_id = await _register_user(api_client)
    await _seed_journey(
        loaded_session_factory, user_id,
        origin="S1", destination="S4", route_id="R1",
        started_at=MONDAYS[0], duration_seconds=450.0,
    )
    planner = JourneyPlanner(loaded_session_factory)
    llm = _ScriptedLlm([{"adjusted_delay_seconds": 1.0, "confidence": 0.5, "explanation": "x"}])
    scheduler = LlmDelayRefinementScheduler(
        DelayPredictionService(planner), llm=llm,
        session_factory=loaded_session_factory, min_sample_size=5,
    )
    assert await scheduler.evaluate(now=MONDAYS[0]) == 0


async def test_scheduler_survives_a_malformed_llm_reply(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    user_id = await _register_user(api_client)
    for when in MONDAYS:
        await _seed_journey(
            loaded_session_factory, user_id,
            origin="S1", destination="S4", route_id="R1",
            started_at=when, duration_seconds=450.0,
        )
    planner = JourneyPlanner(loaded_session_factory)
    llm = _ScriptedLlm([{"confidence": 0.5}])  # missing adjusted_delay_seconds/explanation
    scheduler = LlmDelayRefinementScheduler(
        DelayPredictionService(planner), llm=llm,
        session_factory=loaded_session_factory, min_sample_size=len(MONDAYS),
    )
    # Must not raise -- a malformed reply is skipped, not fatal to the cycle.
    assert await scheduler.evaluate(now=MONDAYS[-1]) == 0


async def test_scheduler_survives_an_llm_request_error(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    user_id = await _register_user(api_client)
    for when in MONDAYS:
        await _seed_journey(
            loaded_session_factory, user_id,
            origin="S1", destination="S4", route_id="R1",
            started_at=when, duration_seconds=450.0,
        )
    planner = JourneyPlanner(loaded_session_factory)
    llm = _ScriptedLlm([LlmRequestError("upstream is down")])
    scheduler = LlmDelayRefinementScheduler(
        DelayPredictionService(planner), llm=llm,
        session_factory=loaded_session_factory, min_sample_size=len(MONDAYS),
    )
    assert await scheduler.evaluate(now=MONDAYS[-1]) == 0


async def test_scheduler_caps_buckets_refined_per_cycle(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    user_id = await _register_user(api_client)
    # Two distinct routes, each with enough history to qualify.
    for route in ("R1", "B1"):
        for when in MONDAYS:
            await _seed_journey(
                loaded_session_factory, user_id,
                origin="S1", destination="S4", route_id=route,
                started_at=when, duration_seconds=450.0,
            )
    planner = JourneyPlanner(loaded_session_factory)
    llm = _ScriptedLlm(
        [{"adjusted_delay_seconds": 1.0, "confidence": 0.5, "explanation": "x"}]
    )
    scheduler = LlmDelayRefinementScheduler(
        DelayPredictionService(planner), llm=llm,
        session_factory=loaded_session_factory, min_sample_size=len(MONDAYS),
        max_buckets_per_cycle=1,
    )
    refined = await scheduler.evaluate(now=MONDAYS[-1])
    assert refined == 1

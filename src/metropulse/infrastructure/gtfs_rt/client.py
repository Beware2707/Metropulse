"""HTTP client for the Delhi OTD GTFS-Realtime VehiclePositions feed.

Every fetch retries with exponential backoff on transport errors and non-2xx
responses; all attempts are logged so feed instability is observable.

A circuit breaker sits above the retries: after N consecutive failed fetch
cycles the client fails fast for a cooldown window instead of hammering an
upstream that is clearly down (and burning our own poll budget on timeouts).
"""

from __future__ import annotations

import logging
import time

import httpx
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from metropulse.domain.exceptions import FeedFetchError

logger = logging.getLogger(__name__)


class GtfsRtClient:
    """Downloads the raw VehiclePositions protobuf payload."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        url: str,
        api_key: str,
        *,
        max_attempts: int = 3,
        backoff_base_seconds: float = 0.5,
        circuit_failure_threshold: int = 5,
        circuit_reset_seconds: float = 30.0,
    ) -> None:
        self._http = http
        self._url = url
        self._api_key = api_key
        self._max_attempts = max_attempts
        self._backoff_base = backoff_base_seconds
        self._circuit_threshold = circuit_failure_threshold
        self._circuit_reset = circuit_reset_seconds
        self._consecutive_failures = 0
        self._circuit_open_until: float | None = None

    @property
    def circuit_open(self) -> bool:
        """Whether the breaker is currently rejecting fetches."""
        return (
            self._circuit_open_until is not None
            and time.monotonic() < self._circuit_open_until
        )

    async def fetch_vehicle_positions(self) -> bytes:
        """Download the feed, retrying on failure.

        Raises :class:`FeedFetchError` once all attempts are exhausted, or
        immediately while the circuit breaker is open.
        """
        if self.circuit_open:
            raise FeedFetchError(
                f"circuit open after {self._consecutive_failures} consecutive "
                f"failed cycles; retrying upstream shortly"
            )
        retrying = AsyncRetrying(
            stop=stop_after_attempt(self._max_attempts),
            wait=wait_exponential(multiplier=self._backoff_base, max=5.0),
            retry=retry_if_exception_type(FeedFetchError),
            before_sleep=self._log_retry,
            reraise=True,
        )
        try:
            async for attempt in retrying:
                with attempt:
                    payload = await self._fetch_once()
                    self._consecutive_failures = 0
                    self._circuit_open_until = None
                    return payload
        except FeedFetchError:
            self._record_cycle_failure()
            raise
        raise FeedFetchError("retry loop exited without a result")  # pragma: no cover

    def _record_cycle_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._circuit_threshold:
            self._circuit_open_until = time.monotonic() + self._circuit_reset
            logger.error(
                "feed circuit opened after %d consecutive failed cycles; "
                "failing fast for %.0fs",
                self._consecutive_failures,
                self._circuit_reset,
            )

    async def _fetch_once(self) -> bytes:
        try:
            response = await self._http.get(self._url, params={"key": self._api_key})
        except httpx.HTTPError as exc:
            raise FeedFetchError(f"transport error fetching feed: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise FeedFetchError(f"feed returned HTTP {response.status_code}")
        if not response.content:
            raise FeedFetchError("feed returned an empty body")
        return response.content

    @staticmethod
    def _log_retry(retry_state: RetryCallState) -> None:
        outcome = retry_state.outcome
        error = outcome.exception() if outcome is not None else None
        logger.warning(
            "feed fetch attempt %d failed (%s); retrying",
            retry_state.attempt_number,
            error,
        )

"""HTTP client for the Delhi OTD GTFS-Realtime VehiclePositions feed.

Every fetch retries with exponential backoff on transport errors and non-2xx
responses; all attempts are logged so feed instability is observable.
"""

from __future__ import annotations

import logging

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
    ) -> None:
        self._http = http
        self._url = url
        self._api_key = api_key
        self._max_attempts = max_attempts
        self._backoff_base = backoff_base_seconds

    async def fetch_vehicle_positions(self) -> bytes:
        """Download the feed, retrying on failure.

        Raises :class:`FeedFetchError` once all attempts are exhausted.
        """
        retrying = AsyncRetrying(
            stop=stop_after_attempt(self._max_attempts),
            wait=wait_exponential(multiplier=self._backoff_base, max=5.0),
            retry=retry_if_exception_type(FeedFetchError),
            before_sleep=self._log_retry,
            reraise=True,
        )
        async for attempt in retrying:
            with attempt:
                return await self._fetch_once()
        raise FeedFetchError("retry loop exited without a result")  # pragma: no cover

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

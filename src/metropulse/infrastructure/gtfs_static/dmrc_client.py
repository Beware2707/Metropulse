"""HTTP client for DMRC's static GTFS feed endpoint.

``https://otd.delhi.gov.in/data/staticDMRC/`` requires an HTTP **POST** (a
plain GET/HEAD only returns the HTML form page, not the archive) carrying a
Django CSRF cookie/form-field pair. This is not real authentication -- it is
satisfied by generating one arbitrary 64-character hex token and sending the
SAME value as both the ``csrftoken`` cookie and the ``csrfmiddlewaretoken``
form field on a single request. A fresh token is generated per request; the
value only needs to match between the cookie and the form field on that one
request, so no cookie-jar continuity across requests is required.

Retry/timeout handling mirrors ``infrastructure/gtfs_rt/client.py``:
exponential backoff on transport errors and non-2xx responses, using the
same ``fetch_max_attempts``/``http_timeout_seconds`` settings (the timeout is
already applied to the shared ``httpx.AsyncClient`` built by
``wiring.build_http_client``).
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass

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


@dataclass(frozen=True, slots=True)
class StaticFeedResponse:
    """Raw result of a DMRC static feed POST."""

    content: bytes
    etag: str | None
    last_modified: str | None


class DmrcStaticFeedClient:
    """Downloads DMRC's static GTFS ZIP via its CSRF-protected POST endpoint."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        url: str,
        *,
        max_attempts: int = 3,
        backoff_base_seconds: float = 0.5,
    ) -> None:
        self._http = http
        self._url = url
        self._max_attempts = max_attempts
        self._backoff_base = backoff_base_seconds

    async def fetch(self) -> StaticFeedResponse:
        """Download the current static feed archive, retrying on failure.

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

    async def _fetch_once(self) -> StaticFeedResponse:
        # A fresh token per attempt is deliberate and simplest: the value
        # only has to match the cookie/form-field pair on this one request,
        # so there is nothing to gain from reusing it across attempts.
        #
        # The cookie is set via an explicit "Cookie" header rather than
        # httpx's per-request `cookies=` kwarg: `self._http` is a shared
        # client reused by several unrelated callers (see cli.py's
        # run_worker), and `cookies=` merges into -- and is deprecated in
        # favour of -- the client's persistent, instance-wide cookie jar.
        # A header avoids both the deprecation and leaking this token into
        # that shared jar for later, unrelated requests.
        token = secrets.token_hex(32)
        try:
            response = await self._http.post(
                self._url,
                data={"csrfmiddlewaretoken": token},
                headers={"Cookie": f"csrftoken={token}"},
            )
        except httpx.HTTPError as exc:
            raise FeedFetchError(f"transport error fetching static feed: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise FeedFetchError(f"static feed returned HTTP {response.status_code}")
        if not response.content:
            raise FeedFetchError("static feed returned an empty body")
        return StaticFeedResponse(
            content=response.content,
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
        )

    @staticmethod
    def _log_retry(retry_state: RetryCallState) -> None:
        outcome = retry_state.outcome
        error = outcome.exception() if outcome is not None else None
        logger.warning(
            "static feed fetch attempt %d failed (%s); retrying",
            retry_state.attempt_number,
            error,
        )

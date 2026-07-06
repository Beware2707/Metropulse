"""Minimal client for Anthropic's Messages API.

Implements the :class:`~metropulse.application.ports.LlmClient` Protocol —
used by ``application/intelligence/llm_delay_refiner.py`` to periodically
ask for a bounded, explained refinement of an already-computed historical
delay estimate, never to invent data on its own. Deliberately a thin
``httpx`` wrapper rather than the official SDK, so it shares this app's
connection pooling and timeout configuration (see
``wiring.build_http_client``) instead of managing its own, matching the
convention already established by :class:`~metropulse.infrastructure.gtfs_rt.client.GtfsRtClient`.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from metropulse.domain.exceptions import LlmRequestError

logger = logging.getLogger(__name__)

_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"


class ClaudeClient:
    """Sends one message, requiring a strict-JSON reply."""

    def __init__(self, http: httpx.AsyncClient, api_key: str, *, model: str) -> None:
        self._http = http
        self._api_key = api_key
        self._model = model

    async def complete_json(
        self, *, system: str, user: str, max_tokens: int = 512
    ) -> dict[str, Any]:
        """Returns the parsed JSON object from Claude's reply.

        Raises :class:`~metropulse.domain.exceptions.LlmRequestError` on any
        transport failure, non-2xx response, or a reply that isn't valid
        JSON.
        """
        try:
            response = await self._http.post(
                _MESSAGES_URL,
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": _API_VERSION,
                    "content-type": "application/json",
                },
                json={
                    "model": self._model,
                    "max_tokens": max_tokens,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
            )
        except httpx.HTTPError as exc:
            raise LlmRequestError(f"transport error calling Claude: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise LlmRequestError(
                f"Claude API returned HTTP {response.status_code}: {response.text[:200]}"
            )
        try:
            data = response.json()
            text = data["content"][0]["text"]
            parsed = json.loads(text)
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise LlmRequestError(f"malformed Claude response: {exc}") from exc
        if not isinstance(parsed, dict):
            raise LlmRequestError(f"Claude reply was valid JSON but not an object: {parsed!r}")
        return parsed

"""Minimal client for OpenAI's Chat Completions API.

Implements the :class:`~metropulse.application.ports.LlmClient` Protocol —
the same seam :class:`~metropulse.infrastructure.claude.client.ClaudeClient`
implements, so either (or both, tried in priority order — see
``infrastructure/llm_fallback.py``) can back
``application/intelligence/llm_delay_refiner.py`` without a code change.
Uses the JSON-object response mode (``response_format: {"type":
"json_object"}``), not the newer strict JSON-Schema mode — this refiner
only ever needs a small, simple, self-describing object, not a rigid
contract the API itself enforces.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from metropulse.domain.exceptions import LlmRequestError

logger = logging.getLogger(__name__)

_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"


class OpenAiClient:
    """Sends one message, requiring a strict-JSON reply."""

    def __init__(self, http: httpx.AsyncClient, api_key: str, *, model: str) -> None:
        self._http = http
        self._api_key = api_key
        self._model = model

    async def complete_json(
        self, *, system: str, user: str, max_tokens: int = 512
    ) -> dict[str, Any]:
        """Returns the parsed JSON object from OpenAI's reply.

        Raises :class:`~metropulse.domain.exceptions.LlmRequestError` on any
        transport failure, non-2xx response, or a reply that isn't valid
        JSON.
        """
        try:
            response = await self._http.post(
                _CHAT_COMPLETIONS_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "content-type": "application/json",
                },
                json={
                    "model": self._model,
                    "max_tokens": max_tokens,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
            )
        except httpx.HTTPError as exc:
            raise LlmRequestError(f"transport error calling OpenAI: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise LlmRequestError(
                f"OpenAI API returned HTTP {response.status_code}: {response.text[:200]}"
            )
        try:
            data = response.json()
            text = data["choices"][0]["message"]["content"]
            parsed = json.loads(text)
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise LlmRequestError(f"malformed OpenAI response: {exc}") from exc
        if not isinstance(parsed, dict):
            raise LlmRequestError(f"OpenAI reply was valid JSON but not an object: {parsed!r}")
        return parsed

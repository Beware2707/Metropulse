"""Minimal client for Google's Gemini ``generateContent`` REST API.

Implements the :class:`~metropulse.application.ports.LlmClient` Protocol —
the same seam :class:`~metropulse.infrastructure.claude.client.ClaudeClient`
and :class:`~metropulse.infrastructure.openai.client.OpenAiClient`
implement. The system prompt is folded into the single user turn (rather
than a separate ``system_instruction`` field) to keep the request shape as
simple and stable as possible across API revisions.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from metropulse.domain.exceptions import LlmRequestError

logger = logging.getLogger(__name__)

_GENERATE_CONTENT_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiClient:
    """Sends one message, requiring a strict-JSON reply."""

    def __init__(self, http: httpx.AsyncClient, api_key: str, *, model: str) -> None:
        self._http = http
        self._api_key = api_key
        self._model = model

    async def complete_json(
        self, *, system: str, user: str, max_tokens: int = 512
    ) -> dict[str, Any]:
        """Returns the parsed JSON object from Gemini's reply.

        Raises :class:`~metropulse.domain.exceptions.LlmRequestError` on any
        transport failure, non-2xx response, or a reply that isn't valid
        JSON.
        """
        try:
            response = await self._http.post(
                _GENERATE_CONTENT_URL.format(model=self._model),
                headers={
                    "x-goog-api-key": self._api_key,
                    "content-type": "application/json",
                },
                json={
                    "contents": [{"role": "user", "parts": [{"text": f"{system}\n\n{user}"}]}],
                    "generationConfig": {
                        "maxOutputTokens": max_tokens,
                        "responseMimeType": "application/json",
                    },
                },
            )
        except httpx.HTTPError as exc:
            raise LlmRequestError(f"transport error calling Gemini: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise LlmRequestError(
                f"Gemini API returned HTTP {response.status_code}: {response.text[:200]}"
            )
        try:
            data = response.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(text)
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise LlmRequestError(f"malformed Gemini response: {exc}") from exc
        if not isinstance(parsed, dict):
            raise LlmRequestError(f"Gemini reply was valid JSON but not an object: {parsed!r}")
        return parsed

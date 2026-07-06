"""Tries configured LLM providers in priority order.

Wraps however many of Claude/OpenAI/Gemini are actually configured (see
``wiring.build_llm_client``) behind a single :class:`~metropulse.application.ports.LlmClient`.
A single provider outage, rate-limit, or key misconfiguration falls through
to the next one rather than stopping delay refinement entirely, as long as
at least one configured provider is currently working.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from metropulse.application.ports import LlmClient
from metropulse.domain.exceptions import LlmRequestError

logger = logging.getLogger(__name__)


class MultiProviderLlmClient:
    """Attempts each ``(name, client)`` pair in order; the first successful
    reply wins. Raises the last provider's error only if every one fails."""

    def __init__(self, providers: Sequence[tuple[str, LlmClient]]) -> None:
        if not providers:
            raise ValueError("MultiProviderLlmClient needs at least one provider")
        self._providers = list(providers)

    async def complete_json(
        self, *, system: str, user: str, max_tokens: int = 512
    ) -> dict[str, Any]:
        last_error: LlmRequestError | None = None
        for name, client in self._providers:
            try:
                return await client.complete_json(system=system, user=user, max_tokens=max_tokens)
            except LlmRequestError as exc:
                logger.warning("LLM provider %r failed, trying next: %s", name, exc)
                last_error = exc
        assert last_error is not None  # unreachable: __init__ guarantees len >= 1
        raise last_error

"""Claude as a translation provider.

The only place in the system that talks to an AI vendor, and it may do exactly
one thing: return the same segments in another language.  It never sees a
number it could change — the service masks periods, figures, product codes and
the department vocabulary *before* the request leaves the process, and puts
them back afterwards (ADR-0008).

The key lives in the backend environment (``CSM_ANTHROPIC_API_KEY``) and is
never sent to the browser (ADR-0009).  With no key configured the provider is
not registered at all and the system keeps using the null provider, so nothing
breaks and nothing is silently sent anywhere.
"""

from __future__ import annotations

import json
import logging

from .provider import (
    SYSTEM_PROMPT,
    TranslationRequest,
    TranslationResult,
    parse_segments as _parse,
)

logger = logging.getLogger(__name__)

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
TIMEOUT_SECONDS = 60.0

class AnthropicProvider:
    """Translates through the Anthropic Messages API."""

    name = "anthropic"
    #: a starting plan is measured in requests per minute, so the service paces
    #: itself rather than discovering the limit through 429s (ADR-0042)
    requests_per_minute = 30
    max_batch = 60

    def __init__(self, api_key: str, model: str, *, url: str = API_URL) -> None:
        self._api_key = api_key
        self._model = model
        self._url = url

    # -- the seam ----------------------------------------------------------- #
    @property
    def model(self) -> str:
        """Which model answers — reported by ``/api/translation/status``."""
        return self._model

    def translate(self, request: TranslationRequest) -> TranslationResult:
        if not request.segments:
            return TranslationResult(segments=[], provider=self.name, model=self._model)

        import httpx  # imported here so the app runs without the dependency

        system = SYSTEM_PROMPT.format(
            source=request.source_language, target=request.target_language
        )
        payload = {
            "model": self._model,
            "max_tokens": 4096,
            "system": system,
            "messages": [
                {
                    "role": "user",
                    "content": json.dumps(request.segments, ensure_ascii=False),
                }
            ],
        }
        response = httpx.post(
            self._url,
            json=payload,
            timeout=TIMEOUT_SECONDS,
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": API_VERSION,
                "content-type": "application/json",
            },
        )
        response.raise_for_status()
        body = response.json()
        text = "".join(
            part.get("text", "") for part in body.get("content", []) if part.get("type") == "text"
        )
        segments = _parse(text, len(request.segments), request.segments)
        return TranslationResult(
            segments=segments,
            provider=self.name,
            model=body.get("model") or self._model,
            meta={"usage": body.get("usage", {}), "stopReason": body.get("stop_reason")},
        )


def register_from_settings() -> str:
    """Kept for callers that predate the shared registration (ADR-0040)."""
    from .provider import configure_from_settings

    return configure_from_settings()

"""Any engine that speaks the OpenAI chat API.

That is `gpt-4o` and its family, but also a gateway in front of several models,
a self-hosted server, or Ollama's own compatibility endpoint.  One provider
covers all of them because the shape of the request is the same; what differs
is the base URL, the key and the model name.

Two things this engine declares about itself, which the service then obeys
(ADR-0042):

* ``requests_per_minute`` — a hosted plan may allow as few as three.  The
  service paces itself to that number rather than discovering it through 429s.
* ``max_batch`` — how many segments go in one request.  Under a tight quota the
  batch size is what decides whether a report translates at all, so it is
  generous by default and the settings can lower it.

The model is multimodal, and this seam is text-only on purpose: a translation
of a report's words has no business sending its photographs anywhere.  When
images do need describing, that is a different capability with its own decision
to make, not a quiet extension of this one.
"""

from __future__ import annotations

import json
import logging

from .provider import SYSTEM_PROMPT, TranslationRequest, TranslationResult, parse_segments

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 120.0

#: what a modest hosted plan allows.  Wrong for a generous one — set
#: ``CSM_TRANSLATION_RPM`` to raise it; the service reads that first.
DEFAULT_RPM = 3.0


class OpenAICompatibleProvider:
    """Translates through an OpenAI-compatible chat endpoint."""

    name = "openai"

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        url: str = "https://api.openai.com/v1",
        requests_per_minute: float = DEFAULT_RPM,
        max_batch: int = 60,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._url = url.rstrip("/")
        self.requests_per_minute = requests_per_minute
        self.max_batch = max_batch

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
            # a translation is not a place for sampling, and the cache assumes
            # the same input gives the same output
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(request.segments, ensure_ascii=False)},
            ],
        }

        # the exception travels: the service decides what is worth retrying and
        # how long to wait, because only it knows the quota (ADR-0042)
        response = httpx.post(
            f"{self._url}/chat/completions",
            json=payload,
            timeout=TIMEOUT_SECONDS,
            headers={
                "authorization": f"Bearer {self._api_key}",
                "content-type": "application/json",
            },
        )
        response.raise_for_status()
        body = response.json()

        choices = body.get("choices") or []
        text = (choices[0].get("message", {}).get("content", "") if choices else "") or ""
        return TranslationResult(
            segments=parse_segments(text, len(request.segments), request.segments),
            provider=self.name,
            model=body.get("model") or self._model,
            meta={"usage": body.get("usage", {})},
        )

"""A model served locally by Ollama, as a translation provider.

Same seam as any other engine, and one real difference: the text never leaves
the machine.  For a quality report that mixes a supplier's name with a lot
number, that is often the deciding factor.

The service around it still does the work that keeps a translation honest —
masking the protected terms and the data tokens on the way out, restoring them
on the way back, and discarding any answer whose numbers moved (ADR-0035).  A
local model is not trusted more than a remote one; it is simply closer.
"""

from __future__ import annotations

import json
import logging

from .provider import SYSTEM_PROMPT, TranslationRequest, TranslationResult, parse_segments

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 180.0


class OllamaProvider:
    """Translates through a model running on this machine."""

    name = "ollama"

    def __init__(self, url: str, model: str) -> None:
        self._url = url.rstrip("/")
        self._model = model

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
            "stream": False,
            # a translation is not a place for sampling: the same input should
            # give the same output, and the cache assumes it
            "options": {"temperature": 0},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(request.segments, ensure_ascii=False)},
            ],
        }

        try:
            response = httpx.post(
                f"{self._url}/api/chat", json=payload, timeout=TIMEOUT_SECONDS
            )
            response.raise_for_status()
            body = response.json()
        except Exception:  # a local engine that is down must not lose the text
            logger.exception("ollama did not answer; keeping the source text")
            return TranslationResult(
                segments=list(request.segments),
                provider=self.name,
                model=self._model,
                meta={"failed": True},
            )

        text = (body.get("message") or {}).get("content", "")
        return TranslationResult(
            segments=parse_segments(text, len(request.segments), request.segments),
            provider=self.name,
            model=body.get("model") or self._model,
            meta={
                "evalCount": body.get("eval_count"),
                "totalDurationMs": round((body.get("total_duration") or 0) / 1e6),
            },
        )

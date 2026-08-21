"""The provider seam.

Nothing in the system talks to an AI engine directly.  A provider receives
plain text segments and returns plain text segments; document structure,
caching and protected terms are handled by the service around it.

Three implementations exist: the null provider (returns the source), Claude
through the Anthropic API, and any model served locally by Ollama.  Adding a
fourth means implementing :class:`TranslationProvider` and registering it — no
other file changes.

The *question* is asked the same way by all of them, so the prompt and the
answer parser live here rather than in any one provider.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@dataclass
class TranslationRequest:
    """A batch of linguistic segments to translate."""

    segments: list[str]
    source_language: str
    target_language: str
    #: never translated: PPM, W32, SEC, TNP, product codes, numbers…
    protected_terms: tuple[str, ...] = ()
    context: str | None = None


@dataclass
class TranslationResult:
    segments: list[str]
    provider: str
    model: str | None = None
    meta: dict = field(default_factory=dict)


@runtime_checkable
class TranslationProvider(Protocol):
    """Contract every provider implements."""

    name: str

    def translate(self, request: TranslationRequest) -> TranslationResult:  # pragma: no cover
        ...


class NullProvider:
    """Returns the source untouched.

    Used until a real provider is configured, and in tests: it makes the whole
    translation path exercisable without a network call or an API key.
    """

    name = "null"

    def translate(self, request: TranslationRequest) -> TranslationResult:
        return TranslationResult(
            segments=list(request.segments),
            provider=self.name,
            model=None,
            meta={"passthrough": True},
        )


#: what every engine is asked, word for word
SYSTEM_PROMPT = """\
You are a translation engine inside a quality-reporting system. You translate \
short strings taken from spreadsheets and reports.

Rules, in order of importance:
1. Translate the meaning of each segment from {source} into {target}. Nothing else.
2. Never change, add, remove or reformat any number, date, percentage or code.
3. Text between section signs, like §A§, is a placeholder for protected \
content. Reproduce every placeholder exactly, in the same order, unchanged.
4. If a segment has nothing to translate (a code, a number, an abbreviation), \
return it byte for byte as it came.
5. Keep the register short and factual, as in a technical report. Do not \
explain, comment, expand or summarise.

Return ONLY a JSON array of strings, the same length as the input array, in the \
same order. No prose, no markdown, no keys."""


def parse_segments(text: str, expected: int, fallback: list[str]) -> list[str]:
    """Read an engine's answer, or keep the original.

    A malformed answer must never corrupt the content: the source text is
    returned untouched and the caller sees the original, not an invention.
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        stripped = stripped.split("\n", 1)[-1] if "\n" in stripped else stripped
    # some local models wrap the array in an object: {"translations": [...]}
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        start, end = stripped.find("["), stripped.rfind("]")
        if start == -1 or end <= start:
            logger.warning("translation answer was not JSON; keeping the source text")
            return list(fallback)
        try:
            parsed = json.loads(stripped[start : end + 1])
        except json.JSONDecodeError:
            logger.warning("translation answer was not JSON; keeping the source text")
            return list(fallback)

    if isinstance(parsed, dict):
        parsed = next(
            (value for value in parsed.values() if isinstance(value, list)), None
        )
    if not isinstance(parsed, list) or len(parsed) != expected:
        logger.warning(
            "translation answer had %s segment(s), expected %d; keeping the source text",
            len(parsed) if isinstance(parsed, list) else "no",
            expected,
        )
        return list(fallback)
    return [str(item) for item in parsed]


_PROVIDERS: dict[str, TranslationProvider] = {"null": NullProvider()}


def register_provider(provider: TranslationProvider) -> None:
    _PROVIDERS[provider.name] = provider


def get_provider(name: str | None = None) -> TranslationProvider:
    from app.core.config import get_settings

    key = name or get_settings().translation_provider
    provider = _PROVIDERS.get(key)
    if provider is None:  # unknown provider must not break the app
        return _PROVIDERS["null"]
    return provider


def available_providers() -> tuple[str, ...]:
    return tuple(sorted(_PROVIDERS))


def configure_from_settings() -> str:
    """Register the engine the environment asks for, and say which one it is.

    Nothing is registered without explicit configuration, and a provider that
    cannot be built leaves the null provider in place: the product degrades to
    "not translated", never to "translated wrongly".
    """
    from app.core.config import get_settings

    settings = get_settings()
    wanted = settings.translation_provider

    if wanted == "anthropic":
        from .anthropic_provider import AnthropicProvider

        if settings.anthropic_api_key:
            register_provider(
                AnthropicProvider(settings.anthropic_api_key, settings.translation_model)
            )
            logger.info("translation provider: anthropic (%s)", settings.translation_model)
            return "anthropic"
        logger.warning(
            "translation provider 'anthropic' requested without CSM_ANTHROPIC_API_KEY — "
            "falling back to the null provider (text is returned untranslated)"
        )

    elif wanted == "ollama":
        from .ollama_provider import OllamaProvider

        register_provider(OllamaProvider(settings.ollama_url, settings.ollama_model))
        logger.info(
            "translation provider: ollama (%s at %s)", settings.ollama_model, settings.ollama_url
        )
        return "ollama"

    return get_provider().name

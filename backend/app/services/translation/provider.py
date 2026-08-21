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
    """Contract every provider implements.

    Two optional attributes declare what the engine can take, and the service
    around it obeys them (ADR-0042):

    * ``requests_per_minute`` — a hosted model may allow as few as three; the
      service paces itself to that and never relies on the engine to refuse;
    * ``max_batch`` — how many segments fit in one request.  Fewer, larger
      requests is the only way to translate a report inside a tight quota.
    """

    name: str

    def translate(self, request: TranslationRequest) -> TranslationResult:  # pragma: no cover
        ...


class NullProvider:
    """Returns the source untouched.

    Used until a real provider is configured, and in tests: it makes the whole
    translation path exercisable without a network call or an API key.
    """

    name = "null"
    requests_per_minute = 0  # nothing leaves the process; no pacing needed
    max_batch = 10_000

    def translate(self, request: TranslationRequest) -> TranslationResult:
        return TranslationResult(
            segments=list(request.segments),
            provider=self.name,
            model=None,
            meta={"passthrough": True},
        )


#: what every engine is asked, word for word.  One prompt for every engine:
#: a local model and a remote one must be asked the same question, or the
#: translation would depend on which was configured (ADR-0040).
SYSTEM_PROMPT = """\
You translate the text of a weekly quality report, written by an engineer for \
an executive meeting. The segments are short: a column heading, a finding, an \
action taken. They come from a factory floor, so they are often typed quickly.

Do exactly two things to each segment:

1. TRANSLATE it from {source} into {target}, keeping the meaning the author \
   intended, not a word-for-word rendering.
2. FIX what was mistyped along the way — spelling, accents, capitalisation and \
   spacing — so the result reads as a careful person would have written it in \
   {target}. Correct the language, never the facts: if the author says a \
   supplier was audited, the translation says the supplier was audited.

Hold to these rules, in this order of importance:

* Never change, add, remove or reformat any number, date, percentage or code.
* Text between section signs, like §A§, is a placeholder standing in for \
  protected content. Reproduce every placeholder exactly as it appears, in the \
  same order. Do not translate it, space it differently or drop it.
* A segment that is a code, an abbreviation or a bare number has nothing to \
  translate: return it byte for byte.
* Keep the register of a technical report: short, factual, no politeness \
  formulas. Do not explain, comment, expand, summarise or add a word the \
  author did not write.
* Keep the segment's own shape — a heading stays a heading, a sentence stays a \
  sentence, a fragment stays a fragment.

Return ONLY a JSON array of strings, the same length as the input array, in the \
same order. No prose, no markdown, no keys, no trailing commentary."""


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

    elif wanted == "openai":
        from .openai_provider import OpenAICompatibleProvider

        if settings.openai_api_key:
            register_provider(
                OpenAICompatibleProvider(
                    settings.openai_api_key,
                    settings.openai_model,
                    url=settings.openai_url,
                    max_batch=settings.translation_max_batch,
                )
            )
            logger.info(
                "translation provider: openai (%s at %s)",
                settings.openai_model,
                settings.openai_url,
            )
            return "openai"
        logger.warning(
            "translation provider 'openai' requested without CSM_OPENAI_API_KEY — "
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

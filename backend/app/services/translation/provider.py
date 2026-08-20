"""The provider seam.

Nothing in the system talks to an AI vendor directly.  A provider receives
plain text segments and returns plain text segments; document structure,
caching and protected terms are handled by the service around it.

Sprint 0 ships the interface and a null provider.  A real provider (Claude via
the Anthropic API) is added in the translation sprint by implementing
:class:`TranslationProvider` and registering it — no other file changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


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

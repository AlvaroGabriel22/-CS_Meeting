"""Wire contract for the translation layer.

The response is an *overlay*: pairs of original and translated text.  The
snapshot itself is never modified, so a client can show either side at any
moment and the original is always available (ADR-0035).
"""

from __future__ import annotations

from .common import CamelModel


class TranslationStatusOut(CamelModel):
    """What the backend can translate with, right now."""

    provider: str
    model: str | None = None
    languages: list[str] = []
    default_language: str = "en"
    #: False when no provider is configured — text comes back untranslated
    active: bool = False

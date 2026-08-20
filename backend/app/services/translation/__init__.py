"""Translation: provider seam, document rules and the cache-first service."""

from .documents import content_hash, extract_segments, apply_segments, plain_text
from .provider import (
    NullProvider,
    TranslationProvider,
    TranslationRequest,
    TranslationResult,
    available_providers,
    get_provider,
    register_provider,
)
from .service import TranslationOutcome, TranslationService

__all__ = [
    "NullProvider",
    "TranslationOutcome",
    "TranslationProvider",
    "TranslationRequest",
    "TranslationResult",
    "TranslationService",
    "apply_segments",
    "available_providers",
    "content_hash",
    "extract_segments",
    "get_provider",
    "plain_text",
    "register_provider",
]

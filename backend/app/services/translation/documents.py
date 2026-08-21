"""Rich-document handling for translation.

An Issue Report cell is a TipTap/ProseMirror tree: text, marks, hard breaks and
images live together.  Translation must replace *only* the text nodes:

    [text] [image] [text]   ->   [translated] [same image] [translated]

These functions are pure — no database, no provider — so the rule is testable
on its own.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any

#: nodes whose content is never sent anywhere
OPAQUE_NODE_TYPES = {"image", "hardBreak", "horizontalRule"}

_NUMBER_RE = re.compile(r"^[\d\s.,:%/+-]+$")

#: patterns that must survive translation untouched even though they sit inside
#: a sentence.  Week labels are a *pattern* on purpose: W32 becomes W33 next
#: week, so they can never be a static list.
#: what may sit next to a token without being part of it.  Deliberately ASCII:
#: Korean glues a particle straight onto the number — ``12/08에`` — and Python's
#: ``\w`` counts 에 as a word character, so a ``(?!\w)`` boundary would fail to
#: see the date at all and the guard would reject a perfectly good translation.
_EDGE = r"[0-9A-Za-z_]"

PROTECTED_PATTERNS: tuple[re.Pattern[str], ...] = (
    # a date is one datum, not two numbers with a slash between them: masking it
    # whole lets it move as a unit, which is what every language does with it
    re.compile(rf"(?<!{_EDGE})\d{{1,4}}[/-]\d{{1,2}}(?:[/-]\d{{2,4}})?(?!{_EDGE})"),
    re.compile(rf"(?<!{_EDGE})(?:W|WK|S)\s?\d{{1,2}}(?!{_EDGE})", re.IGNORECASE),
    re.compile(rf"(?<!{_EDGE})\d+(?:[.,]\d+)*\s?%?(?!{_EDGE})"),        # 3,000 / 13.4%
    re.compile(rf"(?<!{_EDGE})[A-Z]{{2,}}[-_]?\d{{2,}}(?!{_EDGE})"),      # product codes
)


def extract_segments(doc: dict[str, Any]) -> list[str]:
    """Every translatable text node, in document order."""
    segments: list[str] = []

    def walk(node: dict[str, Any]) -> None:
        if node.get("type") in OPAQUE_NODE_TYPES:
            return
        if node.get("type") == "text":
            segments.append(node.get("text", ""))
            return
        for child in node.get("content", []) or []:
            walk(child)

    walk(doc)
    return segments


def apply_segments(doc: dict[str, Any], segments: list[str]) -> dict[str, Any]:
    """Rebuild the document with translated text, structure untouched."""
    result = deepcopy(doc)
    queue = list(segments)

    def walk(node: dict[str, Any]) -> None:
        if node.get("type") in OPAQUE_NODE_TYPES:
            return
        if node.get("type") == "text":
            if queue:
                node["text"] = queue.pop(0)
            return
        for child in node.get("content", []) or []:
            walk(child)

    walk(result)
    return result


def is_translatable(segment: str) -> bool:
    """Pure numbers, codes and whitespace are not language."""
    text = segment.strip()
    if not text:
        return False
    return not _NUMBER_RE.match(text)


def content_hash(doc: dict[str, Any]) -> str:
    """Stable hash of the *linguistic* content of a document.

    Editing an image or a style does not invalidate a translation; editing the
    words does.
    """
    payload = json.dumps(extract_segments(doc), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def text_hash(text: str) -> str:
    """Cache key of a single string.

    Equal by construction to :func:`content_hash` of a document whose only text
    node is ``text``, so a title and a paragraph share one cache and one rule.
    """
    payload = json.dumps([text], ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def data_tokens(text: str) -> list[str]:
    """Every piece of a string that is data rather than language.

    Numbers, week labels and product codes — the things a translation may
    never touch.  Used as a *check* after the fact: what went out and what came
    back must carry the same data tokens (ADR-0035).
    """
    tokens: list[str] = []
    for pattern in PROTECTED_PATTERNS:
        tokens.extend(match.group(0) for match in pattern.finditer(text))
    return sorted(token.strip() for token in tokens)


def preserves_data(original: str, translated: str, terms: tuple[str, ...] = ()) -> bool:
    """True when a translation changed only the language.

    Every data token of the source must survive verbatim: nothing dropped,
    nothing rounded, no decimal separator localised.  A translation that fails
    that is discarded by the caller and the original text is kept.

    A token the translation *adds* is allowed, because some languages spell a
    word with a digit in it — Korean writes August as ``8월`` and "third party"
    as ``제3자``.  Refusing those would be refusing the translation, and the
    figures they sit next to are already masked and restored verbatim, so an
    extra digit cannot be a changed number (ADR-0035).
    """
    from collections import Counter

    source_tokens = Counter(data_tokens(original))
    if source_tokens - Counter(data_tokens(translated)):
        return False
    for term in terms:
        if not term:
            continue
        pattern = re.compile(rf"(?<!{_EDGE})" + re.escape(term) + rf"(?!{_EDGE})")
        if len(pattern.findall(original)) != len(pattern.findall(translated)):
            return False
    return True


def mask_protected(segment: str, terms: tuple[str, ...]) -> tuple[str, dict[str, str]]:
    """Replace protected content with placeholders before sending it out.

    Two sources: the configured vocabulary (``PPM``, ``SEC``, ``TECPLAM``…) and
    :data:`PROTECTED_PATTERNS` (week labels, numbers, product codes).  What
    comes back is put in place again by :func:`unmask_protected`, so the AI can
    only ever change the language, never the data.
    """
    mapping: dict[str, str] = {}
    masked = segment
    counter = 0

    def placeholder() -> str:
        # letters only: a digit inside a placeholder would be matched again by
        # the number pattern, and the masking would never terminate
        nonlocal counter
        name = chr(ord("A") + counter % 26) * (1 + counter // 26)
        counter += 1
        return f"\u00a7{name}\u00a7"

    for term in sorted((term for term in terms if term), key=len, reverse=True):
        pattern = re.compile(rf"(?<!{_EDGE})" + re.escape(term) + rf"(?!{_EDGE})")
        if pattern.search(masked):
            token = placeholder()
            masked = pattern.sub(token, masked)
            mapping[token] = term

    def _replace(match: "re.Match[str]") -> str:
        token = placeholder()
        mapping[token] = match.group(0)
        return token

    for pattern in PROTECTED_PATTERNS:
        masked = pattern.sub(_replace, masked)

    return masked, mapping


def unmask_protected(segment: str, mapping: dict[str, str]) -> str:
    for placeholder, term in mapping.items():
        segment = segment.replace(placeholder, term)
    return segment


def plain_text(doc: dict[str, Any], separator: str = " ") -> str:
    return separator.join(segment for segment in extract_segments(doc) if segment.strip())

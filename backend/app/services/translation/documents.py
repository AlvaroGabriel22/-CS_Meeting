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
PROTECTED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?<!\w)(?:W|WK|S)\s?\d{1,2}(?!\w)", re.IGNORECASE),  # W32, WK32, S28
    re.compile(r"(?<!\w)\d+(?:[.,]\d+)*\s?%?(?!\w)"),                 # 3,000 / 13.4%
    re.compile(r"(?<!\w)[A-Z]{2,}[-_]?\d{2,}(?!\w)"),                  # product codes
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
        pattern = re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)")
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

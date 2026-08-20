"""Discovery of the time dimension from header tokens.

The single most important rule of this system: **periods are discovered, never
hardcoded**.  ``W32`` becoming ``W33`` next week, a new ``Sep`` column showing
up, a year disappearing — all of that is data, and this module is what turns
those strings into structured :class:`~app.excel.model.Period` objects.

Recognised (case-insensitive, en / pt-BR / ko):

* years — ``2026``, ``CY26``, ``FY2026``, ``'26``, ``2026년``
* quarters — ``Q3``, ``3Q``, ``T3``, ``3분기``
* months — ``Aug``, ``August``, ``Ago``, ``Agosto``, ``8월``, ``Aug-26``, ``2026-08``
* weeks — ``W32``, ``WK32``, ``W-32``, ``Week 32``, ``S32``, ``Semana 32``, ``32주``
* series (not periods) — ``Target``, ``Result``, ``Plan``, ``Meta``, ``실적`` …
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Sequence

from .model import Period, PeriodKind

# --------------------------------------------------------------------------- #
# Vocabulary
# --------------------------------------------------------------------------- #
_MONTHS: dict[str, int] = {}


def _register_months() -> None:
    tables = [
        # english
        "january february march april may june july august september october november december",
        "jan feb mar apr may jun jul aug sep oct nov dec",
        "jan feb mar apr may jun jul aug sept oct nov dec",
        # portuguese
        "janeiro fevereiro marco abril maio junho julho agosto setembro outubro novembro dezembro",
        "jan fev mar abr mai jun jul ago set out nov dez",
    ]
    for table in tables:
        for i, name in enumerate(table.split(), start=1):
            _MONTHS.setdefault(name, i)
    for i in range(1, 13):
        _MONTHS[f"{i}월"] = i  # korean


_register_months()

_SERIES_TOKENS = {
    "target": "Target",
    "goal": "Target",
    "meta": "Target",
    "alvo": "Target",
    "목표": "Target",
    "result": "Result",
    "actual": "Result",
    "real": "Result",
    "resultado": "Result",
    "실적": "Result",
    "plan": "Plan",
    "plano": "Plan",
    "forecast": "Forecast",
    "previsao": "Forecast",
    "average": "Average",
    "media": "Average",
    "avg": "Average",
    "total": "Total",
    "acc": "Accumulated",
    "accum": "Accumulated",
    "accumulated": "Accumulated",
    "acumulado": "Accumulated",
    "ytd": "YTD",
    "mtd": "MTD",
}

_YEAR_RE = re.compile(r"^(?:cy|fy)?\s*'?((?:19|20)\d{2})\s*(?:년)?$")
_SHORT_YEAR_RE = re.compile(r"^(?:cy|fy)\s*'?(\d{2})$|^'(\d{2})$")
_WEEK_RE = re.compile(r"^(?:w|wk|week|sem|semana|s)[\s\-_./]*(\d{1,2})$")
_WEEK_KO_RE = re.compile(r"^(\d{1,2})\s*주\s*(?:차)?$")
_QUARTER_RE = re.compile(r"^(?:q|t|tri|trim|trimestre|quarter)[\s\-_./]*([1-4])$")
_QUARTER_SUFFIX_RE = re.compile(r"^([1-4])\s*(?:q|분기)$")
_MONTH_YEAR_RE = re.compile(r"^([a-z]+)[\s\-_./']*((?:19|20)?\d{2})$")
_YEAR_MONTH_RE = re.compile(r"^((?:19|20)\d{2})[\s\-_./](\d{1,2})$")
_ISO_DATE_RE = re.compile(r"^((?:19|20)\d{2})-(\d{1,2})-(\d{1,2})")


@dataclass(frozen=True)
class PeriodFacets:
    """Partial period information extracted from a single token."""

    kind: PeriodKind
    year: int | None = None
    quarter: int | None = None
    month: int | None = None
    week: int | None = None
    day: int | None = None


#: granularity ranking — a finer token wins when several rows describe a column
_GRANULARITY = {
    PeriodKind.YEAR: 1,
    PeriodKind.QUARTER: 2,
    PeriodKind.MONTH: 3,
    PeriodKind.WEEK: 4,
    PeriodKind.DAY: 5,
    PeriodKind.UNKNOWN: 0,
}


def normalize(token: str) -> str:
    """Lowercase, strip accents and punctuation noise (keeps korean intact)."""
    text = str(token).strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    # NFD splits Hangul syllables into jamo — recompose so korean tokens match
    text = unicodedata.normalize("NFC", text)
    return re.sub(r"\s+", " ", text).strip(" .:;*")


def match_series(token: str) -> str | None:
    """Return the canonical series name for a token such as ``Target``."""
    return _SERIES_TOKENS.get(normalize(token))


def match_token(token: str) -> PeriodFacets | None:
    """Extract period facets from one header token, or ``None``."""
    text = normalize(token)
    if not text:
        return None

    if m := _ISO_DATE_RE.match(text):
        return PeriodFacets(PeriodKind.DAY, year=int(m[1]), month=int(m[2]), day=int(m[3]))
    if m := _YEAR_RE.match(text):
        return PeriodFacets(PeriodKind.YEAR, year=int(m[1]))
    if m := _SHORT_YEAR_RE.match(text):
        return PeriodFacets(PeriodKind.YEAR, year=2000 + int(m[1] or m[2]))
    if m := _WEEK_RE.match(text):
        week = int(m[1])
        if 1 <= week <= 53:
            return PeriodFacets(PeriodKind.WEEK, week=week)
    if m := _WEEK_KO_RE.match(text):
        return PeriodFacets(PeriodKind.WEEK, week=int(m[1]))
    if m := _QUARTER_RE.match(text) or _QUARTER_SUFFIX_RE.match(text):
        return PeriodFacets(PeriodKind.QUARTER, quarter=int(m[1]))
    if text in _MONTHS:
        return PeriodFacets(PeriodKind.MONTH, month=_MONTHS[text])
    if m := _YEAR_MONTH_RE.match(text):
        month = int(m[2])
        if 1 <= month <= 12:
            return PeriodFacets(PeriodKind.MONTH, year=int(m[1]), month=month)
    if m := _MONTH_YEAR_RE.match(text):
        name, year = m[1], m[2]
        if name in _MONTHS:
            year_i = int(year) if len(year) == 4 else 2000 + int(year)
            return PeriodFacets(PeriodKind.MONTH, year=year_i, month=_MONTHS[name])
    return None


# --------------------------------------------------------------------------- #
# Row-level context
# --------------------------------------------------------------------------- #
def row_period_kind(values: Sequence[str]) -> PeriodKind | None:
    """Dominant period kind of a header row, used to read bare numbers.

    A row that already says ``W30 W31 W32`` gives meaning to a bare ``33``
    written in the next cell; a row of month names gives meaning to a bare ``8``.
    Without such context bare integers are *not* treated as periods.
    """
    counts: dict[PeriodKind, int] = {}
    for value in values:
        facets = match_token(value)
        if facets:
            counts[facets.kind] = counts.get(facets.kind, 0) + 1
    if not counts:
        return None
    kind, _count = max(counts.items(), key=lambda kv: (kv[1], _GRANULARITY[kv[0]]))
    return kind


def match_token_in_row(token: str, row_kind: PeriodKind | None) -> PeriodFacets | None:
    """Like :func:`match_token`, but resolves bare integers using row context."""
    facets = match_token(token)
    if facets:
        return facets
    text = normalize(token)
    if not row_kind or not re.fullmatch(r"\d{1,2}", text):
        return None
    number = int(text)
    if row_kind is PeriodKind.MONTH and 1 <= number <= 12:
        return PeriodFacets(PeriodKind.MONTH, month=number)
    if row_kind is PeriodKind.WEEK and 1 <= number <= 53:
        return PeriodFacets(PeriodKind.WEEK, week=number)
    if row_kind is PeriodKind.QUARTER and 1 <= number <= 4:
        return PeriodFacets(PeriodKind.QUARTER, quarter=number)
    return None


# --------------------------------------------------------------------------- #
# Column-level combination
# --------------------------------------------------------------------------- #
def build_period(
    header_path: Sequence[str],
    row_kinds: Sequence[PeriodKind | None] | None = None,
) -> tuple[Period | None, str | None]:
    """Combine a column's header tokens into ``(period, series)``.

    ``header_path`` is the top-down list of header cells above one column, e.g.
    ``("2026", "Aug", "W32", "Target")`` -> week 32 of Aug/2026, series Target.
    """
    kinds = list(row_kinds or [None] * len(header_path))
    kinds += [None] * (len(header_path) - len(kinds))

    year = quarter = month = week = day = None
    finest = PeriodKind.UNKNOWN
    labels: list[str] = []
    series: str | None = None

    for token, row_kind in zip(header_path, kinds):
        token = str(token).strip()
        if not token:
            continue
        facets = match_token_in_row(token, row_kind)
        if facets is None:
            if name := match_series(token):
                series = name
            continue
        labels.append(token)
        year = facets.year if facets.year is not None else year
        quarter = facets.quarter if facets.quarter is not None else quarter
        month = facets.month if facets.month is not None else month
        week = facets.week if facets.week is not None else week
        day = facets.day if facets.day is not None else day
        if _GRANULARITY[facets.kind] > _GRANULARITY[finest]:
            finest = facets.kind

    if finest is PeriodKind.UNKNOWN:
        return None, series
    return (
        Period(
            kind=finest,
            label=labels[-1] if labels else "",
            year=year,
            quarter=quarter,
            month=month,
            week=week,
            day=day,
            tokens=tuple(t for t in header_path if str(t).strip()),
        ),
        series,
    )


def looks_like_period_sequence(values: Iterable[str], minimum: int = 2) -> bool:
    """True when a sequence of labels is mostly made of period tokens.

    Used to detect transposed tables (periods running down the first column).
    """
    values = [v for v in values if str(v).strip()]
    if len(values) < minimum:
        return False
    row_kind = row_period_kind(values)
    hits = sum(1 for v in values if match_token_in_row(v, row_kind))
    return hits >= max(minimum, int(0.6 * len(values)))

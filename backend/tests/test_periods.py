"""Period discovery — the rule that must never regress."""

from __future__ import annotations

import pytest

from app.excel.model import PeriodKind
from app.excel.periods import (
    build_period,
    looks_like_period_sequence,
    match_series,
    match_token,
    row_period_kind,
)


@pytest.mark.parametrize(
    "token,kind,value",
    [
        ("W30", PeriodKind.WEEK, 30),
        ("W32", PeriodKind.WEEK, 32),
        ("W33", PeriodKind.WEEK, 33),
        ("W34", PeriodKind.WEEK, 34),
        ("w-34", PeriodKind.WEEK, 34),
        ("WK34", PeriodKind.WEEK, 34),
        ("Week 34", PeriodKind.WEEK, 34),
        ("Semana 34", PeriodKind.WEEK, 34),
        ("S28", PeriodKind.WEEK, 28),
        ("34주", PeriodKind.WEEK, 34),
    ],
)
def test_weeks_are_read_not_hardcoded(token: str, kind: PeriodKind, value: int) -> None:
    facets = match_token(token)
    assert facets is not None and facets.kind is kind and facets.week == value


@pytest.mark.parametrize(
    "token,month",
    [
        ("Jan", 1),
        ("January", 1),
        ("Ago", 8),
        ("Agosto", 8),
        ("Aug", 8),
        ("August", 8),
        ("Set", 9),
        ("Sep", 9),
        ("Dez", 12),
        ("8월", 8),
        ("Março", 3),
    ],
)
def test_months_in_three_languages(token: str, month: int) -> None:
    facets = match_token(token)
    assert facets is not None and facets.month == month


@pytest.mark.parametrize(
    "token,year",
    [("2025", 2025), ("2026", 2026), ("CY26", 2026), ("FY2026", 2026), ("'26", 2026)],
)
def test_years(token: str, year: int) -> None:
    facets = match_token(token)
    assert facets is not None and facets.year == year


@pytest.mark.parametrize(
    "token,quarter", [("Q3", "3Q"), ("3Q", "3Q"), ("T3", "3Q"), ("3분기", "3Q"), ("Q4", "4Q")]
)
def test_quarters_are_canonical_labels(token: str, quarter: str) -> None:
    """However the file spells it, the model says "3Q"."""
    facets = match_token(token)
    assert facets is not None and facets.quarter == quarter


def test_non_periods_are_rejected() -> None:
    for token in ("PPM", "SEC", "TNP", "TECPLAM", "Module A", "Defect Qty", "", "-"):
        assert match_token(token) is None


def test_series_labels_are_not_periods() -> None:
    assert match_series("Target") == "Target"
    assert match_series("실적") == "Result"
    assert match_token("Target") is None


def test_header_path_combines_year_month_week_and_series() -> None:
    period, series = build_period(["2026", "Aug", "W32", "Target"])
    assert period is not None
    assert (period.kind, period.year, period.month, period.week) == (PeriodKind.WEEK, 2026, 8, 32)
    assert series == "Target"
    assert period.sort_key == "2026-W32"


def test_bare_numbers_need_row_context() -> None:
    # a lonely "8" is not a month
    assert build_period(["8"])[0] is None
    # ...but it is when its header row is made of months
    kind = row_period_kind(["Jun", "Jul", "8"])
    period, _ = build_period(["8"], [kind])
    assert period is not None and period.month == 8


def test_week_shift_changes_nothing_structurally() -> None:
    """W32 -> W33 -> W34 is data, so the same call keeps working."""
    for week in (32, 33, 34):
        period, _ = build_period(["2026", f"W{week}"])
        assert period is not None and period.week == week
        assert period.sort_key == f"2026-W{week:02d}"


def test_period_sequence_detection_for_transposed_tables() -> None:
    assert looks_like_period_sequence(["W30", "W31", "W32", "W33"])
    assert not looks_like_period_sequence(["SEC", "TNP", "TECPLAM"])


# --------------------------------------------------------------------------- #
# Canonical quarters
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "month,quarter",
    [
        (1, "1Q"), (2, "1Q"), (3, "1Q"),
        (4, "2Q"), (5, "2Q"), (6, "2Q"),
        (7, "3Q"), (8, "3Q"), (9, "3Q"),
        (10, "4Q"), (11, "4Q"), (12, "4Q"),
    ],
)
def test_every_month_maps_to_its_quarter(month: int, quarter: str) -> None:
    from app.excel.model import QUARTER_OF_MONTH, Period, PeriodKind
    from app.excel.period_engine import enrich

    assert QUARTER_OF_MONTH[month] == quarter
    resolved = enrich(Period(PeriodKind.MONTH, "x", month=month), 2026)
    assert resolved.quarter == quarter
    assert resolved.quarter_number == int(quarter[0])


def test_quarter_label_helpers_round_trip() -> None:
    from app.excel.model import quarter_label, quarter_number

    assert [quarter_label(n) for n in (1, 2, 3, 4)] == ["1Q", "2Q", "3Q", "4Q"]
    assert quarter_label("3Q") == "3Q" and quarter_label(0) is None and quarter_label(None) is None
    assert [quarter_number(label) for label in ("1Q", "4Q")] == [1, 4]
    assert quarter_number(None) is None


def test_quarter_covers_its_months_and_sorts_deterministically() -> None:
    from app.excel.model import Period, PeriodKind

    q4 = Period(PeriodKind.QUARTER, "4Q", year=2026, quarter="4Q")
    november = Period(PeriodKind.MONTH, "Nov", year=2026, month=11, quarter="4Q")
    january = Period(PeriodKind.MONTH, "Jan", year=2026, month=1, quarter="1Q")

    assert q4.months == (10, 11, 12)
    assert q4.contains(november) and not q4.contains(january)
    assert q4.sort_key == "2026-Q4"  # ordinal stays in the key, label stays canonical
    assert Period(PeriodKind.QUARTER, "1Q", year=2026, quarter="1Q").sort_key == "2026-Q1"


def test_quarter_reaches_the_wire_as_a_label() -> None:
    from app.excel.model import Period, PeriodKind

    payload = Period(PeriodKind.QUARTER, "3Q", year=2026, quarter="3Q").to_dict()
    assert payload["quarter"] == "3Q"
    assert payload["quarterNumber"] == 3
    assert payload["sortKey"] == "2026-Q3"

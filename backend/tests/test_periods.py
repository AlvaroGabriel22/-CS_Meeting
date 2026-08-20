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


@pytest.mark.parametrize("token,quarter", [("Q3", 3), ("3Q", 3), ("T3", 3), ("3분기", 3)])
def test_quarters(token: str, quarter: int) -> None:
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

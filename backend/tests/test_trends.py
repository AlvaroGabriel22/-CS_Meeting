"""Trend analysis: deterministic, granularity-aware, polarity-aware."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.excel import parse_file
from app.services import analytics as A
from app.services import trends as T
from app.services.interpretation import from_normalized


def _points(values, kind="month", labels=None):
    labels = labels or [f"M{index}" for index in range(len(values))]
    return [
        {
            "period": {"kind": kind, "label": label, "year": 2026, "month": index + 1,
                       "quarter": None, "week": None, "day": None, "sortKey": f"2026-M{index + 1:02d}",
                       "yearSource": "explicit", "tokens": [], "quarterNumber": None},
            "value": value,
        }
        for index, (label, value) in enumerate(zip(labels, values))
    ]


# --------------------------------------------------------------------------- #
# 9-12. Classification
# --------------------------------------------------------------------------- #
def test_09_three_rising_periods() -> None:
    trend = T.classify(_points([100.0, 120.0, 150.0]))
    assert trend.classification == "rising"
    assert trend.points == 3 and trend.consecutive == 2
    assert trend.change == 50.0 and trend.change_percent == pytest.approx(50.0)


def test_10_three_falling_periods() -> None:
    trend = T.classify(_points([150.0, 120.0, 100.0]))
    assert trend.classification == "falling"
    assert trend.change == -50.0


def test_11_oscillating_values_are_volatile() -> None:
    trend = T.classify(_points([100.0, 150.0, 110.0]))
    assert trend.classification == "volatile"
    assert trend.quality == "unknown"  # a volatile series is not judged


def test_11_a_series_that_barely_moves_is_stable() -> None:
    # every step under the 2% tolerance
    trend = T.classify(_points([100.0, 101.0, 100.5]))
    assert trend.classification == "stable"
    assert trend.quality == "stable"


def test_12_fewer_than_three_readings_is_insufficient_data() -> None:
    assert T.classify(_points([100.0, 120.0])).classification == "insufficient_data"
    assert T.classify([]).classification == "insufficient_data"
    trend = T.classify(_points([100.0, 120.0]))
    assert trend.quality == "unknown" and trend.points == 2


def test_missing_values_do_not_count_as_readings() -> None:
    points = _points([100.0, 120.0, 150.0])
    points[1]["value"] = None
    trend = T.classify(points)
    assert trend.points == 2 and trend.classification == "insufficient_data"


# --------------------------------------------------------------------------- #
# Comparability: granularities are never mixed
# --------------------------------------------------------------------------- #
def test_only_periods_of_the_same_kind_are_compared() -> None:
    months = _points([100.0, 120.0, 150.0], kind="month", labels=["Aug", "Sep", "Oct"])
    quarters = _points([300.0, 900.0], kind="quarter", labels=["2Q", "3Q"])
    trend = T.classify(months + quarters)
    assert trend.granularity == "month"
    assert trend.period_labels == ["Aug", "Sep", "Oct"]
    assert trend.points == 3


def test_the_finest_granularity_with_enough_readings_wins() -> None:
    """Two months cannot be read as a trend; three quarters can."""
    months = _points([10.0, 11.0], kind="month", labels=["Nov", "Dec"])
    quarters = _points([100.0, 120.0, 150.0], kind="quarter", labels=["1Q", "2Q", "3Q"])
    trend = T.classify(months + quarters)
    assert trend.granularity == "quarter" and trend.points == 3


def test_months_are_preferred_once_they_have_enough_readings(iqc_evolution) -> None:
    """Fixture C shows four quarters and three months: the months are tracked."""
    months = _points([10.0, 12.0, 15.0], kind="month", labels=["Aug", "Sep", "Oct"])
    quarters = _points([100.0, 120.0, 150.0, 180.0], kind="quarter",
                       labels=["1Q", "2Q", "3Q", "4Q"])
    trend = T.classify(quarters + months)
    assert trend.granularity == "month"
    assert trend.period_labels == ["Aug", "Sep", "Oct"]


# --------------------------------------------------------------------------- #
# 13-15. Polarity
# --------------------------------------------------------------------------- #
def test_13_lower_is_better_turns_a_fall_into_an_improvement() -> None:
    falling = T.classify(_points([150.0, 120.0, 100.0]), metric="PPM", department="IQC")
    assert falling.classification == "falling" and falling.quality == "improving"

    rising = T.classify(_points([100.0, 120.0, 150.0]), metric="PPM", department="IQC")
    assert rising.classification == "rising" and rising.quality == "worsening"


def test_14_a_neutral_metric_is_never_judged() -> None:
    trend = T.classify(_points([100.0, 120.0, 150.0]), metric="Insp. Lot", department="IQC")
    assert trend.classification == "rising"
    assert trend.quality == "neutral"
    assert trend.polarity == "neutral"


def test_15_an_undeclared_metric_stays_unknown() -> None:
    trend = T.classify(_points([100.0, 120.0, 150.0]), metric="Whatever", department="IQC")
    assert trend.classification == "rising" and trend.quality == "unknown"
    assert trend.polarity is None

    # a department that declares nothing at all
    provisional = T.classify(_points([100.0, 120.0, 150.0]), metric="PPM", department="OQC")
    assert provisional.quality == "unknown"


# --------------------------------------------------------------------------- #
# Against the real data
# --------------------------------------------------------------------------- #
def test_the_real_workbook_has_too_few_months_for_a_trend(iqc_real: Path) -> None:
    tables = [from_normalized(table, "IQC") for table in parse_file(iqc_real, "IQC").tables]
    series = A.table_series(tables[0], filters={"metric": "PPM"})[0]
    trend = T.trend_of_series(series, department="IQC")
    # the sheet shows one month beside years and quarters: quarters are the run
    assert trend.granularity == "quarter"
    assert trend.period_labels == ["1Q", "2Q", "3Q"]
    assert trend.classification in ("rising", "falling", "volatile", "stable")


def test_an_evolved_file_supports_a_monthly_trend(iqc_evolution) -> None:
    tables = [
        from_normalized(table, "IQC")
        for table in parse_file(iqc_evolution["c"], "IQC").tables
    ]
    series = A.table_series(tables[0], filters={"metric": "PPM"})[0]
    trend = T.trend_of_series(series, department="IQC")
    assert trend.granularity == "month"
    assert trend.period_labels == ["Aug", "Sep", "Oct"]
    assert trend.points == 3
    assert trend.classification in ("rising", "falling", "volatile", "stable")
    assert trend.quality in ("improving", "worsening", "stable", "unknown")


def test_the_classification_is_reproducible() -> None:
    points = _points([100.0, 120.0, 150.0])
    first = T.classify(points, metric="PPM", department="IQC").to_dict()
    second = T.classify(points, metric="PPM", department="IQC").to_dict()
    assert first == second

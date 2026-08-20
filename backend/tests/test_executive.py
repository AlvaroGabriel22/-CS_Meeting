"""Sprint 4 — the executive layer: KPIs, insights, ranking, provenance.

Everything is derived from the snapshot: no metric, period or target is
invented, and no cause is ever stated.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.excel import parse_file
from app.services import executive as E
from app.services.interpretation import from_normalized


def _tables(path: Path, department: str = "IQC"):
    return [from_normalized(table, department) for table in parse_file(path, department).tables]


def _view(path: Path, **kwargs):
    return E.build_executive_view(_tables(path), department="IQC", **kwargs)


# --------------------------------------------------------------------------- #
# Period resolution (13-15: Aug → 3Q, Sep → 3Q, Oct → 4Q)
# --------------------------------------------------------------------------- #
def test_the_period_defaults_to_the_last_one_in_the_file(iqc_real: Path) -> None:
    view = _view(iqc_real, period_label=None, table="TTL")
    assert view["period"]["label"] == "Aug"
    assert view["period"]["quarter"] == "3Q"  # the engine, not the executive layer


@pytest.mark.parametrize(
    "key,period,quarter",
    [("a", "Aug", "3Q"), ("b", "Sep", "3Q"), ("c", "Oct", "4Q"), ("d", "Dec", "4Q")],
)
def test_13_14_15_month_to_quarter_holds_through_the_executive_layer(
    iqc_evolution, key: str, period: str, quarter: str
) -> None:
    view = E.build_executive_view(
        _tables(iqc_evolution[key]), period_label=period, table="TTL", department="IQC"
    )
    assert view["period"]["label"] == period
    assert view["period"]["quarter"] == quarter
    assert all(kpi["period"]["quarter"] == quarter for kpi in view["kpis"])


def test_the_reference_is_the_previous_period_of_the_same_kind(iqc_evolution) -> None:
    view = E.build_executive_view(
        _tables(iqc_evolution["c"]), period_label="Oct", table="TTL", department="IQC"
    )
    assert view["previousPeriod"]["label"] == "Sep"  # month against month
    assert view["comparisonBasis"] == "same_kind"
    assert "reference_period_is_preceding_column" not in view["warnings"]


def test_without_an_earlier_month_the_reference_is_labelled_as_preceding(
    iqc_real: Path,
) -> None:
    """The real sheet holds one month only: the fallback must be explicit."""
    view = _view(iqc_real, period_label="Aug", table="TTL")
    assert view["previousPeriod"]["label"] == "3Q"
    assert view["comparisonBasis"] == "preceding"
    assert "reference_period_is_preceding_column" in view["warnings"]


def test_the_first_period_of_a_file_has_no_reference(iqc_real: Path) -> None:
    view = _view(iqc_real, period_label="'25", table="TTL")
    assert view["previousPeriod"] is None
    assert view["comparisonBasis"] == "none"
    assert "no_reference_period_in_snapshot" in view["warnings"]
    assert all(kpi["delta"] is None for kpi in view["kpis"])


# --------------------------------------------------------------------------- #
# KPIs (4-8: target, polarity)
# --------------------------------------------------------------------------- #
def test_kpis_are_built_from_metrics_that_exist(iqc_real: Path) -> None:
    view = _view(iqc_real, period_label="Aug", table="TTL")
    assert view["metric"] == "PPM"  # the department's headline metric
    labels = [kpi["label"] for kpi in view["kpis"]]
    assert labels == ["Total · PPM", "Imported · PPM", "Local · PPM"]
    for kpi in view["kpis"]:
        assert kpi["value"] is not None and kpi["display"]
        assert kpi["source"] and kpi["sourceRange"]  # provenance
        assert kpi["selector"]["subcategory"] is None  # sub-groups stay detail


def test_04_a_snapshot_without_targets_reports_no_target(iqc_real: Path) -> None:
    view = _view(iqc_real, period_label="Aug", table="TTL")
    assert all(kpi["target"] is None and kpi["targetStatus"] is None for kpi in view["kpis"])
    assert all(kpi["targetBreached"] is False for kpi in view["kpis"])
    assert "no_target_in_snapshot" in view["warnings"]


def test_05_a_target_in_the_workbook_is_used(fixture_files) -> None:
    """The FIELD-shaped fixture carries Target/Result rows; the KPI picks it up."""
    tables = [
        from_normalized(table, "FIELD")
        for table in parse_file(fixture_files["field_asr_casr.xlsx"], "FIELD").tables
    ]
    series = [item for table in tables for item in __import__(
        "app.services.analytics", fromlist=["x"]
    ).table_series(table)]
    target = E.find_target(series, {"table": "ASR — Field Quality", "category": "ASR", "subcategory": "MX"})
    assert target is not None
    assert target["selector"]["seriesType"] == "Target"


def test_06_07_08_polarity_decides_severity_and_is_never_guessed(iqc_real: Path) -> None:
    lower = _view(iqc_real, period_label="Aug", table="TTL", metric="PPM")
    assert all(kpi["polarity"] == "lower_is_better" for kpi in lower["kpis"])
    assert {kpi["severity"] for kpi in lower["kpis"]} <= {"positive", "negative", "neutral"}

    neutral = _view(iqc_real, period_label="Aug", table="TTL", metric="Insp. Lot")
    assert all(kpi["polarity"] == "neutral" for kpi in neutral["kpis"])
    assert all(kpi["severity"] == "neutral" for kpi in neutral["kpis"] if kpi["delta"])

    # a department without declared polarity says "unknown", never a colour
    unknown = E.build_executive_view(
        _tables(iqc_real, "OQC"), period_label="Aug", table="TTL", department="OQC"
    )
    assert all(kpi["polarity"] is None for kpi in unknown["kpis"])
    assert all(
        kpi["severity"] in ("unknown", "neutral") for kpi in unknown["kpis"]
    )


def test_09_a_zero_baseline_gives_no_percentage(iqc_evolution) -> None:
    """Rules of ADR-0022 still hold inside the KPI strip."""
    view = E.build_executive_view(
        _tables(iqc_evolution["a"]), period_label="Aug", table="TTL", department="IQC"
    )
    for kpi in view["kpis"]:
        if kpi["previousValue"] == 0:
            assert kpi["deltaPercent"] is None
            assert kpi["status"] == "undefined_percent"


def test_target_status_and_breach_need_polarity() -> None:
    assert E.target_status(120.0, 100.0, "lower_is_better") == "above"
    assert E.target_status(80.0, 100.0, "lower_is_better") == "below"
    assert E.target_status(100.0, 100.0, "lower_is_better") == "at"
    assert E.target_status(None, 100.0, "lower_is_better") is None

    assert E.target_is_breached("above", "lower_is_better") is True
    assert E.target_is_breached("above", "higher_is_better") is False
    assert E.target_is_breached("above", None) is False  # no polarity, no judgement


# --------------------------------------------------------------------------- #
# Insights (10-11: ranking and provenance)
# --------------------------------------------------------------------------- #
def test_insights_say_what_happened_and_by_how_much(iqc_real: Path) -> None:
    view = _view(iqc_real, period_label="Aug", table="TTL")
    texts = [insight["text"] for insight in view["insights"]]
    assert texts, "the executive view must produce statements"

    assert any("rose" in text or "fell" in text for text in texts)
    assert any("%" in text for text in texts)
    assert any("Aug" in text for text in texts)
    # a comparison between categories is allowed; a cause is not
    assert any("largest" in text for text in texts)
    forbidden = ("because", "caused", "due to", "root cause")
    assert not any(word in text.lower() for text in texts for word in forbidden)


def test_10_insights_are_ranked_deterministically(iqc_real: Path) -> None:
    view = _view(iqc_real, period_label="Aug", table="TTL")
    scores = [insight["score"] for insight in view["insights"]]
    assert scores == sorted(scores, reverse=True)

    again = _view(iqc_real, period_label="Aug", table="TTL")
    assert [i["text"] for i in again["insights"]] == [i["text"] for i in view["insights"]]


def test_10_the_score_formula_is_explicit() -> None:
    plain = E.insight_score(delta_percent=10.0, delta=5.0, severity="positive", target_breached=False)
    wrong_way = E.insight_score(delta_percent=10.0, delta=5.0, severity="negative", target_breached=False)
    breached = E.insight_score(delta_percent=10.0, delta=5.0, severity="negative", target_breached=True)

    assert plain == 10.0
    assert wrong_way == 10.0 + E.WEIGHT_WRONG_DIRECTION
    assert breached == 10.0 + E.WEIGHT_WRONG_DIRECTION + E.WEIGHT_TARGET_BREACH
    # a runaway percentage cannot drown everything else
    assert E.insight_score(
        delta_percent=100_000.0, delta=1.0, severity="positive", target_breached=False
    ) == E.PERCENT_CAP


def test_11_every_insight_carries_its_provenance(iqc_real: Path) -> None:
    view = E.build_executive_view(
        _tables(iqc_real), period_label="Aug", table="TTL", department="IQC",
        version_id=9, version_number=3,
    )
    for insight in view["insights"]:
        assert insight["department"] == "IQC"
        assert insight["table"] == "TTL"
        assert insight["metric"] == "PPM"
        assert insight["period"]["label"] == "Aug"
        assert insight["referencePeriod"]["label"] == "3Q"
        assert insight["source"] and insight["sourceRange"] == "B2:I17"
        assert insight["versionId"] == 9 and insight["versionNumber"] == 3
        # renderable in any language
        assert insight["template"].startswith("insights.")
        assert insight["params"]


def test_insights_are_absent_when_nothing_can_be_compared(iqc_real: Path) -> None:
    view = _view(iqc_real, period_label="'25", table="TTL")
    assert view["insights"] == []


def test_the_largest_movement_insight_needs_at_least_two_movers(iqc_real: Path) -> None:
    view = _view(iqc_real, period_label="Aug", table="TTL")
    kinds = {insight["kind"] for insight in view["insights"]}
    assert "largest_movement" in kinds
    leader = next(i for i in view["insights"] if i["kind"] == "largest_movement")
    assert leader["params"]["count"] == 3  # Total, Imported, Local
    assert leader["category"] in ("Total", "Imported", "Local")


# --------------------------------------------------------------------------- #
# Sprint 5 — insights 2.0: trend-aware, ranked, never causal
# --------------------------------------------------------------------------- #
def test_16_an_insight_is_produced_from_a_trend(iqc_evolution) -> None:
    """Three months in a row give a statement about the sequence."""
    view = E.build_executive_view(
        _tables(iqc_evolution["c"]), period_label="Oct", table="TTL", department="IQC"
    )
    trend_insights = [insight for insight in view["insights"] if insight["kind"] == "trend"]
    assert trend_insights, "an evolved file must support a trend statement"

    insight = trend_insights[0]
    assert "consecutive" in insight["text"]
    assert insight["trend"]["points"] >= 3
    assert insight["trend"]["granularity"] == "month"
    assert insight["template"] in ("insights.trend_up", "insights.trend_down")


def test_16_no_trend_insight_without_enough_history(iqc_real: Path) -> None:
    view = _view(iqc_real, period_label="Aug", table="TTL", metric="Insp. Lot")
    for insight in view["insights"]:
        if insight["kind"] != "trend":
            continue
        assert insight["trend"]["points"] >= 3  # never claimed on two readings


def test_17_the_trend_raises_the_rank_of_a_worsening_metric() -> None:
    worsening = {"classification": "rising", "quality": "worsening", "points": 3}
    plain = E.insight_score(delta_percent=10.0, delta=5.0, severity="negative", target_breached=False)
    with_trend = E.insight_score(
        delta_percent=10.0, delta=5.0, severity="negative", target_breached=False, trend=worsening
    )
    assert with_trend == plain + E.WEIGHT_TREND_WORSENING

    unjudged = {"classification": "rising", "quality": "unknown", "points": 3}
    assert (
        E.insight_score(
            delta_percent=10.0, delta=5.0, severity="positive", target_breached=False, trend=unjudged
        )
        == 10.0 + E.WEIGHT_TREND_CONSISTENT
    )
    # a trend nobody can judge as bad adds nothing beyond consistency
    flat = {"classification": "stable", "quality": "stable", "points": 3}
    assert (
        E.insight_score(
            delta_percent=10.0, delta=5.0, severity="positive", target_breached=False, trend=flat
        )
        == 10.0
    )


def test_18_trend_insights_keep_their_provenance(iqc_evolution) -> None:
    view = E.build_executive_view(
        _tables(iqc_evolution["c"]),
        period_label="Oct",
        table="TTL",
        department="IQC",
        version_id=5,
        version_number=2,
    )
    for insight in view["insights"]:
        assert insight["table"] == "TTL"
        assert insight["source"] and insight["sourceRange"]
        assert insight["versionId"] == 5 and insight["versionNumber"] == 2
        assert insight["period"]["label"] == "Oct"


def test_19_no_insight_ever_states_a_cause(iqc_evolution) -> None:
    forbidden = ("because", "caused", "due to", "root cause", "owing to", "thanks to")
    for key in ("a", "b", "c", "d"):
        view = E.build_executive_view(
            _tables(iqc_evolution[key]), period_label=None, table="TTL", department="IQC"
        )
        for insight in view["insights"]:
            lowered = insight["text"].lower()
            assert not any(word in lowered for word in forbidden), insight["text"]


def test_the_kpi_carries_its_trend(iqc_evolution) -> None:
    view = E.build_executive_view(
        _tables(iqc_evolution["c"]), period_label="Oct", table="TTL", department="IQC"
    )
    for kpi in view["kpis"]:
        trend = kpi["trend"]
        assert trend["classification"] in (
            "rising", "falling", "stable", "volatile", "insufficient_data",
        )
        assert trend["quality"] in ("improving", "worsening", "stable", "neutral", "unknown")
        if trend["classification"] != "insufficient_data":
            assert trend["points"] >= 3 and trend["periodLabels"]

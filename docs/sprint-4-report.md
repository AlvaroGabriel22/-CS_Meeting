# Sprint 4 — report

**Scope: the IQC page becomes an executive page.** One version and one period
drive everything on screen; KPIs and insights are derived from the model, never
invented. OQC and FIELD were not touched.

---

## 1. Implementation summary

```
header → VERSION SELECTOR → PERIOD / TABLE / METRIC
       → KPI STRIP → EXECUTIVE INSIGHTS → CHARTS → IQC TABLES → COMPARISON
```

The page owns `versionId`, `period`, `table` and `metric` and hands them to
every panel (ADR-0028), so the tables, the chart, the KPIs and the insights are
always reading the same snapshot and the same period.

New backend layer, `app/services/executive.py`:

| Piece | Rule |
| --- | --- |
| **KPI** | one per top-level category of the chosen table and metric; the metric must exist in the snapshot |
| **reference period** | previous period of the same kind; failing that the preceding column, *labelled as such* (ADR-0025) |
| **target** | only when the workbook itself carries one (a `Target` series or a `Target` metric in the same group) |
| **severity** | only when the department declares the metric's polarity; otherwise `unknown` |
| **insight** | a sentence built from the numbers, with template + params + provenance (ADR-0026) |
| **ranking** | `min(|Δ%|,300) + 50 wrong direction + 25 target breached` (ADR-0027) |

## 2. New files

| File | Role |
| --- | --- |
| `backend/app/services/executive.py` | KPIs, insights, ranking, reference period |
| `backend/tests/test_executive.py` | 20 tests on the executive rules |
| `backend/tests/test_executive_api.py` | 5 tests on the endpoint and its dimensions |
| `frontend/src/components/executive/VersionSelector.tsx` | picks the snapshot the page reads |
| `frontend/src/components/executive/KpiStrip.tsx` | the KPI cards |
| `frontend/src/components/executive/ExecutiveInsights.tsx` | insight cards |
| `frontend/src/components/analytics/ChartsPanel.tsx` | the chart, now controlled |
| `frontend/src/components/analytics/ComparisonPanel.tsx` | period + version comparison, controlled |
| `docs/sprint-4-report.md` | this report |

`frontend/src/components/analytics/AnalyticsPanel.tsx` was removed: its
responsibility (owning the selection) moved to the page, its content split into
the two controlled panels above.

## 3. Modified files

`app/excel/period_engine.py` (`previous_period`), `app/schemas/analytics.py`
(`KpiOut`, `InsightOut`, `ExecutiveViewOut`), `app/api/routes/analytics.py`
(the executive endpoint), `frontend/src/pages/Department.tsx` (rebuilt as the
executive page), `frontend/src/types/api.ts`, `frontend/src/lib/api.ts`,
`frontend/src/components/analytics/QualityChart.tsx` (legend clipping),
i18n `en` / `pt-BR` / `ko`, and `docs/{api-contract,decisions}.md`, `README.md`.

## 4. APIs

One new endpoint; everything else reused unchanged.

| Method | Path | Parameters |
| --- | --- | --- |
| `GET` | `/api/versions/{id}/analytics/executive` | `period`, `table`, `metric` |

Still model-oriented: no period appears in a path. The version comparison uses
the Sprint 3 `/analytics/versus/{otherId}` endpoint as it stands.

## 5. Components

* **VersionSelector** — lists the snapshots from the API (`v2 · Oct —
  iqc_evolution_c.xlsx`); choosing one reloads the whole page state.
* **KpiStrip** — value, period, comparison against the resolved reference,
  target when it exists, and the source cell of every figure.
* **ExecutiveInsights / InsightCard** — the sentence in the user's language,
  the dimensions behind it, the version and the origin cell.
* **ChartsPanel / ComparisonPanel** — the Sprint 3 charts and comparisons, now
  driven by the page's selection.

## 6. Tests — **270 passing** (was 245)

```
cd backend && .venv/bin/python -m pytest -q     → 270 passed
cd frontend && npm run build                    → clean
```

| Requirement (§13) | Where |
| --- | --- |
| 1-2 version selection drives the page | `test_executive_api.py::test_02_03…` + browser |
| 3 period drives KPI/chart/insight | `test_executive_api.py::test_02_03…` |
| 4 KPI without target | `test_04_a_snapshot_without_targets_reports_no_target` |
| 5 KPI with target | `test_05_a_target_in_the_workbook_is_used` |
| 6-8 polarity: lower_is_better / neutral / unknown | `test_06_07_08_polarity_decides_severity…` |
| 9 zero baseline | `test_09_a_zero_baseline_gives_no_percentage` |
| 10 ranking | `test_10_insights_are_ranked_deterministically`, `test_10_the_score_formula_is_explicit` |
| 11 provenance | `test_11_every_insight_carries_its_provenance` |
| 12 version comparison | `test_12_version_comparison_still_answers…` |
| 13-15 Aug→3Q, Sep→3Q, Oct→4Q | `test_13_14_15_month_to_quarter_holds…` |

No regressions: the 245 tests of Sprints 0–3 still pass.

## 7. Browser validation

Real workbook (v1) and an evolved fixture (v2, `… 4Q Aug Sep Oct`) imported,
then driven through the DOM:

| Check | Result |
| --- | --- |
| version selector lists both snapshots | ✅ `v2 · Oct — iqc_evolution_c.xlsx`, `v1 · Aug — RawdataIQC.xlsx` |
| switching version changes the whole page | ✅ header `Version 1 · Aug`, KPI `5,495`, chart axis 6 periods, tables 6 periods |
| switching period changes the analysis | ✅ `Sep` → KPI `1,581`, insights "in Sep" |
| period options carry their quarter | ✅ `Aug · 3Q`, `Sep · 3Q`, `Oct · 4Q` |
| KPI strip | ✅ value, `vs 3Q (previous column)`, delta %, source `B2:I17 · I15` |
| insights | ✅ ranked, severity-coloured, with dimensions, version and cell |
| honest warnings | ✅ "No earlier period of the same kind…", "This workbook carries no target." |
| version comparison | ✅ unchanged from Sprint 3 |
| IQC tables | ✅ still faithful (merges, `Imported` rowspan 9, no artificial PPM) |
| console errors | ✅ none |
| narrow container | ✅ page does not overflow; the table scrolls inside its own container |

**Two bugs were found and fixed during this validation:**

1. insight sentences rendered as `"PPM up} 188.2%"` — plain i18next has no ICU
   `select`, so the direction became part of the template key (ADR-0026);
2. the chart legend kept a stale width and pushed the page sideways on a narrow
   container — the chart area now clips and the legend is width-bounded.

## 8. Screenshots

* executive page, real workbook (v1): KPI strip, insights, warnings —
  `/tmp/claude-chrome-screenshots-3dN8JN/screenshot-1787245171297-7.jpg`
* executive page, evolved snapshot (v2, `Oct · 4Q`) —
  `/tmp/claude-chrome-screenshots-3dN8JN/screenshot-1787245065135-6.jpg`

## 9. Example KPI

```json
{
  "label": "Local · PPM",
  "period": { "label": "Aug", "quarter": "3Q", "year": 2026 },
  "display": "35,714", "value": 35714.0,
  "previousPeriod": { "label": "3Q" }, "previousDisplay": "9,709",
  "delta": 26005.0, "deltaPercent": 267.8,
  "direction": "up", "severity": "negative", "polarity": "lower_is_better",
  "target": null, "targetStatus": null, "targetBreached": false,
  "source": "I15", "sourceRange": "B2:I17"
}
```

## 10. Example insights (real workbook, Aug)

```
[317.8] Local showed the largest increase in PPM among the 3 categories analysed (267.8% in Aug).
[317.8] Local · PPM rose 267.8% in Aug (9,709 → 35,714).
[ 46.4] Imported · PPM fell 46.4% in Aug (5,556 → 2,976).
[ 13.2] Total · PPM fell 13.2% in Aug (6,329 → 5,495).
```

Each carries `table`, `category`, `metric`, `period`, `referencePeriod`,
`versionId`, `sourceRange` and the origin cell. None states a cause — the model
holds none.

## 11. Example version comparison

`GET /api/versions/1/analytics/versus/2?period=Aug&table=TTL&metric=PPM`

```
Total · PPM     v1=5,495   v2=1,581   Δ=-3,914  -71.2%   J3 → L3
Imported · PPM  v1=2,976   v2=3,034   Δ=+58     +1.9%    J6 → L6
```

The same logical row lives in different columns of the two files; matched by
meaning, both origins preserved, neither snapshot touched.

## 12. Limitations

1. **The real IQC workbook has one month only.** Every KPI comparison on it
   falls back to "vs 3Q (previous column)". Month-on-month readings will appear
   as soon as a file carries two months — the evolved fixtures already prove it
   (`Oct` compares against `Sep`).
2. **No target in the real workbook**, so the target half of the KPI card and
   the `target_status` insight are exercised only by a fixture.
3. **Insight vocabulary is small** — three kinds (movement, largest movement,
   target status). Trends across three or more periods, and volume-weighted
   importance, are not modelled yet.
4. **KPIs cover top-level categories only.** Sub-groups (`SKD`, `CKD`) are in
   the tables and the charts but not in the strip.
5. **Responsiveness verified by container simulation**, not on a physical
   tablet: the browser extension drops when the window is resized.
6. **No frontend unit tests** (unchanged from Sprints 2–3): the contract is
   covered by 270 backend tests plus the browser session.

## 13. Architectural decisions

| ADR | Decision |
| --- | --- |
| **0025** | The reference period is resolved by the engine, and its basis (`same_kind` / `preceding` / `none`) is always stated. |
| **0026** | Generated sentences travel as template + params, with the direction in the key. |
| **0027** | Insight ranking is a documented three-term formula. |
| **0028** | The page owns version and period; the analytical panels are controlled. |

## 14. Next steps (Sprint 5 candidates)

1. **Issue Reports** — the rich-text editor the master prompt describes, with
   images inside cells and the translation path already designed (ADR-0006/0007).
2. **Trends across three or more periods** as a fourth insight kind.
3. **Export** — PDF/PPT of exactly what the executive page shows, using
   `insight.text` and the KPI strip.
4. When the real **OQC** workbook arrives: fixture, schema from the data. The
   executive layer should need no change beyond declaring that department's
   polarity — the test of ADR-0021/0022.

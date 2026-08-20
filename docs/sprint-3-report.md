# Sprint 3 — report

**Scope: the first analytical layer over the IQC model.** Charts, period
selection, period comparison, version comparison and the `ExecutiveInsight`
shape. OQC and FIELD were not touched.

---

## 1. Implementation summary

```
NormalizedTable (Sprints 1-2)
   │  app/services/analytics.py
   │    ├ series      selector {table · category · subcategory · metric} → points over periods
   │    ├ deltas      B − A, percentage only against a real non-zero baseline
   │    ├ versions    same selector, same period, two snapshots
   │    └ insights    ranked statements carrying value, delta and provenance
   ▼
GET /api/versions/{id}/analytics/series
GET /api/versions/{id}/analytics/comparison
GET /api/versions/{id}/analytics/versus/{otherId}
   ▼
AnalyticsPanel → PeriodSelect · QualityChart · ComparisonTable
```

Nothing in the chain names a month, a quarter or a week. The React components
receive labelled points and draw them; the period axis, the metric list and the
table list are all discovered from the snapshot.

## 2. New files

| File | Role |
| --- | --- |
| `backend/app/services/analytics.py` | series, deltas, comparisons, insights |
| `backend/app/schemas/analytics.py` | wire contract (series, delta, insight) |
| `backend/app/api/routes/analytics.py` | the three endpoints |
| `backend/tests/test_analytics.py` | 26 tests on the analytical rules |
| `backend/tests/test_analytics_api.py` | 7 tests on the endpoints |
| `frontend/src/components/analytics/AnalyticsPanel.tsx` | the department's analytical container |
| `frontend/src/components/analytics/QualityChart.tsx` | line/bar chart over ready data |
| `frontend/src/components/analytics/PeriodSelect.tsx` | period and dimension selectors |
| `frontend/src/components/analytics/ComparisonTable.tsx` | A/B table with delta and provenance |
| `docs/sprint-3-report.md` | this report |

## 3. Modified files

`app/domain/departments.py` (metric polarity), `app/main.py` (router),
`tests/fixtures/build_iqc_fixtures.py` (dataset C now carries `4Q` beside its
months, per §12), `tests/test_iqc_evolution.py`, `tests/test_render_model.py`,
`tests/test_snapshots.py` (fixture C expectations),
`frontend/src/types/api.ts`, `frontend/src/lib/api.ts`,
`frontend/src/pages/Department.tsx`, `frontend/vite.config.ts` (chart chunk),
i18n `en` / `pt-BR` / `ko`, and `docs/{architecture,data-model,api-contract,decisions}.md`.

## 4. APIs

| Method | Path | Parameters |
| --- | --- | --- |
| `GET` | `/api/versions/{id}/analytics/series` | `table`, `category`, `subcategory`, `metric`, `order=file\|chronological`, `limit` |
| `GET` | `/api/versions/{id}/analytics/comparison` | `periodA`, `periodB`, + the same dimensions, `insights` |
| `GET` | `/api/versions/{id}/analytics/versus/{otherId}` | `period`, + the same dimensions, `insights` |

Model-oriented by design: dimensions travel as query parameters, never as path
segments (no `/iqc/aug`). Existing endpoints were reused unchanged; nothing was
duplicated. Documented in `docs/api-contract.md`.

## 5. Components

* **AnalyticsPanel** — orchestrates the selectors and the two comparison
  panels; holds no business rule.
* **QualityChart** — recharts line/bar over `{periods, series}`; marks the
  selected period on the axis; `connectNulls={false}` so a missing value is a
  gap, never an interpolation.
* **PeriodSelect / OptionSelect** — options come from the model; a month also
  shows the quarter it belongs to (`Aug · 3Q`).
* **ComparisonTable** — value A, value B, delta, percentage, and the source
  cells of both sides.

## 6-7. Tests — **245 passing**

```
cd backend && .venv/bin/python -m pytest -q     → 245 passed
cd frontend && npm run build                    → tsc -b && vite build, clean
```

| File | Tests | Covers |
| --- | --- | --- |
| `test_analytics.py` | 26 | §11 A–S: single/multi period, sortKey order, Aug→Sep→Oct→4Q, deltas, zero baseline, missing period, version comparison, immutability, TTL/SEC/TNP, no artificial PPM, SKD/CKD/Local, insights |
| `test_analytics_api.py` | 7 | the three endpoints, chronological order, absent period, self-comparison refused, reads never write |
| Sprints 0–2 | 212 | no regression |

## 8. Build

```
dist/index.html      0.55 kB │ gzip   0.31 kB
dist/index.css      22.00 kB │ gzip   5.16 kB
dist/index.js      113.05 kB │ gzip  35.23 kB
dist/react.js      180.03 kB │ gzip  59.25 kB
dist/charts.js     393.53 kB │ gzip 108.05 kB
```

The chart library was split into its own chunk so it is cached apart from the
application code.

## 9. Browser validation

Real workbook (v2) plus an evolved fixture (v1, `… 4Q Aug Sep Oct`) imported,
then asserted in the DOM:

| Check | Result |
| --- | --- |
| selectors come from the model | ✅ tables `TTL/SEC/TNP`, metrics `PPM/Rej. Lot/Insp. Lot` |
| period axis | ✅ `'25 '26 1Q 2Q 3Q Aug`, `Aug` bold as the selected period |
| chart | ✅ 5 series drawn, legend `Total · PPM`, `Imported · SKD · PPM`, … |
| period comparison | ✅ `Aug vs 3Q` with delta, % and `H3 → I3` |
| severity colouring | ✅ PPM falling is green, `Local · PPM` +267.8% is red |
| version comparison | ✅ v2 vs v1 on `Aug`, `I3 → J3` (different columns, same row) |
| no artificial `PPM` row label | ✅ absent from every table body |
| console errors | ✅ none |

**One bug was found and fixed during this validation:** the period selector
sorted `sortKey` as a string, which put `2026-M08` before `2026-Q1` (August
ahead of the first quarter). Ordering now belongs to the period engine on both
sides — ADR-0023.

## 10. Example

`GET /api/versions/2/analytics/series?table=TTL&metric=PPM`

```json
{
  "periods": [{ "label": "Aug", "kind": "month", "quarter": "3Q", "sortKey": "2026-M08" }],
  "series": [{
    "label": "Total · PPM",
    "selector": { "table": "TTL", "category": "Total", "metric": "PPM" },
    "sourceRange": "B2:I17",
    "points": [
      { "period": { "label": "'25" }, "value": 6629.0, "display": "6,629", "source": "D3" },
      { "period": { "label": "Aug" }, "value": 5495.0, "display": "5,495", "source": "I3" }
    ]
  }]
}
```

## 11. Aug → Sep → Oct → 4Q

The same code reads every generation of the file (`test_analytics.py`,
`test_analytics_api.py`):

| Fixture | Period axis | Month → quarter |
| --- | --- | --- |
| A | `'25 '26 1Q 2Q 3Q Aug` | Aug → 3Q |
| B | `… Aug Sep` | Sep → 3Q |
| C | `… 3Q 4Q Aug Sep Oct` | Oct → 4Q |
| D | `… 4Q Nov Dec` | Nov → 4Q, Dec → 4Q |
| E | `… Nov Dec W48` | week 48, `sortKey 2026-W48` |

No component was edited between generations.

## 12. Version comparison

`GET /api/versions/1/analytics/versus/2?period=Aug&table=TTL&metric=Rej.%20Lot`

```
Total · Rej. Lot        A=33  B=2   Δ=-31   -93.9%  positive   J4 → I4
Imported · Rej. Lot     A=104 B=1   Δ=-103  -99.0%  positive   J7 → I7
Imported · SKD · …      A=26  B=0   Δ=-26  -100.0%  positive   J10 → I10
```

The same logical row lives in column `J` of one snapshot and `I` of the other:
matched by meaning, both origins preserved. Reading a comparison never writes —
a snapshot fetched before and after is byte-identical (`test_analytics_api.py`).

## 13. Limitations

1. **Severity depends on declared polarity.** IQC declares `PPM` and `Rej. Lot`
   as `lower_is_better` and `Insp. Lot` as neutral; any other metric shows
   `unknown` rather than a guess. OQC/FIELD declare nothing (they have no real
   file yet).
2. **Chronological order is granularity-major** — years, then quarters, then
   months, each group in time order. Interleaving a month with the quarter that
   contains it on one axis was judged more confusing than helpful; the file
   order remains the default.
3. **Charts plot one metric at a time by default.** "All metrics" is available
   but mixes scales (PPM in the thousands next to lot counts in the tens); a
   dual axis or a normalised view is a Sprint 4 question.
4. **Insights are not yet worded for humans.** The title is a label, not a
   sentence, and nothing ranks them by business importance beyond the size of
   the movement.
5. **No frontend unit tests.** As in Sprint 2, the contract is covered by
   backend tests plus a real browser session.
6. **The version picker on the department page still shows only the latest
   snapshot's tables**; the comparison panel can reach any version, but the
   tables container does not switch versions yet.

## 14. Architectural decisions

| ADR | Decision |
| --- | --- |
| **0021** | A series is identified by meaning, not position; endpoints are model-oriented. |
| **0022** | `delta` is arithmetic; `deltaPercent` needs a real non-zero baseline; `severity` needs declared polarity. |
| **0023** | Ordering belongs to the period engine — the client renders the order it receives. |
| **0024** | `ExecutiveInsight` is defined and produced now, with full provenance, for a later presentation sprint. |

## 15. Next steps (Sprint 4 candidates)

1. Version picker driving the whole department page (tables *and* charts).
2. Insight wording and ranking — the step between "a delta" and "a sentence an
   executive reads".
3. A KPI strip (current period, previous period, target when the model has one).
4. When the real **OQC** workbook arrives: fixture, schema from the data; the
   analytics layer should need no change, which will be the test of ADR-0021.

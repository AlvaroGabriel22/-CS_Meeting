# Sprint 1 — report

**Scope: IQC only.** The real IQC workbook was available; OQC and FIELD were
not, so nothing about their structure was invented (ADR-0016).

---

## 1. What was implemented

```
RawdataIQC.xlsx
   │  parser        openpyxl → RawWorkbook (values, styles, merges)
   │  regions       three blocks found: B2:I17, K2:R17, T2:AA17
   │  interpreter   title, header band, label columns
   │    ├ hierarchy.py       blocks, metric cycle, category/subcategory/metric
   │    └ period_engine.py   '25 '26 1Q 2Q 3Q Aug → resolved against each other
   │  normalizer    typed cells: rawValue + number + displayValue + semantics
   │  verification  PPM = Rej. Lot / Insp. Lot × 1e6 → 87/87 confirmed
   ▼
NormalizedTable ──▶ SQLite ──▶ version snapshot ──▶ API ──▶ import screen
```

New modules:

| File | Role |
| --- | --- |
| `app/excel/hierarchy.py` | label blocks, metric cycle, implicit groups |
| `app/excel/period_engine.py` | reporting year, quarter↔month, ordering |
| `app/excel/verification.py` | checks an inference against the data |
| `app/services/presentation_service.py` | presentations and version snapshots |
| `app/api/routes/presentations.py` | presentations / versions endpoints |
| `frontend/src/pages/Import.tsx` | upload → preview → save version |
| `tests/fixtures/build_iqc_fixtures.py` | evolution fixtures A–E |

## 2. Files used

* `backend/tests/fixtures/real/RawdataIQC.xlsx` — the official structure
  (sheet `IQC`, three tables plus a `README` sheet that is correctly ignored).
* Fixtures A–E generated from that structure with a moving period axis.

## 3. Architectural decisions

| ADR | Decision |
| --- | --- |
| **0014** | A metric can be identified by structure alone — repetition separates metrics from groups, a block's first row carries the headline figure, and the schema only supplies its *name*. Verified arithmetically. |
| **0015** | Undated periods inherit the table's reporting year (`yearSource: inferred`); with no year anywhere, the warning stays. |
| **0016** | `DepartmentSchema.provisional` marks OQC/FIELD as "specification only, not confirmed". |

Supporting choices, all reversible:

* the table's name comes from a corner cell merged across the label columns
  (`TTL`, `SEC`, `TNP`) — structural, not a list of names;
* an unnamed leading block is named from `implicit_group_label` (`Total`) and
  flagged `inferred`;
* prose regions (the `README` sheet) are skipped with
  `skipped_non_tabular_region`, never parsed as data;
* `POST /api/uploads` gained `createVersion` so the UI can preview before
  saving; the confirmation costs no second parse (content-hash reuse).

## 4. Tests

```
cd backend && .venv/bin/python -m pytest -q
184 passed
```

| File | Tests | Covers |
| --- | --- | --- |
| `test_iqc_real.py` | 12 | the 20-point checklist against the real workbook |
| `test_iqc_evolution.py` | 9 | fixtures A→E: new months, 4Q, weeks |
| `test_snapshots.py` | 6 | snapshot creation, preview, immutability |
| `test_parser_contract.py` | 17 | the Sprint 0 acceptance suite (still green) |
| `test_periods.py` / `test_values.py` | 35 | vocabulary, canonical quarters, value coercion |
| `test_validation_report.py` | 9 | the per-workbook report and its ambiguities |
| others | 96 | structure, persistence, API, translation architecture |

Correction after the sprint: quarters are now the canonical labels `1Q`…`4Q`
throughout the model, the API and the frontend (ADR-0017); 16 tests were added
or updated for it.

Checklist of §13, item by item: tables detected (1), TTL (2), SEC (3), TNP (4),
periods (5), PPM without the word (6), Imported/Local hierarchy (7), SKD/CKD
(8), merges (9), structural empty cells (10), thousands (11), numbers stay
numbers (12), NA (13), warnings (14), snapshot (15), SQLite (16), snapshot read
back (17), added period columns (18), 4Q (19), added months (20).

## 5. The normalized model produced

```json
{
  "department": "IQC", "sheet": "IQC", "sourceRange": "B2:I17",
  "hierarchy": ["category", "subcategory", "metric"],
  "periods": ["'25", "'26", "1Q", "2Q", "3Q", "Aug"],
  "rowsSample": [
    {
      "sourceRow": 3,
      "category": "Total", "subcategory": null, "metric": "PPM",
      "values": [
        {"period": "'25", "type": "number", "raw": "6629",
         "value": 6629.0, "display": "6,629", "source": "D3"},
        {"period": "Aug", "type": "number", "raw": "5495",
         "value": 5495.0, "display": "5,495", "source": "I3"}
      ]
    }
  ]
}
```

Read as a tree:

```
TTL (B2:I17)
 ├── Total     → PPM · Rej. Lot · Insp. Lot
 ├── Imported  → PPM · Rej. Lot · Insp. Lot
 │    ├── SKD  → PPM · Rej. Lot · Insp. Lot
 │    └── CKD  → PPM · Rej. Lot · Insp. Lot
 └── Local     → PPM · Rej. Lot · Insp. Lot
```

`SEC` (K2:R17) and `TNP` (T2:AA17) are read identically.

## 6. Periods detected

| Label | Kind | Year | Quarter | sortKey | Year source |
| --- | --- | --- | --- | --- | --- |
| `'25` | year | 2025 | — | `2025-Y` | explicit |
| `'26` | year | 2026 | — | `2026-Y` | explicit |
| `1Q` | quarter | 2026 | `"1Q"` | `2026-Q1` | inferred |
| `2Q` | quarter | 2026 | `"2Q"` | `2026-Q2` | inferred |
| `3Q` | quarter | 2026 | `"3Q"` | `2026-Q3` | inferred |
| `Aug` | month | 2026 | `"3Q"` | `2026-M08` | inferred |

Quarters are canonical labels (`1Q`…`4Q`), never bare numbers — see ADR-0017.

Evolution (same code, no edits): `… Aug Sep` → `… Aug Sep Oct` →
`… 4Q Nov Dec` → `… 4Q Nov Dec W48`.

## 7. Warnings found

On the real file, per table:

* `headline_metric_inferred` — the PPM rows were named by the schema, because
  the workbook does not name them (confirmed arithmetically: 87/87 values);
* `implicit_group_label` — the unnamed leading block was called `Total`.

The validation report gives the file the verdict **ok**: three informational
notes (`mixed_period_granularity`, one per table) and no open question. The
`period_without_year` question raised in Sprint 0 is now resolved by the period
engine.

## 8. Limitations

1. **IQC only.** OQC and FIELD have no real file; their schemas are flagged
   provisional and no heuristic was tuned for them.
2. **`Total` and `PPM` are schema-supplied names.** The structure is detected
   without them, but if IQC renames these concepts the schema entry has to
   follow. Both are flagged as inferred in every payload.
3. **One presentation per department.** `ensure_presentation` reuses the active
   one; multiple parallel presentations per department are not exposed yet.
4. **No restore/compare of versions yet** — the schema carries `parent_version_id`
   and `status`, the endpoints come in a later sprint.
5. **Rendering is not final.** The import screen shows a preview table; the
   elegant department rendering is Sprint 2.
6. **The `README` sheet inside the workbook is skipped by a heuristic**
   ("a region with no numbers is not raw data"). A real table with zero numeric
   cells would also be skipped — reported as a warning, never silent.

## 9. Next steps (Sprint 2 candidates)

1. **Render the IQC tables in the UI** from the normalized model — merges,
   hierarchy, number formatting per language, controlled horizontal scroll.
2. **Charts** bound to periods by label/`sortKey` (target vs result, PPM trend).
3. **Version restore and comparison** (`v2` vs `v3`: which periods and values
   moved).
4. When the real **OQC** file arrives: add it as a fixture, fill its schema from
   the data, keep IQC untouched. Same for **FIELD** afterwards.

## 10. What still depends on the real OQC / FIELD files

* their table names, hierarchy levels and metric vocabulary;
* whether they use the same "headline row without a label" convention;
* whether ASR/CASR really share one sheet, and how their targets are laid out;
* any department-specific verification formula.

Until those files exist, `DEPARTMENT_SCHEMAS["OQC"]` and `["FIELD"]` stay
`provisional=True` and the parser treats them exactly like an unknown
department: generic rules only.

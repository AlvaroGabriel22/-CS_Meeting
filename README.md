# CS Meeting

Central system for the weekly quality executive presentations — **IQC**
(Incoming Quality Control), **OQC** (Outgoing Quality Control) and **FIELD**
(Field Quality).

Import the departments' raw Excel files, read their structure automatically,
render tables and charts, write Issue Reports, translate with AI, version the
work and export PPT/PDF. Local, no login, SQLite.

## Status — Sprint 5 (issue reports, trends, PDF/PPT export)

| Area | State |
| --- | --- |
| Parser → Interpreter → Normalizer pipeline | ✅ done |
| Normalized model (original + interpreted, hierarchy, periods) | ✅ done |
| Department schemas (IQC / OQC / FIELD as configuration) | ✅ done |
| SQLite schema + Alembic migration | ✅ done |
| Upload API, content-hash reuse, semantic view endpoint | ✅ done |
| Translation architecture (provider seam + cache + format rules) | ✅ contract + null provider |
| Presentation model contract | ✅ defined |
| Validation tooling for the real workbooks (report + ambiguities) | ✅ done |
| **Real IQC workbook parsed** (TTL / SEC / TNP, hierarchy, merges) | ✅ done |
| **Period engine** (year inference, quarter↔month, ordering) | ✅ done |
| **PPM identified without the word, verified arithmetically** | ✅ 87/87 |
| **Version snapshots** (append-only, raw file kept) | ✅ done |
| **IQC import screen** (upload → preview → save version) | ✅ done |
| **Render model** (merges as spans, hierarchy as depth, borders from the file) | ✅ done |
| **IQC tables rendered in the browser** from the saved snapshot | ✅ done |
| **Charts over the normalized model** (period axis from the file) | ✅ done |
| **Period comparison** with honest deltas (no percentage over a zero baseline) | ✅ done |
| **Version comparison** — same row, same period, two snapshots | ✅ done |
| **Version selector driving the whole page** (tables, charts, KPIs, insights) | ✅ done |
| **Executive KPI strip** with reference period, target when the file has one | ✅ done |
| **Executive insights** — ranked sentences, no invented causes, full provenance | ✅ done |
| **Trend analysis** over 3+ comparable periods, polarity-aware | ✅ done |
| **Issue reports** — editable text, status, images, provable numbers | ✅ done |
| **PDF export** — structured, searchable, tables and images preserved | ✅ done |
| **PPT export** — editable text, native chart, native tables | ✅ done |
| Tests + generated raw-data fixtures | ✅ 314 tests |
| Rich Issue Report editor, AI translation provider | ⏳ next sprints |
| OQC / FIELD structures | ⏳ waiting for the real files |

Read [`docs/sprint-5-report.md`](docs/sprint-5-report.md) for the latest
results, limitations and next steps.

## Quick start

```bash
# backend
cd backend
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload        # http://127.0.0.1:8000/docs

# frontend (second terminal)
cd frontend
npm install
npm run dev                                     # http://localhost:5173

# if port 8000 is taken by another project:
VITE_API_PROXY=http://127.0.0.1:8100 npm run dev
```

## Import and read IQC in the browser

* `http://localhost:5173/department/IQC/import` — choose the workbook, read what
  the parser understood (tables, periods, hierarchy, warnings), save the version.
* `http://localhost:5173/department/IQC` — the executive page: pick a version
  and a period, and the KPI strip, the insights, the issue reports, the charts,
  the tables and the comparisons all follow that one selection. **Export PDF**
  and **Export PPT** take exactly that view to the meeting.

## See the pipeline work

```bash
cd backend
# generate the sample raw data (provisional synthetic fixtures)
.venv/bin/python -m tests.fixtures.build_fixtures /tmp/fx

# RAW EXCEL → PARSER → INTERPRETER → NORMALIZED MODEL, printed as meaning
.venv/bin/python -m app.tools.inspect_raw /tmp/fx/iqc_dataset_c.xlsx --department IQC

# or through the API
curl -F department=IQC -F file=@/tmp/fx/iqc_dataset_c.xlsx \
     http://127.0.0.1:8000/api/uploads
```

## Validate against the real workbooks

Put the real IQC / OQC / FIELD files in `backend/tests/fixtures/real/`
(gitignored), then:

```bash
cd backend && .venv/bin/python -m app.tools.validate_real
```

One report per workbook lands in `backend/reports/`: sheets, tables,
`sourceRange`, merged ranges, periods, hierarchy, metrics, series, sizes,
warnings and **ambiguities**, plus a summarized JSON of the normalized model.

## Tests

```bash
cd backend && .venv/bin/python -m pytest -q     # 314 passed
cd frontend && npm run build
```

## Documentation

* [`docs/architecture.md`](docs/architecture.md) — layers, folders, data flow, how to run
* [`docs/excel-parser.md`](docs/excel-parser.md) — how the parser identifies structure
* [`docs/data-model.md`](docs/data-model.md) — Excel → internal model, SQLite schema
* [`docs/api-contract.md`](docs/api-contract.md) — endpoints and payloads
* [`docs/period-engine.md`](docs/period-engine.md) — how periods are discovered and resolved
* [`docs/versioning.md`](docs/versioning.md) — snapshots, and what never gets overwritten
* [`docs/decisions.md`](docs/decisions.md) — architecture decision log
* [`docs/sprint-0-report.md`](docs/sprint-0-report.md) — Sprint 0 report
* [`docs/sprint-1-report.md`](docs/sprint-1-report.md) — Sprint 1 report
* [`docs/sprint-2-report.md`](docs/sprint-2-report.md) — Sprint 2 report
* [`docs/sprint-3-report.md`](docs/sprint-3-report.md) — Sprint 3 report
* [`docs/sprint-4-report.md`](docs/sprint-4-report.md) — Sprint 4 report
* [`docs/sprint-5-report.md`](docs/sprint-5-report.md) — Sprint 5 report

## The one rule

Next week's file will not look like this week's: `W32` becomes `W33`, `Sep`
appears, a row is added. Nothing in this system may depend on a cell position, a
week number or a column count — see ADR-0002.

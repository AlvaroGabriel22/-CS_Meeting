# CS Meeting

Central system for the weekly quality executive presentations — **IQC**
(Incoming Quality Control), **OQC** (Outgoing Quality Control) and **FIELD**
(Field Quality).

Import the departments' raw Excel files, read their structure automatically,
render tables and charts, write Issue Reports, translate with AI, version the
work and export PPT/PDF. Local, no login, SQLite.

## Status — Sprint 0 (discovery, validation, architecture)

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
| Tests + generated raw-data fixtures | ✅ 130 tests |
| Frontend shell (design system, routing, i18n en/pt-BR/ko) | ✅ scaffold |
| Charts, Issue Report editor, versions CRUD, AI provider, exports | ⏳ next sprints |

Read [`docs/sprint-0-report.md`](docs/sprint-0-report.md) for results,
limitations, open decisions and risks.

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
```

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
cd backend && .venv/bin/python -m pytest -q     # 130 passed, 2 skipped
cd frontend && npm run build
```

## Documentation

* [`docs/architecture.md`](docs/architecture.md) — layers, folders, data flow, how to run
* [`docs/excel-parser.md`](docs/excel-parser.md) — how the parser identifies structure
* [`docs/data-model.md`](docs/data-model.md) — Excel → internal model, SQLite schema
* [`docs/api-contract.md`](docs/api-contract.md) — endpoints and payloads
* [`docs/decisions.md`](docs/decisions.md) — architecture decision log
* [`docs/sprint-0-report.md`](docs/sprint-0-report.md) — Sprint 0 report

## The one rule

Next week's file will not look like this week's: `W32` becomes `W33`, `Sep`
appears, a row is added. Nothing in this system may depend on a cell position, a
week number or a column count — see ADR-0002.

# CS Meeting

Central system for the weekly quality executive presentations — **IQC**
(Incoming Quality Control), **OQC** (Outgoing Quality Control) and **FIELD**
(Field Quality).

Import the departments' raw Excel files, read their structure automatically,
render tables and charts, write Issue Reports, translate with AI, version the
work and export PPT/PDF. Local, no login, SQLite.

## Status — Sprint 0 (foundation)

| Area | State |
| --- | --- |
| Excel parser (regions, merges, periods, values, styles) | ✅ done |
| Normalized table model | ✅ done |
| SQLite schema + Alembic migration | ✅ done |
| Import API (`/api/imports`) with upload validation | ✅ done |
| Test suite + generated raw-data fixtures | ✅ 78 tests |
| Frontend shell (design system, routing, i18n en/pt-BR/ko) | ✅ scaffold |
| Charts, Issue Report editor, versions, translation, exports | ⏳ next sprints |

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

Try the pipeline without the UI:

```bash
cd backend
.venv/bin/python -m tests.fixtures.build_fixtures /tmp/fx     # sample raw data
curl -F department=IQC -F file=@/tmp/fx/iqc_w32.xlsx http://127.0.0.1:8000/api/imports
```

## Tests

```bash
cd backend && .venv/bin/python -m pytest -q
cd frontend && npm run build
```

## Documentation

* [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — layers, folders, how to run
* [`docs/TABLE_MODEL.md`](docs/TABLE_MODEL.md) — the normalized table and how it is inferred
* [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md) — SQLite schema and its rules
* [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) — endpoints and payloads
* [`docs/DECISIONS.md`](docs/DECISIONS.md) — architecture decision log

## The one rule

The next weekly file will not look like this week's: `W32` becomes `W33`,
`Sep` appears, a row is added. Nothing in this system may depend on a cell
position, a week number or a column count — see ADR-0002.

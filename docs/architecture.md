# Architecture

## Two pipelines, never mixed

```
RAW EXCEL → PARSER → INTERPRETER → NORMALIZER → NORMALIZED MODEL
          → REPOSITORY (SQLite) → PRESENTATION MODEL → UI / CHARTS / EXPORT

ISSUE CONTENT → RICH DOCUMENT MODEL → TRANSLATION → PRESENTATION → EXPORT
```

Raw data is a **fact**: imported, immutable, never edited. Issue content is
**editorial**: authored, versioned, translated. Export reads both and writes
neither.

## Layer responsibilities

| Layer | Module | In → Out | Never does |
| --- | --- | --- | --- |
| Parser | `app/excel/parser.py` | file → `RawWorkbook` | assign meaning |
| Regions | `app/excel/regions.py` | sheet → `Rect[]` | read values |
| Interpreter | `app/excel/interpreter.py` | region → `TableInterpretation` | build cells |
| Labels | `app/excel/hierarchy.py` | label cells → category/subcategory/metric/series | touch periods |
| Periods | `app/excel/period_engine.py` | periods → resolved periods | touch cells |
| Normalizer | `app/excel/normalizer.py` | interpretation → `NormalizedTable` | touch openpyxl |
| Verification | `app/excel/verification.py` | table → confirmed / warned | change a value |
| Repository | `app/services/import_service.py` | model ↔ SQLite | parse |
| Presentation | `app/services/interpretation.py` (+ Sprint 1 services) | model → presentation model | mutate facts |
| Frontend | `frontend/src` | presentation model → UI | know Excel |
| Exporter | Sprint 5 | presentation model → PDF/PPT | re-read the workbook |
| Translation | `app/services/translation/` | rich document → translated document | touch tables |

Only `app/excel/parser.py` imports openpyxl. Only `app/services/*` touch the
database. The API layer is thin: validate, call a service, serialize.

## Folder layout

```
CS_Meeting/
├── backend/
│   ├── app/
│   │   ├── core/          config, logging, domain errors
│   │   ├── db/            SQLAlchemy engine + SQLite schema
│   │   ├── domain/        department schemas (configuration, not ifs)
│   │   ├── excel/         raw_model → parser → regions → interpreter
│   │   │                  → normalizer → verification → pipeline
│   │   │                  (+ periods, period_engine, hierarchy, values, model)
│   │   ├── schemas/       Pydantic wire contract (camelCase)
│   │   ├── services/      storage, import, interpretation, translation/
│   │   ├── tools/         inspect_raw.py (CLI proof of interpretation)
│   │   └── api/routes/    HTTP layer
│   ├── alembic/           migrations
│   ├── tests/             parser, API, translation, generated fixtures
│   └── data/              SQLite file, raw uploads, assets (gitignored)
└── frontend/src/
    ├── components/ui/     shadcn/ui-compatible primitives
    ├── components/layout/ topbar, shells
    ├── pages/             Home, Department, Settings
    ├── i18n/              en, pt-BR, ko (no inline strings)
    ├── lib/               api client, number formatting, cn()
    └── types/api.ts       the contract, mirrored from backend/schemas
```

## Frontend

React + TypeScript + Vite + Tailwind v4, shadcn/ui conventions, Recharts for the
chart sprint, TipTap for the Issue Report sprint. The design language is white
surface, dark blue voice, pastel blue accent, depth from soft shadows only.

The UI consumes the **presentation model**. It never receives Excel
coordinates as instructions — `sourceRange` and `source` are shown only as
traceability ("this number came from `Q40`").

## Backend

FastAPI + SQLAlchemy 2.0 + Alembic on one SQLite file. No broker, no cache
server, no second database. Long operations (PDF/PPT) run in-request; if one
ever becomes slow enough to matter, the fix is a thread, not infrastructure.

## SQLite

Three groups of tables — facts, editorial, support — described in
[data-model.md](data-model.md). WAL mode, foreign keys on.

## Parser & normalization

See [excel-parser.md](excel-parser.md). The rule that governs everything:
**structure is inferred, coordinates are provenance**.

## Presentation model

`app/schemas/presentation.py` defines it:

```
Presentation → versions[] → { imports[], tables[], charts[],
                              issueReports[], translations[], assets[] }
```

A version *references* imports (no copy) and *owns* its editorial content.
Charts select rows, periods and series **by label and sortKey**, never by index,
so a table that gains a column keeps its charts working.

## Versioning

* `DRAFT` — the autosave target, mutable.
* `PUBLISHED` — created by "Save Version", never silently modified.
* A new version starts from its parent (`parent_version_id`) and copies only
  editorial rows.
* Presentations are limited to 8 active; archiving, trashing (recoverable) and
  deleting are explicit user actions. Nothing is ever deleted automatically.

## Translation

Two separate mechanisms (ADR-0007):

* **Interface** — i18next JSON files (`en`, `pt-BR`, `ko`). No API call.
* **User content** — `TranslationService` behind a `TranslationProvider`
  interface, cache-first, keyed by the content hash of the source document.
  Protected vocabulary (`PPM`, `SEC`, `TECPLAM`…) and protected patterns (week
  labels, numbers, product codes) are masked before the provider sees them and
  restored afterwards. Images and marks never leave the document.

The API key lives in backend settings and never reaches the frontend.

## Export

Sprint 5. PDF via ReportLab, PPT via python-pptx, both fed by the presentation
model — rendered natively, never as a screenshot of the UI.

## Assets

Images are written to `data/assets/`, addressed by content hash. SQLite keeps
id, path, mime, size, dimensions and usage (`asset_usages`) so orphans can be
collected.

## Running

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload     # http://127.0.0.1:8000/docs

cd frontend && npm install && npm run dev   # http://localhost:5173
```

Inspect a workbook without the UI:

```bash
cd backend
.venv/bin/python -m app.tools.inspect_raw path/to/IQC.xlsx --department IQC
```

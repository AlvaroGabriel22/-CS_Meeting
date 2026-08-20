# Architecture

## The two pipelines

Everything in the system is one of these two flows:

```
RAW DATA → PARSER → NORMALIZED DATA → PRESENTATION MODEL → UI → EXPORT
ISSUE CONTENT → RICH DOCUMENT MODEL → TRANSLATION → PRESENTATION → EXPORT
```

They never mix. Raw data is a *fact* (imported, immutable). Issue content is
*editorial* (authored, versioned). Translation reads editorial content only.
Export reads both but writes neither.

## Folder layout

```
CS_Meeting/
├── backend/
│   ├── app/
│   │   ├── core/            config, logging, domain errors
│   │   ├── db/              SQLAlchemy engine + SQLite schema
│   │   ├── excel/           the parser (no FastAPI, no SQLAlchemy inside)
│   │   │   ├── reader.py        openpyxl → SheetGrid (merges resolved)
│   │   │   ├── regions.py       finds table blocks in a sheet
│   │   │   ├── periods.py       discovers years / months / weeks / series
│   │   │   ├── structure.py     header band, label columns, descriptors
│   │   │   ├── values.py        typing, NA, #DIV/0!, display hints
│   │   │   ├── model.py         NormalizedTable & friends
│   │   │   └── parser.py        orchestration
│   │   ├── schemas/         Pydantic wire contract (camelCase)
│   │   ├── services/        storage, import, serializers (one job each)
│   │   └── api/routes/      thin HTTP layer
│   ├── alembic/             migrations
│   ├── tests/               parser + API tests, generated fixtures
│   └── data/                SQLite file, raw uploads, assets (gitignored)
└── frontend/
    └── src/
        ├── components/ui/       shadcn/ui-compatible primitives
        ├── components/layout/   topbar, shells
        ├── pages/               Home, Department, Settings
        ├── i18n/                en, pt-BR, ko (real i18n, no inline strings)
        ├── lib/                 api client, number formatting, cn()
        └── types/api.ts         the contract, mirrored from backend/schemas
```

## Layer rules

| Layer | May import | Must never |
| --- | --- | --- |
| `app/excel` | stdlib, openpyxl | FastAPI, SQLAlchemy, app.services |
| `app/services` | app.excel, app.db, app.core | FastAPI request objects |
| `app/api` | app.services, app.schemas | openpyxl, raw SQL |
| `frontend/lib` | types | react components |

This is what keeps the parser testable in isolation and lets openpyxl be
replaced without touching anything else.

## Services (one responsibility each)

Implemented in Sprint 0: `ExcelParserService` (`app/excel/parser.py`),
`TableNormalizationService` (`app/excel/structure.py`), `StorageService`
(`app/services/storage.py`), `ImportService` (`app/services/import_service.py`).

Planned, already reflected in the schema: `ChartService`, `IssueReportService`,
`TranslationService` (behind a `TranslationProvider` interface),
`PresentationVersionService`, `PdfExportService`, `PowerPointExportService`,
`AssetService`.

## Running

```bash
# backend
cd backend
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload      # http://127.0.0.1:8000/docs

# frontend
cd frontend
npm install
npm run dev                                   # http://localhost:5173
```

The Vite dev server proxies `/api` to the backend, so there is nothing to
configure in the browser.

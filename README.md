# CS Meeting

Central system for the weekly quality executive presentations — **IQC**
(Incoming Quality Control), **OQC** (Outgoing Quality Control) and **FIELD**
(Field Quality).

Import the departments' raw Excel files, read their structure automatically,
render tables and charts, write Issue Reports, translate them with AI, version
the work and export PPT/PDF. Local, no login, SQLite.

**The system draws; it does not calculate.** The user works the tables in Excel
and uploads the result. The system identifies the structure, renders the three
charts and the three tables faithfully, and hosts the report the person writes
by hand. No insights, no causes, no verdicts, no deltas of its own. AI is used
for one thing: translating that report between en / pt-BR / ko, without
touching a number (ADR-0033, ADR-0036).

The department page is three containers — **charts → tables → report** — and
nothing else: no buttons, no captions. Everything that changes a department
lives on its **configuration** screen (raw data, titles, report editor), and
every saved report is listed for download under **Reports**.

## Status — Sprint 8 (presentation screen, configuration screen, report builder)

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
| **Three charts side by side** — IQC stacks SKD · CKD · Local under a Total line | ✅ done |
| **Chart composed in the configuration** — pick the bars and the line per chart | ✅ done |
| **Three tables side by side**, in the workbook's order (TTL · SEC · TNP) | ✅ done |
| **Report builder** — columns, rows, and text / image / shape blocks per cell | ✅ done |
| **Configuration screen per department** — upload, titles, report | ✅ done |
| **Reports library** with per-part downloads (report · charts · tables · deck) | ✅ done |
| **No generated analysis, no calculation of our own** | ✅ by design (ADR-0033, ADR-0036) |
| **AI translation of what a person typed** — translated *and* spell-checked | ✅ Ollama · Claude · OpenAI-compatible |
| **Issue reports** — editable text, status, images, provable numbers | ✅ done |
| **PDF export** — structured, searchable, tables and images preserved | ✅ done |
| **PPT export** — editable text, native chart, native tables | ✅ done |
| Tests + generated raw-data fixtures | ✅ 328 tests |
| Rich Issue Report editor, AI translation provider | ⏳ next sprints |
| OQC / FIELD structures | ⏳ waiting for the real files |

Read [`docs/sprint-8-report.md`](docs/sprint-8-report.md) for the latest
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

### Choosing a translation engine

Three engines, one seam (ADR-0040). Without configuration the null engine
returns the source text — no translation, never a wrong one.

**A model on this machine** (nothing leaves it), with
[Ollama](https://ollama.com) running:

```bash
# backend/.env
CSM_TRANSLATION_PROVIDER=ollama
CSM_OLLAMA_URL=http://127.0.0.1:11434
CSM_OLLAMA_MODEL=gemma4:e2b
```

**Claude, over the network** — the key stays in the backend and never reaches
the browser:

```bash
CSM_TRANSLATION_PROVIDER=anthropic
CSM_ANTHROPIC_API_KEY=sk-ant-…
CSM_TRANSLATION_MODEL=claude-sonnet-5
```

**Anything speaking the OpenAI chat API** — `gpt-4o`, a gateway, a self-hosted
server:

```bash
CSM_TRANSLATION_PROVIDER=openai
CSM_OPENAI_API_KEY=sk-…
CSM_OPENAI_MODEL=gpt-4o-mini
CSM_OPENAI_URL=https://api.openai.com/v1
```

Whichever engine is configured, the system paces itself to its quota, batches
the whole report into as few requests as possible, retries what the service
asks it to retry, and falls back to the original text rather than failing
(ADR-0042):

```bash
CSM_TRANSLATION_RPM=3        # override the engine's declared limit
CSM_TRANSLATION_MAX_BATCH=60 # segments per request
CSM_TRANSLATION_RETRIES=3
```

The engine both translates the text and corrects what was mistyped in it —
spelling, accents, capitalisation — while every number, date and code is masked
out of the request and restored afterwards (ADR-0043).

`GET /api/translation/status` reports which provider is live.

Only **authored text** is ever sent: the report and the titles a person typed
for the charts and tables (ADR-0039). The interface ships in three languages
and every label inside a table belongs to the workbook — neither leaves the
backend. Numbers, periods and technical terms are masked even inside a
sentence, and an answer that changed one is discarded in favour of the original
(ADR-0035). It works the same for IQC, OQC and FIELD.

Without a key the null provider returns the source text: the page degrades to
"not translated", never to "translated wrongly".

## Import and read IQC in the browser

* `http://localhost:5173/department/IQC/import` — choose the workbook, read what
  the parser understood (tables, periods, hierarchy, warnings), save the version.
* `http://localhost:5173/department/IQC` — the department page: pick a version
  and read it top to bottom — the three charts, the three tables, then the
  report. Changing the interface language translates the report.
* `http://localhost:5173/department/IQC/config` — upload the workbook, rename
  the charts and tables, and build the report.
* `http://localhost:5173/reports` — every saved report, with its downloads. **Export PDF**
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

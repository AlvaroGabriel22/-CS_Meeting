# Sprint 5 — report

> **Revised after delivery.** The directive that followed this sprint — *the
> system must not generate insights, causes or AI analysis; AI is for
> translation only* — removed part of what is described below. §3 (trend
> engine) and §4 (insights 2.0) **no longer exist in the code**; §7–§9 and §11
> describe a page and exports that no longer show an insights block. What
> survived, and why, is written up in
> [ADR-0033](decisions.md#adr-0033--the-system-reports-it-does-not-analyse) and
> summarised in §19 at the end of this report. The rest of the sprint — issue
> reports, provenance, PDF/PPT export — stands as written.

**Scope: from an analytical page to a tool that goes to the meeting.** Issue
reports, trend analysis, insights 2.0 and PDF/PPT export. OQC and FIELD were
not touched — their workbooks still do not exist.

---

## 1. Implementation summary

```
NormalizedTable (Sprints 1-2) ── analytics (Sprint 3) ── executive (Sprint 4)
        │
        ├── trends.py        3+ comparable readings → rising / falling / stable /
        │                    volatile / insufficient_data, polarity-aware
        ├── executive.py     KPIs carry their trend; a trend insight joins the
        │                    ranking, which gains two documented terms
        ├── issues.py        editorial half editable, analytical half recomputed
        │                    from the snapshot and proved by cell
        └── export/          one context → structured PDF + editable PPTX
```

## 2. Issue reports

An issue has two halves that never mix (ADR-0029):

| Half | Fields | Who writes it |
| --- | --- | --- |
| editorial | title, description (rich document), severity, status, images, language | the user |
| analytical | period, reference period, value, previous value, delta, %, target, trend, `sourceCell`, `sourceRange` | recomputed from the snapshot |

* `POST /issues` takes a **selector** (table, category, subcategory, metric,
  period), never numbers — a client cannot make an issue claim something the
  file does not say;
* `PATCH` accepts five fields; anything else is refused *by name*
  (`{"fields": ["value"]}`), not silently dropped;
* status is a controlled vocabulary (`open` → `in_progress` → `resolved` →
  `closed`) and only a person moves it — a metric improving never resolves
  anything;
* the description is stored as a TipTap document with its content hash as
  `translationKey`, so the translation cache of ADR-0007 already applies;
* images go to `data/assets/` (content-addressed) and attach through
  `issue_media` as **evidence**, never as analytical data; the upload is
  validated by magic number, not by the name the browser sent.

## 3. Trend engine — ~~delivered~~ **removed** (ADR-0033)

`app/services/trends.py` — deterministic, documented, no AI (ADR-0031):

| Classification | Rule |
| --- | --- |
| `rising` | every non-flat step goes up |
| `falling` | every non-flat step goes down |
| `stable` | every step is flat |
| `volatile` | steps go both ways |
| `insufficient_data` | fewer than three comparable readings |

* only periods of the **same kind** are compared, and the **finest granularity
  with at least three readings** wins — three months beat four quarters;
* a step is flat below **2%** of the previous value (`FLAT_TOLERANCE`, a named
  constant so it can be argued with);
* `quality` needs declared polarity: `lower_is_better` turns `falling` into
  `improving`; a `neutral` metric is never judged; an undeclared one stays
  `unknown`.

## 4. Executive insights 2.0 — ~~delivered~~ **removed** (ADR-0033)

* new insight kind **`trend`** — "Imported · PPM has fallen across 3
  consecutive months (Aug → Oct)" — produced only when three or more
  comparable readings exist;
* every KPI now carries its `trend`, so the UI and the exports can show it;
* ranking (ADR-0027 extended by ADR-0031):

```
score = min(|Δ%|, 300)
      + 50  movement in the declared wrong direction
      + 25  on the wrong side of a target the file carries
      + 30  trend worsening over 3+ periods
      + 10  trend consistent but unjudgeable
```

* still no causality: a test asserts that no insight ever contains "because",
  "caused", "due to" or "root cause", across every fixture generation.

## 5. Database

Two new tables, nothing destroyed (migration `c9887591ff65`):

```
issues       ─ version_id, department, period, selector, editorial, numbers, provenance
issue_media  ─ issue_id → assets (bytes on disk, metadata in SQLite)
```

The Sprint 0 rich-text grid (`issue_report_*`) was left untouched: it models the
free-form report table of the master prompt and is still available for a later
sprint.

## 6. APIs

| Method | Path |
| --- | --- |
| `GET` / `POST` | `/api/versions/{id}/issues` |
| `PATCH` | `/api/versions/{id}/issues/{issueId}` |
| `POST` | `/api/versions/{id}/issues/{issueId}/media` |
| `GET` | `/api/assets/{assetId}` |
| `POST` | `/api/versions/{id}/export/pdf` · `/export/ppt` |

Model-oriented as before: no period, table or metric ever appears in a path.
Trends are served inside the existing executive endpoint rather than as a
separate resource — they are a property of a KPI, not an entity.

## 7. Components

`IssueCard` (editable title/description, status and severity selectors, image
attach, numbers and provenance shown read-only), `IssuesSection` (list + "raise
from insight"), `ExportButtons` (sends the page's state, downloads the file).
The page order is now: **KPIs → insights → issue reports → charts → tables →
comparison**.

## 8. PDF

ReportLab, structured — text is text, tables keep their spans, the chart is
drawn natively. Header carries department, version, period, metric and table;
every page carries a footer with the same identity. Blocks are kept together so
tables and issues are not split across pages. Evidence images are embedded.

Validated with `pypdf`: 6 pages, `Version 2`, `Period Oct`, `Key indicators`,
`Executive insights`, `Issue reports`, the issue title and description, `TTL`,
`SKD`, and **one embedded image** — with no artificial `PPM` row label in the
table dump.

## 9. PPT

python-pptx, editable — 7 slides for the same state:

1. executive overview (department, period, version, KPI cards)
2. executive insights (bulleted text with origin and trend)
3. one slide per issue (text + evidence picture)
4. **native chart** with its data behind it
5. version comparison, when the page is showing one
6+. one slide per IQC table, as a **native table with its merges**

Validated with python-pptx: the chart's categories read
`['25, '26, 1Q, 2Q, 3Q, Aug]`, the table cells include `TTL`, `Imported`,
`Rej. Lot` and **not** `PPM`, merged cells are merged, and the evidence picture
is present.

## 10. Tests — **314 passing** (was 270)

| File | Tests | Covers |
| --- | --- | --- |
| `test_trends.py` | 15 | §19.9–15: rising, falling, volatile, insufficient, granularity, polarity |
| `test_issues.py` | 11 | §19.1–8: creation, edit, status, provenance, version, period, image, translation key |
| `test_export.py` | 12 | §19.20–27: PDF, PPT, version, period, charts, issues, images, tables |
| `test_executive.py` | 23 | insights 2.0: trend insight, ranking terms, provenance, no causality |
| Sprints 0–4 | 253 | no regressions |

## 11. Browser validation

Real workbook (v1) and an evolved fixture (v2, `… 4Q Aug Sep Oct`), driven
through the DOM:

| Check | Result |
| --- | --- |
| page order | ✅ KPIs → insights → issue reports → graphs → tables → comparison |
| trend insight | ✅ "Imported · PPM has fallen across 3 consecutive months (Aug → Oct)" |
| raise issue from insight | ✅ card created with numbers, trend and `B2:L17 · L3 · v2` |
| edit title and description | ✅ saved; the numbers and provenance did not move |
| status and severity | ✅ `open → in_progress`, severity selectable |
| attach image | ✅ served from `/api/assets/1`, 160×160 rendered in the card |
| period switch | ✅ KPIs, insights and the issue list all follow |
| export buttons | ✅ both produce a file (see §12) |
| console errors | ✅ none after the two fixes below |

**Two bugs were found and fixed during this validation:**

1. duplicate React key in the "raise from insight" list — two insights sharing
   kind, category and metric collided; the key now includes the template and
   the index;
2. **React crashed on the export spinner** (`NotFoundError: insertBefore`)
   because Chrome was auto-translating the page and rewriting text nodes under
   React. The app ships its own translations, so browser translation is now
   disabled (ADR-0032) — which also stopped the UI appearing in Portuguese
   while the language selector said English.

## 12. Export validation

Files produced by clicking the buttons in the browser, then validated
programmatically:

```
IQC_Oct_v2_20260820-173317.pdf   14,490 bytes  6 pages   1 image
IQC_Oct_v2_20260820-173317.pptx  47,253 bytes  7 slides  1 chart, 3 tables, 1 picture
```

Both contain `IQC`, `Period Oct` / `Version 2`, the KPI strip, the insights
(including the trend one), the issue with its description and image, the chart
and the three IQC tables.

## 13. Screenshots

* executive page with issue reports and evidence image —
  `/tmp/claude-chrome-screenshots-3dN8JN/screenshot-1787247347102-9.jpg`
* KPI strip and insights (v2, `Oct · 4Q`) —
  `/tmp/claude-chrome-screenshots-3dN8JN/screenshot-1787247176976-8.jpg`

## 14. Examples from the real IQC data

Issue raised from an insight, edited, with evidence attached:

```
Total PPM spike — supplier audit          [In progress] [Medium]
TTL · Total · PPM · Oct
PPM 4,557   vs Sep +2,976 (+188.2%)   Trend volatile
Containment in place.
Supplier audit scheduled for next week.
[image]
B2:L17 · L3 · v2
```

Trend insight on the real structure:

```
Imported · PPM has fallen across 3 consecutive months (Aug → Oct).
   TTL · Imported · PPM · Oct · v2 · B2:L17 · L6      severity: positive
```

## 15. Limitations

1. **The description editor is a textarea**, not the full TipTap editor of the
   master prompt. The *storage* is already a rich document with a translation
   key, so the editor can be upgraded without a migration.
2. **Translation of issue text is not wired to a provider** — the cache, the
   protected-term masking and the key all exist (Sprint 0), but no button calls
   them yet.
3. **Charts in the exports are rendered from the data, not from the screen's
   chart.** They show the same series and periods, but the visual is
   ReportLab's / PowerPoint's, not recharts'.
4. **One issue list per period.** An issue raised on `Oct` is not shown while
   the page is on `Sep`; there is no "all periods" view yet.
5. **No issue deletion** — by design for now, nothing is deleted automatically
   or manually. A `closed` status is the way out.
6. **Trend needs three readings of one granularity.** The real workbook has a
   single month, so its trends are read on quarters; monthly trends appear as
   soon as a file carries three months (proved with the evolved fixtures).
7. **No frontend unit tests** (unchanged since Sprint 2): the contract is
   covered by 314 backend tests plus the browser session.

## 16. Architectural decisions

| ADR | Decision |
| --- | --- |
| **0029** | An issue has an editorial half and an analytical half; only the first is editable, the second is recomputed and provable. |
| **0030** | Both export formats read one context, built from the page's own state. |
| **0031** | Trend classification is deterministic, granularity- and polarity-aware; the ranking gains two documented terms. |
| **0032** | The application translates itself; browser auto-translation is disabled. |

## 17. Files

**New (backend):** `services/trends.py`, `services/issues.py`,
`services/assets.py`, `services/export/{context,pdf,powerpoint}.py`,
`schemas/issues.py`, `api/routes/{issues,exports}.py`, migration
`c9887591ff65`, tests `test_trends.py`, `test_issues.py`, `test_export.py`.

**New (frontend):** `components/issues/{IssueCard,IssuesSection}.tsx`,
`components/executive/ExportButtons.tsx`.

**Modified:** `db/models.py` (Issue, IssueMedia, statuses), `services/storage.py`
(image validation and storage), `services/executive.py` (trends in KPIs,
trend insight, ranking), `excel/period_engine.py` (unchanged behaviour, used by
trends), `main.py`, `pages/Department.tsx`, `types/api.ts`, `lib/api.ts`,
`index.html` (no browser translation), i18n `en`/`pt-BR`/`ko`, and
`docs/{api-contract,data-model,decisions}.md`, `README.md`.

## 18. Next steps (Sprint 6 candidates)

1. **The rich Issue Report editor** — TipTap with inline images, using the
   document model already stored.
2. **Wire the translation provider** so an issue reads in pt-BR and ko: the
   cache, the masking and the key are already there.
3. **An "all periods" issue view** and issue history across versions.
4. When the real **OQC** workbook arrives: fixture, schema from the data, and a
   polarity declaration — the analytical, executive, issue and export layers
   should need no change.

---

## 19. Revision — what was removed, and what replaced it

The sprint shipped a system that both *reported* and *concluded*. The directive
that followed kept the first half and deleted the second.

**Removed.** `services/trends.py` and `tests/test_trends.py`; `build_insights`,
`insight_score`, the ranking formula and every insight kind; `severity` on a
delta, on a KPI and on an issue's analytical half; `DepartmentSchema.polarity`
and `metric_polarity()`; `targetBreached`; the `insights` payload of both
comparison endpoints; the `ExecutiveInsights` component, the insights section of
the department page, the green/red delta colouring, and the `insights.*` /
`trends.*` i18n blocks in all three languages. Columns
`issues.analytical_severity` and `issues.trend` were dropped by migration
`7696dbad9dc7`.

**Replaced by.** `services/executive.py` now builds **key figures**: a value,
the reading in the resolved reference period, the difference, the percentage
when the baseline allows one, the direction of the movement, the target when the
workbook carries one, and the cell that proves all of it — in the order the
workbook lists them, with nothing said about them. The endpoint returns
`figures` instead of `kpis`. An issue raised from a figure gets a neutral
default title (the selection and the period) and `severity: "info"` for the user
to set. The PDF and the deck carry *Key figures*, the issues a person wrote, the
chart and the tables.

**Not touched.** The parser, the region split, the interpreter, the normalizer,
the period engine, the hierarchy inference, the render model, versioning,
snapshots and the export plumbing. Faithful interpretation was never what the
directive questioned.

**Tests — 293 passing** (was 314). The 21 net removals are the trend suite and
the insight assertions; the new tests assert the *absence* of generated
analysis: the exact key set of a figure and of a comparison row, that
`build_insights` / `insight_score` / `trends` do not exist, that an issue
payload carries no derived verdict, and that neither exported file contains the
vocabulary a generated analysis would need.

**Limitations of §15 that this revision resolves or changes.** Item 6 (trend
needs three readings) no longer applies — there is no trend engine. Item 2 (AI
translation not wired) is now the *only* place AI is allowed to appear, and
remains unwired pending approval.

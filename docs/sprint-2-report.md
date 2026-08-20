# Sprint 2 — report

**Scope: IQC rendering.** Structural fidelity to the reference workbook, not
dashboard aesthetics. OQC and FIELD were not touched.

---

## 1. What was implemented

```
NormalizedTable (Sprint 1)
   │  app/services/render_model.py     merges → spans, hierarchy → depth,
   │                                   styles → borders/alignment, periods as-is
   ▼
TableView  ──▶  GET /api/imports/{id}/tables/{tid}/view
           ──▶  GET /api/versions/{id}/view          (a whole snapshot)
   ▼
IQCTable / IQCCell   ──▶  the department page
```

| File | Role |
| --- | --- |
| `app/services/render_model.py` | builds the display grid from the normalized model |
| `app/schemas/table.py` | `TableViewOut`, `RenderRowOut`, `RenderCellOut`, `RenderColumnOut` |
| `app/schemas/presentation.py` | `VersionViewOut` |
| `app/api/routes/imports.py` | `/tables/{id}/view` |
| `app/api/routes/presentations.py` | `/versions/{id}/view` |
| `frontend/src/components/table/IQCTable.tsx` | header + body + horizontal scroll |
| `frontend/src/components/table/IQCCell.tsx` | one structural cell (spans, borders, indent) |
| `frontend/src/pages/Department.tsx` | loads the latest snapshot and renders it |
| `tests/test_render_model.py` | 25 tests on the render contract |

The React components contain **no** month, quarter or week name, and no rule
about `SKD`, `CKD` or `PPM`. Everything structural arrives in the payload.

## 2. What the browser shows

The real workbook, imported and rendered:

* `TTL`, `SEC` and `TNP` as three tables, each with its own source range;
* the corner cell (`TTL`) merged across both label columns, as in the file;
* `Imported` merged down nine rows, `Local` down three — verified in the DOM as
  `rowspan="9"` and `rowspan="3"`;
* `SKD` and `CKD` in bold at their own level, their `Rej. Lot` / `Insp. Lot`
  indented one step deeper;
* headline rows showing their figure with **no metric label** — the DOM
  contains no "PPM" anywhere;
* the unnamed first block shown as a muted italic `Total`, marked as read from
  the structure;
* period headers `'25 · '26 · 1Q · 2Q · 3Q · Aug`, unique, in file order;
* no console errors.

## 3. Architectural decisions

| ADR | Decision |
| --- | --- |
| **0018** | The UI receives a render model; structure is never re-derived in React. |
| **0019** | The headline row shows its figure and keeps its label cell empty; `PPM` stays metadata. The workbook's border pattern there (vertical rules only) is reproduced exactly. |
| **0020** | Inferred labels (`Total`) travel in a separate field and are drawn as visibly distinct from the file's own content. |

Smaller decisions:

* `.table-scroll > table { min-width: max-content }` — a wide table scrolls, it
  is never compressed, and numbers never wrap;
* under 1024px the first label column is sticky, so the identification stays in
  view while the periods scroll;
* alignment, weight, fill and borders come from the workbook's own styles; the
  defaults only apply where the file says nothing.

## 4. Tests

```
cd backend && .venv/bin/python -m pytest -q
212 passed
cd frontend && npm run build          # tsc -b && vite build
```

| File | Tests | Covers |
| --- | --- | --- |
| `test_render_model.py` | 25 | the §16 checklist: three tables, hierarchy, SKD/CKD/Local, Rej./Insp., values, merges as spans, no artificial PPM, dynamic periods A→E, weeks, styles |
| `test_snapshots.py` | 9 | snapshot rendering, old versions unchanged, preview ≡ saved version |
| Sprint 0/1 suites | 178 | no regression |

Checklist of §16 item by item: TTL (1), SEC (2), TNP (3), hierarchy (4), SKD
(5), CKD (6), Local (7), Rej. Lot (8), Insp. Lot (9), values (10), 1Q/2Q/3Q (11–13),
4Q (14), Aug (15), Sep (16), Oct (17), Nov (18), Dec (19), weeks (20) — the
last nine driven by fixtures A→E, one parametrised test per generation.

## 5. Browser validation (§17)

Done in a real Chrome session against the real file, asserted in the DOM:

| Check | Result |
| --- | --- |
| three tables render | ✅ `TTL`, `SEC`, `TNP` |
| header and periods appear | ✅ `['25, '26, 1Q, 2Q, 3Q, Aug]`, unique per table |
| hierarchy appears | ✅ merged groups, indented sub-groups |
| values appear | ✅ formatted (`20,970`), aligned as in the workbook |
| no artificial "PPM" | ✅ `/\bPPM\b/` absent from the rendered text |
| merges preserved | ✅ `TTL:1x2`, `Imported:9x1`, `Local:3x1` |
| no duplicate columns/periods | ✅ asserted in the DOM and in the model |
| console errors | ✅ none |
| desktop usable | ✅ full width, no page-level horizontal scroll |

## 6. Limitations

1. **The narrow-viewport scroll was verified by contract, not by a resized
   browser.** The Chrome extension disconnected when the window was resized, so
   the mobile/tablet behaviour rests on the CSS (`overflow-x: auto`,
   `min-width: max-content`, sticky first column) and on the desktop session.
   Worth a manual look on a real tablet.
2. **No frontend unit-test runner.** The render contract is covered by 25
   backend tests plus the browser session; adding Vitest for two presentational
   components was judged not worth the weight (§17). If the component layer
   grows in Sprint 3, that judgement should be revisited.
3. **One snapshot per page.** The department page always renders the latest
   version; choosing an older version in the UI is not wired yet (the endpoint
   already serves any version).
4. **Row heights are carried but not applied.** The model has `height`; the
   renderer lets content decide, which keeps the table compact.
5. **Theme colours, not workbook colours, for the header band.** The corner and
   period cells use the product's blue; the workbook's own fills are applied to
   every other cell. This is the one deliberate deviation from pixel fidelity,
   and it is one line in `IQCCell`.

## 7. Next steps (Sprint 3 candidates)

1. Charts over the same normalized model, bound to periods by label/`sortKey`.
2. Version picker on the department page (the endpoint already exists).
3. Version comparison (which periods and values moved between two snapshots).
4. When the real **OQC** workbook arrives: fixture, schema from the data, and
   the same renderer — no change expected in the component layer.

# Period engine

> The rule that decides whether this system survives next month.

Two layers do the work:

| Layer | File | Question it answers |
| --- | --- | --- |
| Vocabulary | `app/excel/periods.py` | what does this *token* mean? |
| Engine | `app/excel/period_engine.py` | what do these periods mean *together*? |

## 1. Vocabulary — one token at a time

Recognised case-insensitively in English, Portuguese and Korean:

| Kind | Examples |
| --- | --- |
| year | `2026`, `'26`, `CY26`, `FY2026`, `2026년` |
| quarter | `1Q`, `2Q`, `3Q`, `4Q`, `Q3`, `T3`, `3분기` |
| month | `Jan`…`Dec`, `January`, `Ago`, `Agosto`, `8월`, `Aug-26`, `2026-08` |
| week | `W30`…`W53`, `WK32`, `W-32`, `Week 32`, `S28`, `Semana 32`, `32주` |
| series (not a period) | `Target`, `Result`, `Plan`, `Meta`, `실적` |

A bare integer becomes a period **only** when its header row is already
dominated by that kind of token: a row reading `W30 W31 32` gives the `32`
meaning; a lonely `8` never becomes August.

Nothing is enumerated: `W30` and `W53` follow the same rule, and a week the
system has never seen parses exactly like the ones it has.

## 2. Engine — all the periods of a table together

```python
resolution = period_engine.resolve(periods)
```

### Reporting year

A header reading `'25 | '26 | 1Q | 2Q | 3Q | Aug` states two years and leaves
the quarters and the month undated. The **latest year written explicitly** is
the year being reported, and every undated period inherits it:

```
'25  → year 2025                     (explicit)
'26  → year 2026                     (explicit)
1Q   → 2026, quarter "1Q"            (inferred)
3Q   → 2026, quarter "3Q"            (inferred)
Aug  → 2026, month 8, quarter "3Q"   (inferred)
```

Each period records where its year came from (`yearSource: explicit | inferred`),
so the inference is visible instead of implied. When no year appears anywhere,
the periods keep `year: null` and the table carries the warning
`period_without_year` — a question for a human, never a guess.

### Quarter ↔ month

A quarter is always the **canonical label** the reports use — `1Q`, `2Q`, `3Q`,
`4Q` — never a bare number, however the file spelled it (`Q3`, `3Q`, `T3`,
`3분기` all become `"3Q"`). The ordinal is still available as
`quarterNumber` for arithmetic and ordering.

| Quarter | Months |
| --- | --- |
| `1Q` | Jan · Feb · Mar |
| `2Q` | Apr · May · Jun |
| `3Q` | Jul · Aug · Sep |
| `4Q` | Oct · Nov · Dec |

A month knows its quarter (`Aug` → `"3Q"`) and a quarter knows its months
(`4Q.months == (10, 11, 12)`), so `4Q.contains(Nov)` is a fact the engine can
answer:

```python
period_engine.covering(august, table.periods)   # -> ['26, 3Q]
```

### Ordering

`sort_key` orders by (year, granularity, ordinal) — **never** by column
position:

```
'25  <  '26  <  1Q  <  2Q  <  3Q  <  4Q  <  Nov  <  Dec  <  W48
```

A chart binds to a period's `label`/`sortKey`, so it keeps matching when the
column moves, and simply shows a gap when the period leaves the file.

## 3. What "dynamic" means in practice

The same code reads all of these, with no edit in between:

| Generation | Period axis |
| --- | --- |
| A | `'25 '26 1Q 2Q 3Q Aug` |
| B | `'25 '26 1Q 2Q 3Q Aug Sep` |
| C | `'25 '26 1Q 2Q 3Q Aug Sep Oct` |
| D | `'25 '26 1Q 2Q 3Q 4Q Nov Dec` |
| E | `'25 '26 1Q 2Q 3Q 4Q Nov Dec W48` |

Pinned by `tests/test_iqc_evolution.py`. A new month, a closing quarter or a
week appearing is data, not a code change.

## 4. What the engine never does

* it does not know today's date — a report about August is read as August in
  November;
* it does not invent a year when the file gives none;
* it does not reorder or rewrite the file's columns; source order stays the
  primary order for rendering, `sortKey` exists for charts;
* it does not consolidate quarters. When the file replaces `Aug/Sep/Oct` with
  `4Q`, that is a **new snapshot** — see [versioning.md](versioning.md); the
  previous version keeps showing the months it was saved with.

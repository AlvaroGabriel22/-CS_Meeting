"""Validate the parser against real workbooks and write a report per file.

Usage::

    # every workbook in backend/tests/fixtures/real/
    python -m app.tools.validate_real

    # a specific file, forcing the department
    python -m app.tools.validate_real path/to/OQC.xlsx --department OQC

    # choose where the reports go (default: backend/reports/)
    python -m app.tools.validate_real --out reports/2026-W34

For each workbook it writes ``<name>.md`` (readable report) and ``<name>.json``
(the summarized normalized model), and prints a verdict:

* ``ok``       — nothing to decide
* ``check``    — readable, but questions are listed in the report
* ``blocking`` — a table could not be interpreted safely; do not build on it
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from app.services.validation import workbook_report

DEFAULT_INPUT = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "real"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "reports"

SEVERITY_MARK = {"info": "ℹ", "check": "▲", "blocking": "■"}


def department_of(path: Path, override: str | None = None) -> str | None:
    if override:
        return override.upper()
    name = path.name.upper()
    return next((code for code in ("IQC", "OQC", "FIELD") if code in name), None)


def render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = [
        f"# Parser validation — {report['file']}",
        "",
        f"* department: **{report['department'] or 'not identified'}**",
        f"* parser version: `{report['parserVersion']}`",
        f"* verdict: **{report['verdict']}**",
        f"* sheets: {len(report['sheets'])} · tables detected: {report['tableCount']}",
    ]
    if report["warnings"]:
        lines.append(f"* workbook warnings: `{', '.join(report['warnings'])}`")

    lines += ["", "## Sheets", "", "| sheet | tables | warnings |", "| --- | --- | --- |"]
    for sheet in report["sheets"]:
        lines.append(
            f"| {sheet['name']} | {sheet['tables']} | {', '.join(sheet['warnings']) or '—'} |"
        )

    for index, table in enumerate(report["tables"], start=1):
        size = table["size"]
        lines += [
            "",
            f"## Table {index} — {table['title'] or table['sheet']}",
            "",
            f"* sheet / source range: `{table['sheet']}` / `{table['sourceRange']}`",
            f"* shape: `{table['shape']}` · period axis: `{table['periodAxis']}`",
            f"* size: {size['rows']} rows × {size['columns']} columns "
            f"({size['headerRows']} header row(s), {size['labelColumns']} label column(s), "
            f"{size['dataRows']} data rows, {size['valueCells']} value cells)",
            f"* hierarchy: {' > '.join(table['hierarchy']) or '—'}",
            f"* styles captured: {table['styles']}",
        ]
        if table["warnings"]:
            lines.append(f"* parser warnings: `{', '.join(table['warnings'])}`")

        lines += ["", "### Periods detected", ""]
        if table["periods"]:
            lines += [
                "| label | kind | year | quarter | month | week | sortKey |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
            for period in table["periods"]:
                lines.append(
                    f"| {period['label']} | {period['kind']} | {period['year'] or '—'} | "
                    f"{period.get('quarter') or '—'} | {period['month'] or '—'} | "
                    f"{period['week'] or '—'} | `{period['sortKey']}` |"
                )
        else:
            lines.append("_none_")

        lines += [
            "",
            "### Hierarchy detected",
            "",
            f"* categories: {', '.join(table['categories']) or '—'}",
            f"* subcategories: {', '.join(table['subcategories']) or '—'}",
            f"* metrics: {', '.join(table['metrics']) or '—'}",
            f"* series types: {', '.join(table['seriesTypes']) or '—'}",
            "",
            "### Values",
            "",
            "| type | cells |",
            "| --- | --- |",
        ]
        for value_type, count in sorted(table["valueTypes"].items()):
            lines.append(f"| {value_type} | {count} |")

        lines += ["", "### Merged ranges", ""]
        merged = table["mergedRanges"]
        lines.append(
            f"{len(merged)} range(s): `{', '.join(merged[:20])}`" + (" …" if len(merged) > 20 else "")
            if merged
            else "_none_"
        )

        lines += ["", "### Ambiguities", ""]
        if table["ambiguities"]:
            for item in table["ambiguities"]:
                mark = SEVERITY_MARK.get(item["severity"], "?")
                lines.append(f"* {mark} **{item['code']}** ({item['severity']}) — {item['message']}")
                if item["evidence"]:
                    lines.append(f"  * evidence: `{json.dumps(item['evidence'], ensure_ascii=False)}`")
        else:
            lines.append("_none_")

    lines += [
        "",
        "---",
        "",
        "The summarized normalized model of every table is in the `.json` file "
        "next to this report.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the parser against real workbooks")
    parser.add_argument("paths", nargs="*", type=Path, help="workbooks (default: fixtures/real/*)")
    parser.add_argument("--department", choices=["IQC", "OQC", "FIELD"], default=None)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    paths = args.paths or sorted(DEFAULT_INPUT.glob("*.xls[xm]"))
    if not paths:
        print(
            f"no workbook found in {DEFAULT_INPUT}\n"
            "Place the real IQC / OQC / FIELD files there (see its README).",
            file=sys.stderr,
        )
        return 2

    args.out.mkdir(parents=True, exist_ok=True)
    verdicts: dict[str, str] = {}

    for path in paths:
        if not path.exists():
            print(f"missing: {path}", file=sys.stderr)
            return 2
        report = workbook_report(path, department_of(path, args.department))
        stem = path.stem
        (args.out / f"{stem}.md").write_text(render_markdown(report), encoding="utf-8")
        (args.out / f"{stem}.json").write_text(
            json.dumps(
                {
                    "file": report["file"],
                    "department": report["department"],
                    "parserVersion": report["parserVersion"],
                    "verdict": report["verdict"],
                    "tables": [
                        {
                            "sourceRange": table["sourceRange"],
                            "ambiguities": table["ambiguities"],
                            "model": table["model"],
                        }
                        for table in report["tables"]
                    ],
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        verdicts[path.name] = report["verdict"]
        counts: dict[str, int] = {}
        for table in report["tables"]:
            for item in table["ambiguities"]:
                counts[item["severity"]] = counts.get(item["severity"], 0) + 1
        detail = ", ".join(f"{count} {severity}" for severity, count in sorted(counts.items()))
        print(
            f"{path.name:35} verdict={report['verdict']:9} "
            f"tables={report['tableCount']:2}  {detail or 'no ambiguities'}"
        )

    print(f"\nreports written to {args.out}")
    return 1 if "blocking" in verdicts.values() else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

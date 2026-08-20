"""Inspect a raw workbook straight from the command line.

The Sprint 0 proof: a real file in, the *interpreted* model out — periods,
hierarchy and values, with no Excel coordinates driving anything.

::

    python -m app.tools.inspect_raw path/to/IQC.xlsx --department IQC
    python -m app.tools.inspect_raw path/to/IQC.xlsx --json > interpretation.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.excel import parse_file
from app.services.interpretation import from_normalized, interpretation_view


def build_report(path: Path, department: str | None, max_rows: int | None) -> dict:
    workbook = parse_file(path, department)
    return {
        "file": workbook.filename,
        "parserVersion": workbook.parser_version,
        "warnings": workbook.warnings,
        "tables": [
            interpretation_view(from_normalized(table, department), max_rows=max_rows)
            for table in workbook.tables
        ],
    }


def render(report: dict) -> str:
    lines = [f"file: {report['file']}  (parser {report['parserVersion']})"]
    if report["warnings"]:
        lines.append(f"warnings: {', '.join(report['warnings'])}")
    for table in report["tables"]:
        lines.append("")
        lines.append(f"┌─ {table['table'] or '(untitled)'}")
        lines.append(
            f"│  sheet={table['sheet']}  source={table['sourceRange']}  "
            f"shape={table['shape']}  periodAxis={table['periodAxis']}"
        )
        if table["hierarchy"]:
            lines.append(f"│  hierarchy: {' > '.join(table['hierarchy'])}")
        if table["periods"]:
            lines.append(f"│  periods ({len(table['periods'])}): {', '.join(table['periods'])}")
        if table["warnings"]:
            lines.append(f"│  warnings: {', '.join(table['warnings'])}")
        for row in table["rows"]:
            if "period" in row:  # transposed table
                values = ", ".join(
                    f"{value['metric']}={value.get('display') or value.get('value')}"
                    for value in row["values"]
                )
                lines.append(f"│  {row['period']:<10} {values}")
                continue
            if "values" not in row:  # flat record
                lines.append(f"│  {row}")
                continue
            label = " / ".join(
                part
                for part in (
                    row.get("category"),
                    row.get("subcategory"),
                    row.get("metric"),
                    row.get("seriesType"),
                )
                if part
            )
            values = ", ".join(
                f"{value['period']}"
                + (f"·{value['series']}" if value.get("series") else "")
                + f"={value.get('display') or value.get('error') or value.get('raw') or '—'}"
                for value in row["values"]
            )
            lines.append(f"│  {label:<28} {values}")
        lines.append("└─")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect the interpretation of a raw workbook")
    parser.add_argument("path", type=Path)
    parser.add_argument("--department", choices=["IQC", "OQC", "FIELD"], default=None)
    parser.add_argument("--json", action="store_true", help="print the raw JSON view")
    parser.add_argument("--max-rows", type=int, default=None)
    args = parser.parse_args(argv)

    if not args.path.exists():
        print(f"file not found: {args.path}", file=sys.stderr)
        return 2

    report = build_report(args.path, args.department, args.max_rows)
    print(json.dumps(report, indent=2, ensure_ascii=False) if args.json else render(report))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

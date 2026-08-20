"""Pipeline orchestration.

::

    RAW EXCEL → parser → regions → interpreter → normalizer → NORMALIZED MODEL

Each arrow is a module with one job; this file only wires them together and
keeps a broken region from killing a whole import.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.domain.departments import DepartmentSchema, schema_for

from .interpreter import interpret_region
from .model import ParsedSheet, ParsedWorkbook, TableShape
from .normalizer import normalize_table
from .parser import parse_workbook
from .regions import find_regions
from .version import PARSER_VERSION

logger = logging.getLogger(__name__)


def parse_file(path: str | Path, department: str | None = None) -> ParsedWorkbook:
    """Full pipeline for one workbook.

    ``department`` is optional: when given, the matching
    :class:`DepartmentSchema` is used to raise confidence on the hierarchy
    (``SEC`` is a section, ``Insp.`` is a metric).  Parsing works without it.
    """
    path = Path(path)
    schema: DepartmentSchema | None = schema_for(department)
    raw = parse_workbook(path)
    workbook = ParsedWorkbook(filename=raw.filename, parser_version=PARSER_VERSION)
    workbook.warnings.extend(raw.warnings)

    for sheet in raw.sheets:
        parsed_sheet = ParsedSheet(name=sheet.name)
        regions = find_regions(sheet)
        if not regions:
            parsed_sheet.warnings.append("empty_sheet")
        for rect in regions:
            try:
                interpretation = interpret_region(sheet, rect, schema)
                table = normalize_table(sheet, interpretation, department=department)
            except Exception:  # one broken region must not lose the whole file
                logger.exception("region %s of sheet %r failed", rect.a1, sheet.name)
                parsed_sheet.warnings.append(f"region_failed:{rect.a1}")
                continue
            if table.shape is TableShape.FRAGMENT and not table.cells:
                continue
            parsed_sheet.tables.append(table)
        logger.info(
            "parsed sheet %r: %d region(s) -> %d table(s)",
            sheet.name,
            len(regions),
            len(parsed_sheet.tables),
        )
        workbook.sheets.append(parsed_sheet)

    if not workbook.tables:
        workbook.warnings.append("no_table_detected")
    return workbook

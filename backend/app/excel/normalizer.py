"""**Layer 3 — Normalizer: semantic structure -> normalized data model.**

Builds the serializable :class:`NormalizedTable` the rest of the system uses:
typed cells carrying *both* the original (``rawValue``, Excel address, merged
range, style) and the interpretation (``number``, ``displayValue``, semantic
type), plus deduplicated styles.

After this layer nothing needs the workbook again.
"""

from __future__ import annotations

import hashlib

from openpyxl.utils import range_boundaries

from . import values as V
from .interpreter import TableInterpretation
from .model import (
    CellRole,
    CellStyle,
    NormalizedCell,
    NormalizedTable,
    SemanticType,
    ValueType,
)
from .raw_model import RawSheet
from .regions import Rect


def _style_id(style: CellStyle) -> str | None:
    if style.is_default:
        return None
    return hashlib.blake2s(repr(style).encode("utf-8"), digest_size=6).hexdigest()


def _raw_text(value: object, number_format: str | None) -> str | None:
    """The value as it appears in the file, as a string."""
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip() or None


def _cell_semantic(
    interpretation: TableInterpretation,
    row_offset: int,
    col_offset: int,
    role: CellRole,
) -> SemanticType:
    if role is CellRole.HEADER:
        if row_offset < interpretation.title_rows:
            return SemanticType.TITLE
        column = interpretation.columns[col_offset]
        if column.period:
            return SemanticType.PERIOD
        if column.series_type:
            return SemanticType.SERIES
        return SemanticType.LABEL
    if role is CellRole.LABEL:
        override = interpretation.cell_semantics.get((row_offset, col_offset))
        if override is not None:
            return override
        role_name = interpretation.label_roles.get(col_offset, "label")
        return {
            "category": SemanticType.CATEGORY,
            "subcategory": SemanticType.SUBCATEGORY,
            "metric": SemanticType.METRIC,
            "series": SemanticType.SERIES,
        }.get(role_name, SemanticType.LABEL)
    if role is CellRole.VALUE:
        return SemanticType.VALUE
    return SemanticType.UNKNOWN


def normalize_table(
    sheet: RawSheet,
    interpretation: TableInterpretation,
    *,
    department: str | None = None,
) -> NormalizedTable:
    """Assemble the normalized table for one interpreted region."""
    rect: Rect = interpretation.rect
    table = NormalizedTable(
        sheet_name=sheet.name,
        source_range=rect.a1,
        title=interpretation.title,
        department=department,
        hierarchy=interpretation.hierarchy,
        shape=interpretation.shape,
        period_axis=interpretation.period_axis,
        header_row_count=interpretation.header_rows,
        label_col_count=interpretation.label_cols,
        columns=interpretation.columns,
        rows=interpretation.rows,
        warnings=list(interpretation.warnings),
        meta=dict(interpretation.meta),
    )

    header_band = interpretation.title_rows + interpretation.header_rows
    numeric_cells = uncached_formulas = 0

    for row_offset, row in enumerate(range(rect.r1, rect.r2 + 1)):
        for col_offset, col in enumerate(range(rect.c1, rect.c2 + 1)):
            source = sheet.get(row, col)
            if source is None:
                continue
            value_type, number, text, error = V.coerce(source.value)
            if value_type is ValueType.EMPTY and source.style.is_default and not source.formula:
                continue

            if row_offset < header_band:
                role = CellRole.HEADER
            elif col_offset < interpretation.label_cols:
                role = CellRole.LABEL
            elif value_type is ValueType.EMPTY and source.formula:
                # a formula whose result was never cached by Excel: still a data
                # slot, flagged so the UI can ask for a recalculated file
                role = CellRole.VALUE
                uncached_formulas += 1
            elif value_type is ValueType.EMPTY:
                role = CellRole.EMPTY
            else:
                role = CellRole.VALUE

            if role is CellRole.VALUE and value_type is ValueType.NUMBER:
                numeric_cells += 1

            display = V.display_format(source.number_format, value_type)
            style_id = _style_id(source.style)
            if style_id and style_id not in table.styles:
                table.styles[style_id] = source.style

            table.cells.append(
                NormalizedCell(
                    row=row_offset,
                    col=col_offset,
                    role=role,
                    semantic=_cell_semantic(interpretation, row_offset, col_offset, role),
                    value_type=value_type,
                    raw_value=_raw_text(source.value, source.number_format),
                    number=number,
                    text=text,
                    display_value=(
                        V.format_number(number, display) if value_type is ValueType.NUMBER and number is not None
                        else (error if value_type is ValueType.ERROR else text)
                    ),
                    raw=source.value if isinstance(source.value, (str, int, float, bool)) else None,
                    error_code=error,
                    formula=source.formula,
                    number_format=source.number_format,
                    display=display,
                    style_id=style_id,
                    source_address=source.address,
                    merged_range=source.merged_range,
                    is_merge_anchor=source.is_merge_anchor,
                )
            )

    table.merged_ranges = [rng for rng in sheet.merged_ranges if _intersects(rng, rect)]
    if uncached_formulas:
        table.warnings.append("formula_without_cached_value")
    table.meta.update(
        {
            "numericCells": numeric_cells,
            "uncachedFormulas": uncached_formulas,
            "periodCount": len(table.periods),
            "styleCount": len(table.styles),
        }
    )
    return table


def _intersects(range_str: str, rect: Rect) -> bool:
    c1, r1, c2, r2 = range_boundaries(range_str)
    return not (r2 < rect.r1 or r1 > rect.r2 or c2 < rect.c1 or c1 > rect.c2)

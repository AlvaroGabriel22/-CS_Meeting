"""**Layer 1 — Raw parsed structure.**

What the file literally contains: values, formulas, number formats, styles,
merged ranges, column widths, row heights and Excel coordinates.

No meaning is assigned here.  ``W33`` is still just the string ``"W33"`` sitting
in ``Q2``; turning it into "week 33" is the interpreter's job (layer 2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator

from openpyxl.utils import get_column_letter

from .model import DEFAULT_STYLE, CellStyle


@dataclass
class RawCell:
    """One cell exactly as the workbook holds it."""

    row: int  # 1-based Excel row
    col: int  # 1-based Excel column
    value: Any = None  # cached value (formulas already evaluated by Excel)
    formula: str | None = None
    number_format: str | None = None
    style: CellStyle = DEFAULT_STYLE
    merged_range: str | None = None
    is_merge_anchor: bool = False

    @property
    def address(self) -> str:
        """Excel coordinate — kept for traceability, never used as a rule."""
        return f"{get_column_letter(self.col)}{self.row}"


@dataclass
class RawSheet:
    """A sheet flattened into a dictionary of cells, with merges resolved.

    Every cell covered by a merged range carries the anchor's value, so callers
    never have to ask "is this cell hidden under a merge?".
    """

    name: str
    min_row: int = 1
    min_col: int = 1
    max_row: int = 1
    max_col: int = 1
    cells: dict[tuple[int, int], RawCell] = field(default_factory=dict)
    merged_ranges: list[str] = field(default_factory=list)
    col_widths: dict[int, float] = field(default_factory=dict)
    row_heights: dict[int, float] = field(default_factory=dict)

    def get(self, row: int, col: int) -> RawCell | None:
        return self.cells.get((row, col))

    def value(self, row: int, col: int) -> Any:
        cell = self.cells.get((row, col))
        return cell.value if cell else None

    def text(self, row: int, col: int) -> str:
        value = self.value(row, col)
        if value is None:
            return ""
        if isinstance(value, float) and value.is_integer():
            return str(int(value))  # a year header reads "2026", not "2026.0"
        return str(value).strip()

    def is_occupied(self, row: int, col: int) -> bool:
        cell = self.cells.get((row, col))
        if cell is None:
            return False
        return cell.value is not None and str(cell.value).strip() != ""

    def iter_rect(self, r1: int, c1: int, r2: int, c2: int) -> Iterator[RawCell]:
        for row in range(r1, r2 + 1):
            for col in range(c1, c2 + 1):
                cell = self.cells.get((row, col))
                if cell is not None:
                    yield cell


@dataclass
class RawWorkbook:
    """The whole file as read from disk."""

    filename: str
    sheets: list[RawSheet] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def sheet(self, name: str) -> RawSheet | None:
        return next((sheet for sheet in self.sheets if sheet.name == name), None)

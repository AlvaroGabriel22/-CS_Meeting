"""Post-parse checks that confirm an inference against the data itself.

The IQC tables never write the word ``PPM``: the parser infers that the first
row of each block is the headline metric.  That inference can be *verified*
arithmetically — a block whose ``Rej. Lot`` is 139 and whose ``Insp. Lot`` is
20970 must show ``139 / 20970 × 1_000_000 ≈ 6629`` on its headline row.

A check never rewrites a value.  It either confirms the reading or raises a
warning saying the block does not behave as expected.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.domain.departments import DepartmentSchema, canonical

from .model import NormalizedTable

logger = logging.getLogger(__name__)


@dataclass
class HeadlineCheck:
    checked: int = 0
    matched: int = 0
    mismatches: list[dict] = field(default_factory=list)
    skipped: int = 0

    @property
    def consistent(self) -> bool:
        return self.checked > 0 and not self.mismatches

    def to_dict(self) -> dict:
        return {
            "checked": self.checked,
            "matched": self.matched,
            "skipped": self.skipped,
            "consistent": self.consistent,
            "mismatches": self.mismatches[:10],
        }


def verify_headline_metric(
    table: NormalizedTable, schema: DepartmentSchema | None
) -> HeadlineCheck | None:
    """Check every block's headline row against its own numerator/denominator."""
    formula = schema.headline_formula if schema else None
    if formula is None or not schema or not schema.headline_metric:
        return None

    values = {(cell.row, cell.col): cell for cell in table.cells}
    period_columns = [column.index for column in table.columns if column.period]
    if not period_columns:
        return None

    rows_by_block: dict[int, list] = {}
    for row in table.rows:
        if row.is_header_row:
            continue
        rows_by_block.setdefault(row.block, []).append(row)

    check = HeadlineCheck()
    headline = canonical(schema.headline_metric)
    numerator_name = canonical(formula.numerator)
    denominator_name = canonical(formula.denominator)

    for block_rows in rows_by_block.values():
        by_metric = {canonical(row.metric or ""): row for row in block_rows}
        head = by_metric.get(headline)
        numerator = by_metric.get(numerator_name)
        denominator = by_metric.get(denominator_name)
        if not (head and numerator and denominator):
            check.skipped += 1
            continue

        for column in period_columns:
            head_cell = values.get((head.index, column))
            num_cell = values.get((numerator.index, column))
            den_cell = values.get((denominator.index, column))
            if not (head_cell and num_cell and den_cell):
                continue
            if None in (head_cell.number, num_cell.number, den_cell.number):
                continue
            if den_cell.number == 0:
                continue

            expected = num_cell.number / den_cell.number * formula.scale
            actual = head_cell.number
            check.checked += 1
            reference = max(abs(expected), 1.0)
            if abs(expected - actual) / reference <= formula.tolerance:
                check.matched += 1
            else:
                check.mismatches.append(
                    {
                        "source": head_cell.source_address,
                        "expected": round(expected, 2),
                        "actual": actual,
                        "category": head.category,
                        "subcategory": head.subcategory,
                    }
                )

    if check.checked == 0:
        return None
    if check.mismatches:
        logger.warning(
            "%s: %d headline value(s) do not match %s/%s×%g",
            table.source_range,
            len(check.mismatches),
            formula.numerator,
            formula.denominator,
            formula.scale,
        )
    return check


def apply_checks(table: NormalizedTable, schema: DepartmentSchema | None) -> NormalizedTable:
    """Run every verification and record the outcome on the table."""
    check = verify_headline_metric(table, schema)
    if check is None:
        return table
    table.meta["headlineCheck"] = check.to_dict()
    if check.consistent:
        # the inference is confirmed by the numbers themselves
        table.meta["headlineMetricConfirmed"] = True
    else:
        table.warnings.append("headline_metric_mismatch")
    return table

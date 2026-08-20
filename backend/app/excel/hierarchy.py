"""Row hierarchy: category > subcategory > metric, discovered from the labels.

The real IQC tables do not spell out every level.  A block looks like this
(column B on the left, column C in the middle):

::

    (empty)   (empty)      6629    <- the headline metric of the block: PPM
    (empty)   Rej. Lot      139
    (empty)   Insp. Lot   20970
    Imported  (empty)      5319    <- headline metric of "Imported"
    Imported  Rej. Lot       83
    Imported  Insp. Lot   15604
    Imported  SKD         18847    <- a sub-group, and its headline metric
    Imported  Rej. Lot       69
    Imported  Insp. Lot    3661

So the word ``PPM`` never appears, ``SKD``/``CKD`` sit in the *metric* column
although they are sub-groups, and the first block has no name at all.

The rules used here are structural, not vocabulary-based:

1. **Repetition tells metrics apart from groups.**  A label that comes back in
   every block (``Rej. Lot``, ``Insp. Lot``) is a metric; a label that appears
   once (``SKD``, ``CKD``) opens a sub-group.
2. **A block starts** where a category is written, where a sub-group label
   appears, or where the metric cell is empty.
3. **The first row of a block carries the headline metric** — the derived
   figure the block is about.  Its name comes from the department schema
   (``PPM`` for IQC) and is flagged as inferred; the file itself never says it.
4. An unnamed leading block is the total of the table (schema
   ``implicit_group_label``), also flagged as inferred.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.domain.departments import DepartmentSchema, is_metric_token

from . import periods as P

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LabelCell:
    """One label cell of one data row."""

    value: str = ""  # value in force here (merged/blank cells inherit)
    written: bool = False  # True only where the analyst actually typed it


@dataclass
class RowLabels:
    category: str | None = None
    subcategory: str | None = None
    metric: str | None = None
    series_type: str | None = None
    block: int = 0
    #: which fields the parser had to infer rather than read
    inferred: tuple[str, ...] = ()


@dataclass
class LabelAnalysis:
    roles: dict[int, str] = field(default_factory=dict)
    rows: list[RowLabels] = field(default_factory=list)
    metric_cycle: tuple[str, ...] = ()
    subgroups: tuple[str, ...] = ()
    blocks: int = 0
    hierarchy: tuple[str, ...] = ()
    warnings: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Column roles
# --------------------------------------------------------------------------- #
def _dominated_by(values: list[str], predicate, minimum_distinct: int = 1) -> bool:
    present = [value for value in values if value]
    if not present:
        return False
    hits = [value for value in present if predicate(value)]
    if len(set(hits)) < minimum_distinct:
        return False
    return len(hits) >= max(1, int(0.6 * len(present)))


def assign_column_roles(
    matrix: list[list[str]], label_cols: int, schema: DepartmentSchema | None
) -> tuple[dict[int, str], tuple[str, ...]]:
    """Which label column is the category, the subcategory, the metric, the series.

    1. a column dominated by plan-vs-outcome labels is a **series** (ADR-0012);
    2. the outermost remaining column groups the rows: **category**, never metric;
    3. the **metric** is the innermost remaining column that reads as measured
       quantities, or the innermost column when the vocabulary says nothing;
    4. a single label column of unknown words names the rows: category.
    """
    if label_cols <= 0 or not matrix:
        return {}, ()

    roles: dict[int, str] = {}
    columns = {index: [row[index] for row in matrix] for index in range(label_cols)}

    series_col = next(
        (
            index
            for index in range(label_cols - 1, -1, -1)
            if _dominated_by(columns[index], lambda v: P.match_plan_actual_series(v) is not None, 2)
        ),
        None,
    )
    if series_col is not None:
        roles[series_col] = "series"

    remaining = [index for index in range(label_cols) if index not in roles]
    if not remaining:
        return roles, ("series",)

    category_col = remaining[0] if len(remaining) >= 2 else None
    metric_candidates = [index for index in remaining if index != category_col]

    metric_col = next(
        (
            index
            for index in reversed(metric_candidates)
            if _dominated_by(columns[index], lambda v: is_metric_token(v, schema))
        ),
        None,
    )
    if metric_col is None and series_col is None and len(remaining) >= 2:
        metric_col = remaining[-1]
    if metric_col is None and series_col is None and len(remaining) == 1:
        # a lonely column of unknown words names the rows, it does not measure them
        column = columns[remaining[0]]
        if not _dominated_by(column, lambda v: is_metric_token(v, schema)):
            roles[remaining[0]] = "category"
            return roles, ("category",)
        metric_col = remaining[0]

    if metric_col is not None:
        roles[metric_col] = "metric"

    outer = [index for index in remaining if metric_col is None or index < metric_col]
    if outer:
        roles[outer[0]] = "category"
    if len(outer) >= 2:
        roles[outer[1]] = "subcategory"
    for index in outer[2:]:
        roles[index] = "label"

    order = {"category": 0, "subcategory": 1, "metric": 2, "series": 3}
    hierarchy = tuple(
        role for role in sorted((r for r in roles.values() if r in order), key=lambda r: order[r])
    )
    return roles, hierarchy


# --------------------------------------------------------------------------- #
# Metric cycle
# --------------------------------------------------------------------------- #
def find_metric_cycle(written_labels: list[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split the labels of the metric column into repeating metrics and one-offs.

    ``["", "Rej. Lot", "Insp. Lot", "", "Rej. Lot", "Insp. Lot", "SKD", …]``
    -> metrics ``("Rej. Lot", "Insp. Lot")``, sub-groups ``("SKD", …)``.
    """
    counts: dict[str, int] = {}
    for label in written_labels:
        if label:
            counts[label] = counts.get(label, 0) + 1

    repeated = [label for label, count in counts.items() if count >= 2]
    singles = [label for label, count in counts.items() if count == 1]
    if not repeated:
        return (), ()  # nothing repeats: every label names its own row

    order = {label: index for index, label in enumerate(dict.fromkeys(written_labels))}
    return (
        tuple(sorted(repeated, key=lambda label: order[label])),
        tuple(sorted(singles, key=lambda label: order[label])),
    )


# --------------------------------------------------------------------------- #
# Blocks
# --------------------------------------------------------------------------- #
def analyze(
    matrix: list[list[LabelCell]], label_cols: int, schema: DepartmentSchema | None
) -> LabelAnalysis:
    """Full label analysis for the data rows of one table."""
    values = [[cell.value for cell in row] for row in matrix]
    roles, hierarchy = assign_column_roles(values, label_cols, schema)
    analysis = LabelAnalysis(roles=roles, hierarchy=hierarchy)
    if not matrix:
        return analysis

    metric_col = next((index for index, role in roles.items() if role == "metric"), None)
    category_col = next((index for index, role in roles.items() if role == "category"), None)
    subcategory_col = next((index for index, role in roles.items() if role == "subcategory"), None)
    series_col = next((index for index, role in roles.items() if role == "series"), None)

    written_metric_labels = (
        [row[metric_col].value if row[metric_col].written else "" for row in matrix]
        if metric_col is not None
        else []
    )
    cycle, subgroups = find_metric_cycle(written_metric_labels)
    analysis.metric_cycle = cycle
    analysis.subgroups = subgroups

    uses_blocks = bool(cycle) and (
        any(not label for label in written_metric_labels) or bool(subgroups)
    )

    block = -1
    current_subgroup: str | None = None
    for index, row in enumerate(matrix):
        labels = RowLabels()
        metric_written = written_metric_labels[index] if metric_col is not None else ""
        starts_block = index == 0
        if category_col is not None and row[category_col].written:
            starts_block = True
            current_subgroup = None
        if uses_blocks and (not metric_written or metric_written in subgroups):
            starts_block = True
            current_subgroup = metric_written if metric_written in subgroups else None
        if starts_block:
            block += 1
        labels.block = max(block, 0)

        inferred: list[str] = []
        if category_col is not None:
            labels.category = row[category_col].value or None
            if labels.category is None and schema and schema.implicit_group_label:
                labels.category = schema.implicit_group_label
                inferred.append("category")
        if subcategory_col is not None and row[subcategory_col].value:
            labels.subcategory = row[subcategory_col].value
        if current_subgroup:
            labels.subcategory = current_subgroup
        if series_col is not None and row[series_col].value:
            labels.series_type = (
                P.match_plan_actual_series(row[series_col].value) or row[series_col].value
            )

        if metric_col is not None:
            if uses_blocks and (not metric_written or metric_written in subgroups):
                # the headline row of the block: the file does not name it
                if schema and schema.headline_metric:
                    labels.metric = schema.headline_metric
                    inferred.append("metric")
                else:
                    analysis.warnings.append("unnamed_headline_metric")
            else:
                value = row[metric_col].value
                series = P.match_plan_actual_series(value) if value else None
                if series:
                    labels.series_type = series
                elif value:
                    labels.metric = value

        labels.inferred = tuple(inferred)
        analysis.rows.append(labels)

    analysis.blocks = block + 1
    if uses_blocks and subgroups and "subcategory" not in analysis.hierarchy:
        analysis.hierarchy = tuple(
            part
            for part in ("category", "subcategory", "metric", "series")
            if part in analysis.hierarchy or part == "subcategory"
        )
    if any("category" in row.inferred for row in analysis.rows):
        analysis.warnings.append("implicit_group_label")
    if any("metric" in row.inferred for row in analysis.rows):
        analysis.warnings.append("headline_metric_inferred")

    analysis.meta.update(
        {
            "metricCycle": list(cycle),
            "subgroups": list(subgroups),
            "blocks": analysis.blocks,
            "usesBlocks": uses_blocks,
        }
    )
    analysis.warnings = sorted(set(analysis.warnings))
    logger.debug(
        "labels: cycle=%s subgroups=%s blocks=%d roles=%s",
        cycle,
        subgroups,
        analysis.blocks,
        roles,
    )
    return analysis

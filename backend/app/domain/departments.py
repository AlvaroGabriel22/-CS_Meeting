"""Department schemas — configuration, not ``if department == "IQC"``.

The parser is generic: it never needs a schema to work.  A schema only *raises
confidence* — it tells the interpreter that ``SEC`` is a section of IQC and that
``Insp.`` is a metric, so a table that is unusual in shape is still read the way
the department means it.

Adding a department, a section or a metric is a data change here, never a code
change in the parser.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


def canonical(text: str) -> str:
    """Comparison form: accent-free, lowercase, no trailing dots/spaces."""
    value = unicodedata.normalize("NFD", str(text).strip().lower())
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    value = unicodedata.normalize("NFC", value)
    return re.sub(r"[\s._/-]+", " ", value).strip()


@dataclass(frozen=True)
class HeadlineFormula:
    """How the headline metric of a block is derived from its siblings.

    Used to *verify* an inference, never to produce a value: if the block says
    ``Rej. Lot = 139`` and ``Insp. Lot = 20970``, then a headline of ``6629``
    confirms the row really is PPM.  A mismatch raises a warning instead of
    rewriting anything.
    """

    numerator: str
    denominator: str
    scale: float = 1_000_000.0
    tolerance: float = 0.02  # 2% — the file is rounded


@dataclass(frozen=True)
class ChartShare:
    """How a rate is split among the parts that produce it.

    ``PPM`` is a rate, and rates do not add up: stacking the PPM of ``SKD``,
    ``CKD`` and ``Local`` builds a column five to twenty times taller than the
    total it sits under, which says nothing.  What *does* add up is the count
    of rejected lots, so the total PPM is split in that proportion:

        segment = PPM(total) x Rej. Lot(part) / Rej. Lot(total)

    The stack then reads as the total, and each segment is the share that part
    is responsible for.  Both numbers come from the workbook; the split is
    arithmetic on cells the file already holds (ADR-0046).
    """

    #: the rate being split — the metric the chart plots
    whole: str
    #: the countable quantity whose parts really do sum to the whole
    weight: str


@dataclass(frozen=True)
class DepartmentSchema:
    """What is known about one department's raw data."""

    code: str
    label: str
    #: first hierarchy level (``SEC``, ``TNP``, ``TECPLAM`` / ``ASR``, ``CASR``)
    sections: tuple[str, ...] = ()
    #: second level (``Total``, ``TSI``, ``Packing`` / ``MX``, ``Mobile``)
    subgroups: tuple[str, ...] = ()
    #: third level — the measured quantities
    metrics: tuple[str, ...] = ()
    #: tokens that must never be translated by the AI (ADR-0007)
    protected_terms: tuple[str, ...] = ()
    #: name given to a leading block that carries no label of its own
    implicit_group_label: str | None = None
    #: metric of the first row of each block, which the file never spells out
    headline_metric: str | None = None
    #: how to check that inference against the block's other rows
    headline_formula: HeadlineFormula | None = None
    #: table names seen in the corner cell of the header
    tables: tuple[str, ...] = ()
    #: how this department's chart stacks its bars.  ``"stacked"`` draws the
    #: leaf components of each table on top of each other, so the bar reads as
    #: the whole; ``"grouped"`` puts them side by side.  Declared per
    #: department because it depends on whether the components actually add up
    #: — which only the real workbook can tell us (ADR-0037).
    chart_bars: str = "grouped"
    #: what a chart of this department *is*.  ``"components"`` — the parts of
    #: the table as bars with its total as a line (IQC, and the default).
    #: ``"series_pair"`` — one chart per model, its outcome as bars and its
    #: plan as a line (FIELD: Result against Target).  Declared per department
    #: because only the real workbook can say which shape its data has.
    chart_kind: str = "components"
    #: how the bars are scaled when they stack.  ``None`` plots each part's own
    #: figure; a share splits the whole among the parts (ADR-0046).
    chart_share: ChartShare | None = None
    #: True while the structure comes from the specification and no real
    #: workbook has been seen yet — such a schema must not drive decisions
    provisional: bool = False
    notes: str = ""

    _index: dict[str, frozenset[str]] = field(default_factory=dict, repr=False, compare=False)

    def is_section(self, text: str) -> bool:
        return canonical(text) in {canonical(item) for item in self.sections}

    def is_subgroup(self, text: str) -> bool:
        return canonical(text) in {canonical(item) for item in self.subgroups}

    def is_metric(self, text: str) -> bool:
        return canonical(text) in {canonical(item) for item in self.metrics}

#: metrics that appear across every department — used when no schema is known
GENERIC_METRICS: tuple[str, ...] = (
    "PPM",
    "Def.",
    "Def",
    "Defect",
    "Defects",
    "Defect Qty",
    "Insp.",
    "Insp",
    "Inspected",
    "Inspected Qty",
    "Qty",
    "Quantity",
    "Target",
    "Result",
    "Rate",
    "Ratio",
    "Cost",
    "Sales",
    "ASR",
    "CASR",
)

#: never sent to the translation provider (numbers are handled separately)
GLOBAL_PROTECTED_TERMS: tuple[str, ...] = (
    "PPM",
    "SEC",
    "TNP",
    "TECPLAM",
    "IQC",
    "OQC",
    "FIELD",
    "ASR",
    "CASR",
    "TSI",
    "MX",
)

DEPARTMENT_SCHEMAS: dict[str, DepartmentSchema] = {
    # --- IQC: validated against the real workbook (Sprint 1) ---------------- #
    "IQC": DepartmentSchema(
        code="IQC",
        label="Incoming Quality Control",
        tables=("TTL", "SEC", "TNP"),
        sections=("Total", "Imported", "Local"),
        subgroups=("SKD", "CKD"),
        metrics=("PPM", "Rej. Lot", "Insp. Lot"),
        implicit_group_label="Total",
        headline_metric="PPM",
        headline_formula=HeadlineFormula(
            numerator="Rej. Lot", denominator="Insp. Lot", scale=1_000_000.0
        ),
        protected_terms=("PPM", "IQC", "TTL", "SEC", "TNP", "SKD", "CKD"),
        chart_bars="stacked",  # SKD + CKD + Local make up the total
        # PPM is a rate: the stack is the total PPM split by each part's share
        # of the rejected lots, which is what actually adds up (ADR-0046)
        chart_share=ChartShare(whole="PPM", weight="Rej. Lot"),
        notes="Three tables side by side; the PPM row is never labelled.",
    ),
    # --- OQC: no real workbook yet ----------------------------------------- #
    # This one comes from the written specification only.  It is marked
    # provisional on purpose: nothing about it may be treated as known until
    # the real file arrives (Sprint 1 scope decision).
    "OQC": DepartmentSchema(
        code="OQC",
        label="Outgoing Quality Control",
        sections=("SEC", "TNP", "TECPLAM"),
        metrics=("PPM", "Def.", "Insp.", "Target", "Result"),
        protected_terms=("SEC", "TNP", "TECPLAM", "PPM"),
        provisional=True,
        notes="Structure not confirmed — waiting for the real OQC workbook.",
    ),
    # --- FIELD: validated against the real workbook (MX Field KPI) --------- #
    "FIELD": DepartmentSchema(
        code="FIELD",
        label="Field Quality",
        sections=("ASR", "CASR"),
        subgroups=("MX", "Mobile", "APS"),
        metrics=("Target", "Result", "PPM", "Rate"),
        protected_terms=("ASR", "CASR", "MX", "APS"),
        chart_kind="series_pair",  # Result as bars, Target as the line
        notes=(
            "One sheet, one table: ASR and CASR over 2025, 2026 and Jan-Dec, "
            "each model carrying a Target row and a Result row.  A second "
            "header row qualifies the periods (Simulation / Result / Partial); "
            "it annotates the figures and is not a series axis."
        ),
    ),
}


def schema_for(code: str | None) -> DepartmentSchema | None:
    return DEPARTMENT_SCHEMAS.get(str(code).upper()) if code else None


def is_metric_token(text: str, schema: DepartmentSchema | None = None) -> bool:
    """Metric vocabulary check — schema first, generic list as fallback."""
    if schema and schema.is_metric(text):
        return True
    return canonical(text) in {canonical(item) for item in GENERIC_METRICS}


def protected_terms(schema: DepartmentSchema | None = None) -> tuple[str, ...]:
    return tuple(dict.fromkeys(GLOBAL_PROTECTED_TERMS + (schema.protected_terms if schema else ())))

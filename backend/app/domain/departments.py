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
        notes="Three tables side by side; the PPM row is never labelled.",
    ),
    # --- OQC / FIELD: no real workbook yet --------------------------------- #
    # These come from the written specification only.  They are marked
    # provisional on purpose: nothing about them may be treated as known until
    # the real files arrive (Sprint 1 scope decision).
    "OQC": DepartmentSchema(
        code="OQC",
        label="Outgoing Quality Control",
        sections=("SEC", "TNP", "TECPLAM"),
        metrics=("PPM", "Def.", "Insp.", "Target", "Result"),
        protected_terms=("SEC", "TNP", "TECPLAM", "PPM"),
        provisional=True,
        notes="Structure not confirmed — waiting for the real OQC workbook.",
    ),
    "FIELD": DepartmentSchema(
        code="FIELD",
        label="Field Quality",
        sections=("ASR", "CASR"),
        metrics=("Target", "Result", "PPM", "Rate"),
        protected_terms=("ASR", "CASR"),
        provisional=True,
        notes="Structure not confirmed — waiting for the real FIELD workbook.",
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

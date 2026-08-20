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
    "IQC": DepartmentSchema(
        code="IQC",
        label="Incoming Quality Control",
        sections=("SEC", "TNP", "TECPLAM"),
        subgroups=("Total", "TSI", "Packing"),
        metrics=("PPM", "Def.", "Insp.", "Target", "Result"),
        protected_terms=("SEC", "TNP", "TECPLAM", "TSI", "PPM"),
    ),
    "OQC": DepartmentSchema(
        code="OQC",
        label="Outgoing Quality Control",
        sections=("SEC", "TNP", "TECPLAM"),
        subgroups=("Total", "TSI", "Packing"),
        metrics=("PPM", "Def.", "Insp.", "Target", "Result"),
        protected_terms=("SEC", "TNP", "TECPLAM", "TSI", "PPM"),
    ),
    "FIELD": DepartmentSchema(
        code="FIELD",
        label="Field Quality",
        sections=("ASR", "CASR"),
        subgroups=("MX", "Mobile"),
        metrics=("Target", "Result", "PPM", "Rate"),
        protected_terms=("ASR", "CASR", "MX", "Mobile"),
        notes="ASR and CASR usually share one raw data file, side by side.",
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

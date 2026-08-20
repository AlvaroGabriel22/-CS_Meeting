"""Wire contract for raw-data imports."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from .common import CamelModel
from .table import TableSummaryOut

DepartmentLiteral = Literal["IQC", "OQC", "FIELD"]


class RawFileOut(CamelModel):
    id: int
    original_filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    created_at: datetime


class ImportOut(CamelModel):
    id: int
    #: true when an identical file had already been parsed (no re-parse)
    reused: bool = False
    department: DepartmentLiteral
    parser_version: str
    parsed_at: datetime
    summary: dict[str, Any] = {}
    warnings: list[str] = []
    raw_file: RawFileOut | None = None
    tables: list[TableSummaryOut] = []

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
    """The result of an upload: what was parsed and which snapshot it became."""

    success: bool = True
    id: int
    #: true when an identical file had already been parsed (no re-parse)
    reused: bool = False
    department: DepartmentLiteral
    parser_version: str
    parsed_at: datetime
    #: the snapshot this upload created (null when ``createVersion=false``)
    presentation_id: int | None = None
    version_id: int | None = None
    version_number: int | None = None
    #: names of the detected tables, in file order — "TTL", "SEC", "TNP"
    table_names: list[str] = []
    #: period labels, in file order — "'25", "'26", "1Q", "2Q", "3Q", "Aug"
    periods: list[str] = []
    summary: dict[str, Any] = {}
    warnings: list[str] = []
    raw_file: RawFileOut | None = None
    tables: list[TableSummaryOut] = []

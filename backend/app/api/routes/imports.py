"""Raw-data upload and inspection endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.db.base import get_session
from app.db.models import Department, DepartmentData, TableDefinition
from app.schemas.imports import ImportOut
from app.schemas.table import InterpretationOut, TableOut, TableViewOut
from app.services import presentation_service, serializers
from app.services.import_service import import_raw_data
from app.services.interpretation import interpretation_view
from app.services.render_model import build_table_view

router = APIRouter(prefix="/api", tags=["raw data"])


async def _handle_upload(
    department: Department,
    file: UploadFile,
    force: bool,
    create_version: bool,
    session: Session,
) -> ImportOut:
    payload = await file.read()
    result = import_raw_data(
        session,
        department=department,
        filename=file.filename or "upload.xlsx",
        content_type=file.content_type,
        payload=payload,
        force_reparse=force,
    )
    session.flush()

    version = None
    if create_version:
        version = presentation_service.snapshot_for_import(
            session, department=department, data=result.data
        )
        session.flush()
    return serializers.import_out(result.data, reused=result.reused, version=version)


@router.post("/uploads", response_model=ImportOut, status_code=201)
async def create_upload(
    department: Department = Form(...),
    file: UploadFile = File(...),
    force: bool = Form(False),
    # the wire format is camelCase everywhere, form fields included
    create_version: bool = Form(True, alias="createVersion"),
    session: Session = Depends(get_session),
) -> ImportOut:
    """Upload a raw workbook: validated, stored, parsed, persisted, snapshotted.

    * an identical file (same content hash, same parser version) is not parsed
      twice — the previous import comes back with ``reused: true``
      (``force=true`` parses anyway);
    * ``createVersion=false`` parses and returns the preview **without** adding
      a version, which is what the import screen uses before the user confirms.
      The confirmation call costs nothing extra thanks to the reuse above.
    """
    return await _handle_upload(department, file, force, create_version, session)


@router.post("/imports", response_model=ImportOut, status_code=201, include_in_schema=False)
async def create_import(
    department: Department = Form(...),
    file: UploadFile = File(...),
    force: bool = Form(False),
    # the wire format is camelCase everywhere, form fields included
    create_version: bool = Form(True, alias="createVersion"),
    session: Session = Depends(get_session),
) -> ImportOut:
    """Alias of ``POST /api/uploads`` (kept so both names work)."""
    return await _handle_upload(department, file, force, create_version, session)


@router.get("/imports", response_model=list[ImportOut])
def list_imports(
    department: Department | None = None,
    limit: int = 20,
    session: Session = Depends(get_session),
) -> list[ImportOut]:
    query = select(DepartmentData).order_by(DepartmentData.id.desc()).limit(min(limit, 100))
    if department:
        query = query.where(DepartmentData.department == department)
    return [serializers.import_out(data) for data in session.scalars(query)]


@router.get("/imports/{import_id}", response_model=ImportOut)
def get_import(import_id: int, session: Session = Depends(get_session)) -> ImportOut:
    data = session.get(DepartmentData, import_id)
    if data is None:
        raise NotFound("Import not found", {"importId": import_id})
    return serializers.import_out(data)


def _table_or_404(session: Session, import_id: int, table_id: int) -> TableDefinition:
    definition = session.get(TableDefinition, table_id)
    if definition is None or definition.department_data_id != import_id:
        raise NotFound("Table not found", {"importId": import_id, "tableId": table_id})
    return definition


@router.get("/imports/{import_id}/tables/{table_id}", response_model=TableOut)
def get_table(import_id: int, table_id: int, session: Session = Depends(get_session)) -> TableOut:
    """The full normalized table — cells included (heavy; use for rendering)."""
    return serializers.table_out(_table_or_404(session, import_id, table_id))


@router.get("/imports/{import_id}/tables/{table_id}/interpretation", response_model=InterpretationOut)
def get_interpretation(
    import_id: int,
    table_id: int,
    max_rows: int | None = None,
    session: Session = Depends(get_session),
) -> InterpretationOut:
    """The semantic view: periods, hierarchy and values, no coordinates.

    Light enough to inspect by hand and to feed charts.
    """
    table = serializers.table_out(_table_or_404(session, import_id, table_id))
    return InterpretationOut.model_validate(interpretation_view(table, max_rows=max_rows))


@router.get("/imports/{import_id}/tables/{table_id}/view", response_model=TableViewOut)
def get_table_view(
    import_id: int, table_id: int, session: Session = Depends(get_session)
) -> TableViewOut:
    """The table prepared for display: merges as spans, hierarchy as depth.

    The UI draws this as it comes — it never re-derives structure from rows and
    columns, and no period is known to it in advance.
    """
    table = serializers.table_out(_table_or_404(session, import_id, table_id))
    return TableViewOut.model_validate(build_table_view(table))

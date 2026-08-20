"""Raw-data import endpoints (Sprint 0 slice of the API)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.db.base import get_session
from app.db.models import Department, DepartmentData, TableDefinition
from app.schemas.imports import ImportOut
from app.schemas.table import TableOut
from app.services import serializers
from app.services.import_service import import_raw_data

router = APIRouter(prefix="/api/imports", tags=["imports"])


@router.post("", response_model=ImportOut, status_code=201)
async def create_import(
    department: Department = Form(...),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> ImportOut:
    payload = await file.read()
    data = import_raw_data(
        session,
        department=department,
        filename=file.filename or "upload.xlsx",
        content_type=file.content_type,
        payload=payload,
    )
    session.flush()
    return serializers.import_out(data)


@router.get("", response_model=list[ImportOut])
def list_imports(
    department: Department | None = None,
    limit: int = 20,
    session: Session = Depends(get_session),
) -> list[ImportOut]:
    query = select(DepartmentData).order_by(DepartmentData.id.desc()).limit(min(limit, 100))
    if department:
        query = query.where(DepartmentData.department == department)
    return [serializers.import_out(data) for data in session.scalars(query)]


@router.get("/{import_id}", response_model=ImportOut)
def get_import(import_id: int, session: Session = Depends(get_session)) -> ImportOut:
    data = session.get(DepartmentData, import_id)
    if data is None:
        raise NotFound("Import not found", {"importId": import_id})
    return serializers.import_out(data)


@router.get("/{import_id}/tables/{table_id}", response_model=TableOut)
def get_table(import_id: int, table_id: int, session: Session = Depends(get_session)) -> TableOut:
    definition = session.get(TableDefinition, table_id)
    if definition is None or definition.department_data_id != import_id:
        raise NotFound("Table not found", {"importId": import_id, "tableId": table_id})
    return serializers.table_out(definition)

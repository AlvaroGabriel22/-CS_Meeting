"""The department page and its configuration.

Reading is the presentation screen: charts, tables, report.  Writing happens on
the configuration screen — the upload, the titles and the report editor — so the
page a meeting looks at carries no buttons of its own (ADR-0038).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import NotFound, ValidationError
from app.domain.glossary import translate_term
from app.db.base import get_session
from app.db.models import (
    Department,
    DepartmentSettings,
    PresentationVersion,
    VersionReport,
)
from app.schemas.report import (
    ChartsResponseOut,
    DepartmentSettingsIn,
    DepartmentSettingsOut,
    ReportOut,
    ReportSaveIn,
    ReportSummaryOut,
    TranslationOut,
    UploadedImageOut,
)
from app.schemas.table import TableOut
from app.services import assets, charts, presentation_service, reports, serializers
from app.services.translation import TranslationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["page"])


def _tables_of(version: PresentationVersion) -> list[TableOut]:
    return [
        serializers.table_out(definition)
        for data in version.imports
        for definition in sorted(data.tables, key=lambda item: item.order_index)
    ]


def _department_of(version: PresentationVersion) -> str:
    return version.imports[0].department.value if version.imports else "IQC"


def _settings_of(session: Session, department: str) -> DepartmentSettings:
    code = Department(department)
    found = session.scalars(
        select(DepartmentSettings).where(DepartmentSettings.department == code).limit(1)
    ).first()
    if found is None:
        found = DepartmentSettings(department=code, chart_titles={}, table_titles={})
        session.add(found)
        session.flush()
    return found


def _report_out(report: VersionReport | None, version: PresentationVersion) -> ReportOut:
    department = _department_of(version)
    if report is None:
        return ReportOut(
            version_id=version.id,
            department=department,
            version_number=version.number,
            version_label=version.label,
            content=reports.empty_content(),
        )
    return ReportOut(
        version_id=report.version_id,
        department=department,
        version_number=version.number,
        version_label=version.label,
        language=report.language,
        content=report.content or reports.empty_content(),
        text=report.text or "",
        translation_key=report.translation_key,
        media=[
            {
                "id": media.id,
                "assetId": media.asset_id,
                "url": f"/api/assets/{media.asset_id}",
                "mimeType": media.asset.mime_type,
                "sizeBytes": media.asset.size_bytes,
                "caption": media.caption,
            }
            for media in report.media
        ],
        updated_at=report.updated_at,
    )


# --------------------------------------------------------------------------- #
# Charts
# --------------------------------------------------------------------------- #
@router.get("/versions/{version_id}/charts", response_model=ChartsResponseOut)
def get_charts(version_id: int, session: Session = Depends(get_session)) -> ChartsResponseOut:
    """One chart per table, in the workbook's order.

    The parts of each table as bars — stacked when the department says they add
    up — and its total as a line, from values the file already holds.
    """
    version = presentation_service.get_version(session, version_id)
    department = _department_of(version)
    stored = _settings_of(session, department)
    titles = stored.chart_titles or {}
    built = charts.build_charts(
        _tables_of(version), department=department, configured=stored.chart_series or {}
    )
    session.commit()

    payload = []
    for chart in built["charts"]:
        # a chart is named by its own id; settings written when a table meant
        # exactly one chart are still found under the table's name
        payload.append(
            {**chart, "title": titles.get(chart["id"]) or titles.get(chart["table"]) or None}
        )
    return ChartsResponseOut.model_validate(
        {
            "versionId": version.id,
            "department": department,
            "metric": built["metric"],
            "charts": payload,
        }
    )


# --------------------------------------------------------------------------- #
# The report
# --------------------------------------------------------------------------- #
@router.get("/versions/{version_id}/report", response_model=ReportOut)
def get_report(version_id: int, session: Session = Depends(get_session)) -> ReportOut:
    """The report of this snapshot — empty until someone builds it."""
    version = presentation_service.get_version(session, version_id)
    return _report_out(reports.get_report(session, version.id), version)


@router.put("/versions/{version_id}/report", response_model=ReportOut)
def save_report(
    version_id: int, payload: ReportSaveIn, session: Session = Depends(get_session)
) -> ReportOut:
    """Save the table the author built, exactly as they built it."""
    version = presentation_service.get_version(session, version_id)
    report = reports.save_report(
        session, version=version, content=payload.content, language=payload.language
    )
    session.commit()
    return _report_out(report, version)


@router.post("/versions/{version_id}/report/media", response_model=UploadedImageOut)
async def upload_report_image(
    version_id: int,
    file: UploadFile = File(...),
    caption: str | None = Form(None),
    session: Session = Depends(get_session),
) -> UploadedImageOut:
    """Upload an image so the author can place it in a cell.

    Validated by magic number, not by the name the browser sent.  The image is
    registered against the report, so it is never orphaned on disk.
    """
    version = presentation_service.get_version(session, version_id)
    report = reports.get_report(session, version.id)
    if report is None:
        report = reports.save_report(session, version=version, content=reports.empty_content())

    payload = await file.read()
    asset = assets.store_image(
        session, filename=file.filename or "image", content_type=file.content_type, payload=payload
    )
    reports.attach_media(session, report, asset, caption)
    session.commit()
    return UploadedImageOut(
        asset_id=asset.id,
        url=f"/api/assets/{asset.id}",
        mime_type=asset.mime_type,
        size_bytes=asset.size_bytes,
    )


@router.post("/versions/{version_id}/translation", response_model=TranslationOut)
def translate_authored_text(
    version_id: int, payload: dict, session: Session = Depends(get_session)
) -> TranslationOut:
    """Translate everything a person wrote about this snapshot.

    That is the report — its title, its column names, its text and its image
    captions — plus the titles given to the charts and tables in the
    configuration.  Those are the only strings the system cannot know in
    advance; the rest of the page ships in three languages and the labels
    inside the tables belong to the workbook, so neither is ever sent anywhere
    (ADR-0039).

    The stored content is not modified: the translation comes back beside the
    original, and a line whose data tokens changed keeps the author's words
    (ADR-0035).  Works the same for every department — the department only
    decides which technical terms are masked out of the request.
    """
    settings = get_settings()
    target = str(payload.get("targetLanguage") or "")
    if target not in settings.supported_languages:
        raise ValidationError(
            "This language is not supported",
            {"targetLanguage": target, "supported": list(settings.supported_languages)},
        )

    version = presentation_service.get_version(session, version_id)
    department = _department_of(version)
    report = reports.get_report(session, version.id)
    content = (report.content if report else None) or reports.empty_content()
    stored = _settings_of(session, department)
    chart_titles = dict(stored.chart_titles or {})
    table_titles = dict(stored.table_titles or {})

    source = str(
        payload.get("sourceLanguage")
        or (report.language if report else settings.default_language)
    )

    strings = reports.translatable_strings(content)
    strings.extend(title for title in chart_titles.values() if title)
    strings.extend(title for title in table_titles.values() if title)

    outcome = TranslationService().translate_texts(
        session,
        list(dict.fromkeys(strings)),
        source_language=source,
        target_language=target,
        department=department,
    )
    session.commit()

    mapping = outcome.mapping
    logger.info(
        "version %d: %d authored string(s) %s -> %s via %s (%d cached, %d rejected)",
        version.id,
        len(strings),
        source,
        target,
        outcome.provider,
        sum(1 for entry in outcome.entries if entry.cached),
        sum(1 for entry in outcome.entries if entry.rejected),
    )
    return TranslationOut(
        version_id=version.id,
        department=department,
        source_language=source,
        target_language=target,
        provider=outcome.provider,
        model=outcome.model,
        original=content,
        translated=reports.apply_translation(content, mapping),
        chart_titles={key: mapping.get(value, value) for key, value in chart_titles.items()},
        table_titles={key: mapping.get(value, value) for key, value in table_titles.items()},
        string_count=len(outcome.entries),
        cached_count=sum(1 for entry in outcome.entries if entry.cached),
        rejected_count=sum(1 for entry in outcome.entries if entry.rejected),
    )


# --------------------------------------------------------------------------- #
# The reports library
# --------------------------------------------------------------------------- #
@router.get("/reports", response_model=list[ReportSummaryOut])
def list_reports(
    department: str | None = Query(None),
    language: str | None = Query(None),
    session: Session = Depends(get_session),
) -> list[ReportSummaryOut]:
    """Every report that has been saved, newest first, ready to download.

    ``language`` renders the titles for the reader.  A title is authored text —
    nobody knows it before somebody types it — so it goes through the
    translation layer, cache first and all the titles in one request, which is
    what a three-a-minute quota needs (ADR-0039, ADR-0042).  The department and
    the period come from the glossary instead, because those are decided terms
    (ADR-0044).
    """
    query = select(VersionReport).order_by(VersionReport.updated_at.desc())
    found = list(session.scalars(query))

    summaries: list[ReportSummaryOut] = []
    to_translate: list[str] = []
    for report in found:
        version = report.version
        if version is None:  # pragma: no cover - a report always has its version
            continue
        code = _department_of(version)
        if department and code != department:
            continue
        content = report.content or {}
        title = content.get("title") or ""
        if language and title and report.language != language:
            to_translate.append(title)
        summaries.append(
            ReportSummaryOut(
                version_id=report.version_id,
                department=code,
                version_number=version.number,
                version_label=translate_term(version.label, language),
                title=title,
                column_count=len(content.get("columns") or []),
                row_count=len(content.get("rows") or []),
                image_count=len(report.media),
                language=report.language,
                updated_at=report.updated_at,
            )
        )

    if to_translate:
        # every title in one request: N rows must not become N calls
        source = found[0].language if found else "en"
        outcome = TranslationService().translate_texts(
            session,
            list(dict.fromkeys(to_translate)),
            source_language=source,
            target_language=language or source,
            department=department or "IQC",
        )
        session.commit()
        mapping = outcome.mapping
        for summary in summaries:
            summary.title = mapping.get(summary.title, summary.title)

    return summaries


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
@router.get("/departments/{code}/settings", response_model=DepartmentSettingsOut)
def get_department_settings(
    code: str, session: Session = Depends(get_session)
) -> DepartmentSettingsOut:
    """What this department's charts and tables are called."""
    settings = _settings_of(session, _valid_department(code))
    session.commit()
    return DepartmentSettingsOut(
        department=settings.department.value,
        chart_titles=settings.chart_titles or {},
        table_titles=settings.table_titles or {},
        chart_series=settings.chart_series or {},
    )


@router.put("/departments/{code}/settings", response_model=DepartmentSettingsOut)
def save_department_settings(
    code: str, payload: DepartmentSettingsIn, session: Session = Depends(get_session)
) -> DepartmentSettingsOut:
    """Name the charts and tables, and choose what each chart plots.

    The numbers under them are never editable: a composition selects *which*
    rows of the workbook to draw, never what they say (ADR-0041).
    """
    settings = _settings_of(session, _valid_department(code))
    settings.chart_titles = {
        key: value.strip() for key, value in payload.chart_titles.items() if value.strip()
    }
    settings.table_titles = {
        key: value.strip() for key, value in payload.table_titles.items() if value.strip()
    }
    settings.chart_series = {
        chart: {"bars": list(choice.bars), "line": choice.line, "enabled": choice.enabled}
        for chart, choice in payload.chart_series.items()
        if choice.bars or choice.line or choice.enabled is not None
    }
    session.commit()
    logger.info(
        "settings saved for %s: %d chart title(s), %d table title(s), %d composition(s)",
        settings.department.value,
        len(settings.chart_titles),
        len(settings.table_titles),
        len(settings.chart_series),
    )
    return DepartmentSettingsOut(
        department=settings.department.value,
        chart_titles=settings.chart_titles,
        table_titles=settings.table_titles,
        chart_series=settings.chart_series,
    )


def _valid_department(code: str) -> str:
    try:
        return Department(code.upper()).value
    except ValueError as exc:
        raise NotFound("Unknown department", {"department": code}) from exc


# --------------------------------------------------------------------------- #
# Images
# --------------------------------------------------------------------------- #
@router.get("/assets/{asset_id}")
def get_asset(asset_id: int, session: Session = Depends(get_session)) -> FileResponse:
    """Serve one stored image."""
    asset = assets.get_asset(session, asset_id)
    path = assets.absolute_path(asset)
    if not path.exists():  # pragma: no cover - the row exists, the file does not
        raise NotFound("Asset file not found", {"assetId": asset_id})
    return FileResponse(path, media_type=asset.mime_type, filename=asset.original_filename)

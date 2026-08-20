"""Assets: images on disk, metadata in SQLite (ADR-0005 of the master prompt).

The bytes never enter the database. An asset is addressed by the hash of its
content, so the same screenshot attached twice is stored once.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import NotFound
from app.db.models import Asset
from app.services import storage

logger = logging.getLogger(__name__)


def store_image(
    session: Session, *, filename: str, content_type: str | None, payload: bytes
) -> Asset:
    """Validate, write to disk and register one image."""
    mime_type = storage.validate_image_upload(filename, content_type, payload)
    path, digest = storage.store_asset(payload, mime_type)

    existing = session.scalars(select(Asset).where(Asset.sha256 == digest)).first()
    if existing is not None:
        return existing  # same bytes, same asset

    asset = Asset(
        sha256=digest,
        stored_path=storage.relative_to_data(path),
        mime_type=mime_type,
        size_bytes=len(payload),
        original_filename=Path(filename).name,
    )
    session.add(asset)
    session.flush()
    logger.info("registered asset %d (%s, %d bytes)", asset.id, mime_type, len(payload))
    return asset


def get_asset(session: Session, asset_id: int) -> Asset:
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise NotFound("Asset not found", {"assetId": asset_id})
    return asset


def absolute_path(asset: Asset) -> Path:
    """Where the bytes live, resolved inside the data directory."""
    settings = get_settings()
    path = (settings.data_dir / asset.stored_path).resolve()
    if not str(path).startswith(str(settings.data_dir.resolve())):  # pragma: no cover
        raise NotFound("Asset file not found", {"assetId": asset.id})
    return path

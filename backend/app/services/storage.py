"""Safe file storage for uploads.

Uploaded names are never trusted: the stored name is derived from the content
hash, the extension is validated against an allow-list and the resolved path is
checked to stay inside the data directory (no path traversal).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import get_settings
from app.core.errors import UploadRejected

logger = logging.getLogger(__name__)

#: xlsx/xlsm are ZIP containers — every valid file starts with "PK"
ZIP_MAGIC = b"PK\x03\x04"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def safe_extension(filename: str, allowed: tuple[str, ...]) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in allowed:
        raise UploadRejected(
            "File type not allowed", {"filename": filename, "allowed": list(allowed)}
        )
    return suffix


def validate_raw_upload(filename: str, content_type: str | None, payload: bytes) -> str:
    """Validate a raw-data upload and return the safe extension."""
    settings = get_settings()
    suffix = safe_extension(filename, settings.allowed_raw_extensions)
    limit = settings.max_upload_mb * 1024 * 1024
    if len(payload) == 0:
        raise UploadRejected("Empty file")
    if len(payload) > limit:
        raise UploadRejected(
            "File too large", {"sizeBytes": len(payload), "limitBytes": limit}
        )
    if content_type and content_type not in settings.allowed_raw_mimetypes:
        raise UploadRejected("Unexpected content type", {"contentType": content_type})
    if not payload.startswith(ZIP_MAGIC):
        raise UploadRejected("File does not look like a real .xlsx workbook")
    return suffix


def store_raw_file(payload: bytes, suffix: str, department: str) -> tuple[Path, str]:
    """Write the upload under ``data/raw/<department>/`` and return (path, sha256).

    Identical content is stored once — re-uploading the same file is cheap and
    keeps provenance stable.
    """
    settings = get_settings()
    digest = sha256_bytes(payload)
    folder = settings.raw_dir / department
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    path = folder / f"{stamp}-{digest[:12]}{suffix}"
    resolved = path.resolve()
    if not str(resolved).startswith(str(settings.data_dir.resolve())):  # pragma: no cover
        raise UploadRejected("Refusing to write outside the data directory")
    if not resolved.exists():
        resolved.write_bytes(payload)
        logger.info("stored raw file %s (%d bytes)", resolved.name, len(payload))
    return resolved, digest


def relative_to_data(path: Path) -> str:
    settings = get_settings()
    try:
        return str(path.resolve().relative_to(settings.data_dir.resolve()))
    except ValueError:  # pragma: no cover - defensive
        return str(path)

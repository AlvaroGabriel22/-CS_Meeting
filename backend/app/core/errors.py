"""Domain errors mapped to HTTP responses in ``app.main``."""

from __future__ import annotations


class AppError(Exception):
    code = "app_error"
    status_code = 400

    def __init__(self, message: str, detail: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class ValidationError(AppError):
    code = "validation_error"
    status_code = 422


class UploadRejected(AppError):
    code = "upload_rejected"
    status_code = 400


class ParseError(AppError):
    code = "parse_error"
    status_code = 422


class NotFound(AppError):
    code = "not_found"
    status_code = 404


class LimitReached(AppError):
    """The 8-presentation ceiling: the user must archive, replace or delete."""

    code = "limit_reached"
    status_code = 409

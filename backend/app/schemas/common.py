"""Shared contract primitives.

The wire format is camelCase (TypeScript friendly); Python stays snake_case.
Keep ``frontend/src/types/api.ts`` in sync with this package — it is the single
contract between backend and frontend.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


def to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(word.capitalize() for word in tail)


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class ErrorResponse(CamelModel):
    code: str
    message: str
    detail: dict | None = None

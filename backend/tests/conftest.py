"""Test harness.

Fixtures are *generated* into a temporary directory (see
``tests/fixtures/build_fixtures.py``) and the whole application is pointed at a
throw-away data directory, so tests never touch the developer's database.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_TMP_DATA = Path(tempfile.mkdtemp(prefix="cs-meeting-tests-"))
os.environ["CSM_DATA_DIR"] = str(_TMP_DATA)
os.environ["CSM_DATABASE_URL"] = f"sqlite:///{_TMP_DATA / 'test.db'}"

from app.db.base import Base, engine  # noqa: E402
from app.db import models  # noqa: E402,F401
from tests.fixtures.build_fixtures import build_all  # noqa: E402

Base.metadata.create_all(engine)


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    target = _TMP_DATA / "fixtures"
    build_all(target)
    return target


@pytest.fixture(scope="session")
def fixture_files(fixtures_dir: Path) -> dict[str, Path]:
    return {path.name: path for path in sorted(fixtures_dir.glob("*.xlsx"))}


@pytest.fixture()
def session():
    from app.db.base import SessionLocal

    db = SessionLocal()
    try:
        yield db
        db.rollback()
    finally:
        db.close()


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client

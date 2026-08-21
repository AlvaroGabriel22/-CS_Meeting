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
# the developer's .env must not change what the suite proves: a test that wants
# a translation engine registers its own, and the default is always "no engine"
os.environ["CSM_TRANSLATION_PROVIDER"] = "null"
os.environ["CSM_ANTHROPIC_API_KEY"] = ""

from app.db.base import Base, engine  # noqa: E402
from app.db import models  # noqa: E402,F401
from tests.fixtures.build_fixtures import build_all  # noqa: E402
from tests.fixtures.build_iqc_fixtures import build_all as build_iqc_all  # noqa: E402

REAL_DIR = Path(__file__).parent / "fixtures" / "real"

Base.metadata.create_all(engine)


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    target = _TMP_DATA / "fixtures"
    build_all(target)
    return target


@pytest.fixture(scope="session")
def fixture_files(fixtures_dir: Path) -> dict[str, Path]:
    return {path.name: path for path in sorted(fixtures_dir.glob("*.xlsx"))}


@pytest.fixture(scope="session")
def iqc_real() -> Path:
    """The official IQC workbook — the reference structure of Sprint 1."""
    path = REAL_DIR / "RawdataIQC.xlsx"
    if not path.exists():
        pytest.skip("the real IQC workbook is not available in tests/fixtures/real/")
    return path


@pytest.fixture(scope="session")
def iqc_evolution() -> dict[str, Path]:
    """Synthetic IQC workbooks whose period axis evolves month after month."""
    target = _TMP_DATA / "iqc-evolution"
    build_iqc_all(target)
    return {path.stem.rsplit("_", 1)[-1]: path for path in sorted(target.glob("*.xlsx"))}


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


@pytest.fixture(autouse=True)
def clean_department_settings():
    """Settings are global per department, so one test must not leak into another.

    Everything else in the schema is append-only and scoped to a version; the
    titles are the one piece of shared configuration.
    """
    from app.db.base import SessionLocal
    from app.db.models import DepartmentSettings

    yield
    session = SessionLocal()
    try:
        session.query(DepartmentSettings).delete()
        session.commit()
    finally:
        session.close()

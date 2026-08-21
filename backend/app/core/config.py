"""Application settings (env-driven, no secret ever reaches the frontend)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CSM_", extra="ignore")

    app_name: str = "CS Meeting"
    debug: bool = False

    # --- storage ---------------------------------------------------------- #
    data_dir: Path = BACKEND_DIR / "data"
    database_url: str = ""  # defaults to sqlite in data_dir

    # --- business rules --------------------------------------------------- #
    max_active_presentations: int = 8
    trash_retention_days: int = 30

    # --- uploads ---------------------------------------------------------- #
    max_upload_mb: int = 25
    allowed_raw_extensions: tuple[str, ...] = (".xlsx", ".xlsm")
    allowed_raw_mimetypes: tuple[str, ...] = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel.sheet.macroEnabled.12",
        "application/octet-stream",  # some browsers send this for .xlsx
    )
    #: the file is stored as uploaded, never re-encoded, so this is a limit
    #: on size and never on quality
    max_image_mb: int = 15
    allowed_image_mimetypes: tuple[str, ...] = ("image/png", "image/jpeg", "image/webp", "image/gif")

    # --- translation ------------------------------------------------------ #
    #: null (returns the source) | anthropic (remote) | ollama (this machine)
    translation_provider: str = "null"
    translation_model: str = "claude-sonnet-5"
    anthropic_api_key: str | None = None
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "gemma4:12b"

    # --- i18n ------------------------------------------------------------- #
    default_language: str = "en"
    supported_languages: tuple[str, ...] = ("en", "pt-BR", "ko")

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def assets_dir(self) -> Path:
        return self.data_dir / "assets"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def sqlalchemy_url(self) -> str:
        return self.database_url or f"sqlite:///{self.data_dir / 'cs_meeting.db'}"

    def ensure_dirs(self) -> None:
        for path in (self.data_dir, self.raw_dir, self.assets_dir, self.exports_dir):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings

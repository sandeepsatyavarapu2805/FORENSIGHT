from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL, make_url

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
DEFAULT_UPLOAD_STORAGE_PATH = Path(__file__).resolve().parents[1] / "var" / "uploads"


class Settings(BaseSettings):
    db_user: str | None = None
    db_password: SecretStr | None = None
    db_host: str | None = None
    db_port: int | None = None
    db_name: str | None = None
    render_database_url: SecretStr | None = Field(
        default=None, validation_alias="DATABASE_URL"
    )

    frontend_origin: str
    session_cookie_secure: bool = False
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    session_lifetime_hours: int = 12
    upload_storage_path: Path = DEFAULT_UPLOAD_STORAGE_PATH
    upload_max_bytes: int = 536_870_912
    archive_max_members: int = 100_000
    archive_max_uncompressed_bytes: int = 2_147_483_648
    archive_max_compression_ratio: int = 1_000
    archive_max_report_xml_bytes: int = 268_435_456
    ai_provider: str = "disabled"
    ai_api_key: SecretStr | None = None
    ai_model: str | None = None
    ai_base_url: str = "https://api.openai.com/v1"
    ai_timeout_seconds: float = 20.0
    ai_context_max_items: int = 12
    ai_context_excerpt_chars: int = 1_000
    ai_context_data_chars: int = 1_500

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def database_url(self) -> URL:
        if self.render_database_url is not None:
            url = make_url(self.render_database_url.get_secret_value())
            if url.drivername in {"postgres", "postgresql"}:
                url = url.set(drivername="postgresql+psycopg")
            return url
        if not all(
            (self.db_user, self.db_password, self.db_host, self.db_port, self.db_name)
        ):
            raise ValueError("DATABASE_URL or all DB_* settings are required")
        assert self.db_password is not None
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )


settings = Settings()  # type: ignore[call-arg]

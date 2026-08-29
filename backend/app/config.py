from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
DEFAULT_UPLOAD_STORAGE_PATH = Path(__file__).resolve().parents[1] / "var" / "uploads"


class Settings(BaseSettings):
    db_user: str
    db_password: SecretStr
    db_host: str
    db_port: int
    db_name: str

    frontend_origin: str
    session_cookie_secure: bool = False
    session_lifetime_hours: int = 12
    upload_storage_path: Path = DEFAULT_UPLOAD_STORAGE_PATH
    upload_max_bytes: int = 536_870_912
    archive_max_members: int = 100_000
    archive_max_uncompressed_bytes: int = 2_147_483_648
    archive_max_compression_ratio: int = 1_000
    archive_max_report_xml_bytes: int = 268_435_456

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def database_url(self) -> URL:
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )


settings = Settings()  # type: ignore[call-arg]

from app.config import Settings, settings


def test_required_settings_are_loaded() -> None:
    assert settings.frontend_origin
    assert settings.db_user
    assert settings.db_host
    assert settings.db_port
    assert settings.db_name
    assert settings.db_password.get_secret_value()


def test_render_database_url_uses_psycopg_driver() -> None:
    configured = Settings(
        _env_file=None,
        frontend_origin="https://forensight-web.onrender.com",
        DATABASE_URL="postgresql://user:secret@db.example/forensight",
    )
    assert configured.database_url().drivername == "postgresql+psycopg"
    assert configured.database_url().password == "secret"

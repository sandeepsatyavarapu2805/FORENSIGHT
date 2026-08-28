from app.config import settings


def test_required_settings_are_loaded() -> None:
    assert settings.frontend_origin
    assert settings.db_user
    assert settings.db_host
    assert settings.db_port
    assert settings.db_name
    assert settings.db_password.get_secret_value()
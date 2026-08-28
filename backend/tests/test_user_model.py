from app.models.user import User


def test_user_model_table_name() -> None:
    assert User.__tablename__ == "users"


def test_user_model_required_columns() -> None:
    expected_columns = {
        "id",
        "username",
        "password_hash",
        "display_name",
        "is_active",
        "created_at",
        "updated_at",
    }

    assert expected_columns == set(User.__table__.columns.keys())
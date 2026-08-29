from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

from app.db.session import engine


def test_database_is_at_migration_head_with_expected_tables() -> None:
    scripts = ScriptDirectory("migrations")
    expected_head = scripts.get_current_head()

    with engine.connect() as connection:
        current_revision = MigrationContext.configure(connection).get_current_revision()
        table_names = set(inspect(connection).get_table_names())

    assert current_revision == expected_head
    assert {
        "alembic_version",
        "users",
        "cases",
        "evidence_sources",
        "auth_sessions",
        "processing_jobs",
        "evidence_items",
    } == table_names

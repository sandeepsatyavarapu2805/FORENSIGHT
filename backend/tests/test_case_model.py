from app.models.case import Case
from app.models.user import User


def test_case_model_columns() -> None:
    assert Case.__tablename__ == "cases"
    assert set(Case.__table__.columns.keys()) == {
        "id",
        "case_identifier",
        "name",
        "description",
        "owner_id",
        "case_kind",
        "parent_case_id",
        "evidence_case_id",
        "source_grant_id",
        "created_at",
        "updated_at",
    }


def test_user_case_relationship() -> None:
    assert User.cases.property.back_populates == "owner"
    assert Case.owner.property.back_populates == "cases"

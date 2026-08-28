from app.security import hash_password, verify_password


def test_password_hashing_uses_argon2_and_verifies() -> None:
    password_hash = hash_password("a strong test password")

    assert password_hash.startswith("$argon2id$")
    assert "a strong test password" not in password_hash
    assert verify_password("a strong test password", password_hash)
    assert not verify_password("wrong password", password_hash)

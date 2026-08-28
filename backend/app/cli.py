import argparse
import getpass

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.user import User
from app.security import hash_password


def create_investigator(username: str, display_name: str) -> None:
    username = username.strip().lower()
    password = getpass.getpass("Password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match")
    if len(password) < 12:
        raise SystemExit("Password must be at least 12 characters")

    with SessionLocal() as db:
        if db.scalar(select(User).where(User.username == username)):
            raise SystemExit("Username already exists")
        db.add(
            User(
                username=username,
                display_name=display_name.strip(),
                password_hash=hash_password(password),
            )
        )
        db.commit()
    print(f"Created investigator {username}")


def main() -> None:
    parser = argparse.ArgumentParser(description="ForenSight administration")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create-investigator")
    create.add_argument("username")
    create.add_argument("display_name")
    args = parser.parse_args()
    if args.command == "create-investigator":
        create_investigator(args.username, args.display_name)


if __name__ == "__main__":
    main()

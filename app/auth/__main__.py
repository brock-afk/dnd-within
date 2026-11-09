import argparse
import sys
from getpass import getpass

from app import models  # noqa: F401
from app.auth.form import RegisterForm
from app.auth.models import User
from app.auth.service import Refusal, create_admin, grant_admin
from app.core.db import SessionLocal


def create(form: RegisterForm) -> int:
    with SessionLocal() as db:
        outcome = create_admin(db, form)
        if not isinstance(outcome, User):
            print(outcome.value if isinstance(outcome, Refusal) else outcome)
            return 1
        db.commit()
    print(f"{outcome.username} is an admin.")
    return 0


def grant(username: str) -> int:
    with SessionLocal() as db:
        if not grant_admin(db, username):
            print(f"No user named {username}.")
            return 1
        db.commit()
    print(f"{username} is an admin.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.auth")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("create-admin", help="create an admin account")
    granting = sub.add_parser("grant-admin", help="make an existing user an admin")
    granting.add_argument("username")
    args = parser.parse_args()
    if args.command == "create-admin":
        return create(
            RegisterForm(
                username=input("Username: "),
                password=getpass("Password: "),
                confirm_password=getpass("Confirm password: "),
            )
        )
    return grant(args.username)


if __name__ == "__main__":
    sys.exit(main())

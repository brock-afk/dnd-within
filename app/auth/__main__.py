import argparse
import sys
from getpass import getpass

from app import models  # noqa: F401
from app.auth.form import RegisterForm
from app.auth.models import User
from app.auth.service import Refusal, create_admin, set_admin
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


def change(username: str, is_admin: bool) -> int:
    with SessionLocal() as db:
        if problem := set_admin(db, username, is_admin):
            print(problem)
            return 1
        db.commit()
    print(f"{username} is an admin." if is_admin else f"{username} is no longer an admin.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.auth")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("create-admin", help="create an admin account")
    sub.add_parser("grant-admin", help="make an existing user an admin").add_argument("username")
    sub.add_parser("revoke-admin", help="take admin away from a user").add_argument("username")
    args = parser.parse_args()
    if args.command == "create-admin":
        return create(
            RegisterForm(
                username=input("Username: "),
                password=getpass("Password: "),
                confirm_password=getpass("Confirm password: "),
            )
        )
    return change(args.username, is_admin=args.command == "grant-admin")


if __name__ == "__main__":
    sys.exit(main())

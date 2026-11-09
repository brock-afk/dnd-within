import re
from typing import Annotated

from pydantic import BaseModel, StringConstraints

Stripped = Annotated[str, StringConstraints(strip_whitespace=True)]
USERNAME = re.compile(r"[A-Za-z0-9._][A-Za-z0-9._-]{2,49}")


class LoginForm(BaseModel):
    username: Stripped = ""
    password: str = ""

    def problem(self) -> str | None:
        if not self.username or not self.password:
            return "Enter your username and password."
        return None


USERNAME_RULE = (
    "Username must be 3–50 letters, digits, dots, dashes or underscores, not starting with a dash."
)


class RegisterForm(BaseModel):
    username: Stripped = ""
    password: str = ""
    confirm_password: str = ""
    invite_code: Stripped = ""

    def problem(self) -> str | None:
        if not USERNAME.fullmatch(self.username):
            return USERNAME_RULE
        if len(self.password) < 8:
            return "Password must be at least 8 characters."
        if self.password != self.confirm_password:
            return "Passwords do not match."
        return None

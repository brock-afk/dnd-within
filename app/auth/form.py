from typing import Annotated

from pydantic import BaseModel, StringConstraints

Stripped = Annotated[str, StringConstraints(strip_whitespace=True)]


class LoginForm(BaseModel):
    username: Stripped = ""
    password: str = ""


class RegisterForm(BaseModel):
    username: Stripped = ""
    password: str = ""
    confirm_password: str = ""
    invite_code: Stripped = ""

    def problem(self) -> str | None:
        if not 3 <= len(self.username) <= 50:
            return "Username must be 3–50 characters."
        if len(self.password) < 8:
            return "Password must be at least 8 characters."
        if self.password != self.confirm_password:
            return "Passwords do not match."
        return None

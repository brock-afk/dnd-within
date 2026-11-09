from pydantic import BaseModel

from app.auth.form import Stripped
from app.invites.models import NOTE_LENGTH


class InviteForm(BaseModel):
    note: Stripped = ""

    def problem(self) -> str | None:
        if not 1 <= len(self.note) <= NOTE_LENGTH:
            return f"Say who the invite is for, in up to {NOTE_LENGTH} characters."
        return None

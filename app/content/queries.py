"""Query helpers shared by everything that lists content."""

from sqlalchemy import ColumnElement


def available(model) -> ColumnElement[bool]:
    """Rows that can be newly picked: not retired from their pack. Characters keep rows they
    already have, so only use this when offering options.

    Visibility settings for homebrew will narrow this too, so every list of pickable content
    should go through here."""
    return model.retired_at.is_(None)

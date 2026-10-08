"""Imports every domain's models so all tables are registered on Base.metadata.

Used by Alembic (migrations/env.py) and the app. Lives at app level, not in core/,
because core never imports from domains.
"""

from app.abilities import models as abilities  # noqa: F401
from app.auth import models as auth  # noqa: F401
from app.characters import models as characters  # noqa: F401
from app.classes import models as classes  # noqa: F401
from app.features import models as features  # noqa: F401
from app.skills import models as skills  # noqa: F401
from app.species import models as species  # noqa: F401
from app.spells import models as spells  # noqa: F401

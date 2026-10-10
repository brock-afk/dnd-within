"""Imports every domain's models so all tables are registered on Base.metadata.

Used by Alembic (migrations/env.py) and the app. Lives at app level, not in core/,
because core never imports from domains.
"""

from app.abilities import models as abilities  # noqa: F401
from app.auth import models as auth  # noqa: F401
from app.backgrounds import models as backgrounds  # noqa: F401
from app.characters import models as characters  # noqa: F401
from app.classes import models as classes  # noqa: F401
from app.content import models as content  # noqa: F401
from app.feats import models as feats  # noqa: F401
from app.features import models as features  # noqa: F401
from app.inventory import models as inventory  # noqa: F401
from app.leveling import models as leveling  # noqa: F401
from app.sharing import models as sharing  # noqa: F401
from app.sheet import models as sheet  # noqa: F401
from app.skills import models as skills  # noqa: F401
from app.species import models as species  # noqa: F401
from app.spells import models as spells  # noqa: F401

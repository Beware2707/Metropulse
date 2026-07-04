"""Relational persistence: SQLAlchemy models, engine wiring and repositories.

Importing this package registers ALL model modules on the shared Base
metadata, so ``Base.metadata`` is complete for Alembic and test setup.
"""

from metropulse.infrastructure.db import commuter_models as commuter_models
from metropulse.infrastructure.db import models as models

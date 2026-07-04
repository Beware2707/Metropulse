"""Anonymous device-based user accounts with rotating bearer tokens."""

from __future__ import annotations

import hashlib
import secrets
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.domain.entities import utcnow
from metropulse.infrastructure.db.commuter_models import User
from metropulse.infrastructure.db.commuter_repositories import UserRepository


def hash_token(token: str) -> str:
    """SHA-256 hex digest of a bearer token (only the hash is stored)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class UserService:
    """Registration and token authentication for device-scoped users."""

    async def register(
        self, session: AsyncSession, device_id: str, platform: str | None
    ) -> tuple[User, str, bool]:
        """Create or re-key the account for a device.

        Re-registering an existing device rotates its token (the old token
        stops working), which doubles as the recovery path for lost tokens.
        Returns ``(user, plaintext_token, created)``.
        """
        token = secrets.token_urlsafe(32)
        now = utcnow()
        repo = UserRepository(session)
        user = await repo.by_device(device_id)
        if user is not None:
            user.token_hash = hash_token(token)
            user.platform = platform or user.platform
            user.last_seen_at = now
            return user, token, False
        user = User(
            id=str(uuid.uuid4()),
            device_id=device_id,
            token_hash=hash_token(token),
            platform=platform,
            created_at=now,
            last_seen_at=now,
        )
        repo.add(user)
        await session.flush()
        return user, token, True

    async def authenticate(self, session: AsyncSession, token: str) -> User | None:
        """Resolve a bearer token to its user, updating last_seen_at."""
        user = await UserRepository(session).by_token_hash(hash_token(token))
        if user is not None:
            user.last_seen_at = utcnow()
        return user

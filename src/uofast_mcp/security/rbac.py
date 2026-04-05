"""RBAC engine: user lookup, permission checking, authentication."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .auth import verify_password
from .models import Permission, Role, RolePermission, User

logger = logging.getLogger(__name__)


class RBACEngine:
    """Stateless helper; every method takes a live AsyncSession."""

    async def get_user_by_id(self, session: AsyncSession, user_id: int) -> User | None:
        return await session.get(
            User,
            user_id,
            options=[selectinload(User.role).selectinload(Role.role_permissions)
                     .selectinload(RolePermission.permission)],
        )

    async def get_user_by_username(self, session: AsyncSession, username: str) -> User | None:
        result = await session.execute(
            select(User)
            .where(User.username == username)
            .options(
                selectinload(User.role)
                .selectinload(Role.role_permissions)
                .selectinload(RolePermission.permission)
            )
        )
        return result.scalar_one_or_none()

    async def has_permission(
        self, session: AsyncSession, user_id: int, permission_key: str
    ) -> bool:
        user = await self.get_user_by_id(session, user_id)
        if not user or user.status != "active":
            return False
        perm_keys = await self._get_permission_keys(session, user.role_id)
        return permission_key in perm_keys

    async def _get_permission_keys(
        self, session: AsyncSession, role_id: int
    ) -> set[str]:
        result = await session.execute(
            select(Permission.permission_key)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role_id)
        )
        return {row[0] for row in result.fetchall()}

    async def authenticate_password(
        self, session: AsyncSession, username: str, password: str
    ) -> User | None:
        user = await self.get_user_by_username(session, username)
        if not user:
            return None
        if user.status != "active":
            logger.warning("Login attempt for disabled user: %s", username)
            return None
        if not verify_password(password, user.password_hash):
            return None
        # Update last_login
        user.last_login = datetime.now(tz=timezone.utc)
        await session.commit()
        return user


rbac_engine = RBACEngine()

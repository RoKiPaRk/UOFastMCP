"""Async SQLAlchemy engine, session factory, and DB initialisation/seeding."""
from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .models import Base, Permission, Role, RolePermission, User
from .auth import hash_password
from .permissions import DEFAULT_ROLE_PERMISSIONS, PERMISSION_DESCRIPTIONS

logger = logging.getLogger(__name__)

DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./data/security.db",
)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Create all tables and run idempotent seed."""
    # Ensure data/ directory exists for SQLite
    if "sqlite" in DATABASE_URL:
        db_path = DATABASE_URL.split("///")[-1]
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await _seed_defaults()
    logger.info("Database initialised at %s", DATABASE_URL)


async def _seed_defaults() -> None:
    """Idempotently seed default roles, permissions, and the initial admin user."""
    async with AsyncSessionLocal() as session:
        await _seed_roles(session)
        await _seed_permissions(session)
        await _seed_role_permissions(session)
        await _seed_admin_user(session)
        await session.commit()


async def _seed_roles(session: AsyncSession) -> None:
    from sqlalchemy import select

    role_defs = [
        ("admin",          "Full access to all tools and management functions"),
        ("developer",      "Read/write access to records, DICT, and BP programs"),
        ("analyst",        "Read access plus query execution"),
        ("readonly",       "Read-only access to files, records, and dictionaries"),
        ("service_account","Service-to-service access (readonly by default, customizable)"),
    ]
    for role_name, description in role_defs:
        existing = await session.scalar(select(Role).where(Role.role_name == role_name))
        if not existing:
            session.add(Role(role_name=role_name, description=description))
            logger.info("Seeded role: %s", role_name)


async def _seed_permissions(session: AsyncSession) -> None:
    from sqlalchemy import select

    for perm_key, (tool_name, description) in PERMISSION_DESCRIPTIONS.items():
        action = perm_key.rsplit(".", 1)[-1]
        existing = await session.scalar(
            select(Permission).where(Permission.permission_key == perm_key)
        )
        if not existing:
            session.add(Permission(
                tool_name=tool_name,
                action=action,
                permission_key=perm_key,
                description=description,
            ))
            logger.info("Seeded permission: %s", perm_key)


async def _seed_role_permissions(session: AsyncSession) -> None:
    from sqlalchemy import select

    for role_name, perm_keys in DEFAULT_ROLE_PERMISSIONS.items():
        role = await session.scalar(select(Role).where(Role.role_name == role_name))
        if not role:
            continue
        for perm_key in perm_keys:
            perm = await session.scalar(
                select(Permission).where(Permission.permission_key == perm_key)
            )
            if not perm:
                continue
            existing = await session.scalar(
                select(RolePermission).where(
                    RolePermission.role_id == role.id,
                    RolePermission.permission_id == perm.id,
                )
            )
            if not existing:
                session.add(RolePermission(role_id=role.id, permission_id=perm.id))


async def _seed_admin_user(session: AsyncSession) -> None:
    from sqlalchemy import select

    existing = await session.scalar(select(User).where(User.username == "admin"))
    if existing:
        return

    # Only auto-seed if INITIAL_ADMIN_PASSWORD is explicitly set.
    # Without it, skip seeding so the setup wizard at /setup can run on a
    # fresh install. Users who want to skip the wizard should set this env var.
    admin_password = os.getenv("INITIAL_ADMIN_PASSWORD")
    if not admin_password:
        logger.info(
            "INITIAL_ADMIN_PASSWORD not set — skipping admin user seed. "
            "Run the setup wizard at /setup to create the admin account."
        )
        return

    admin_role = await session.scalar(select(Role).where(Role.role_name == "admin"))
    if not admin_role:
        logger.warning("Admin role not found, skipping admin user seed")
        return

    session.add(User(
        username="admin",
        email="admin@localhost",
        password_hash=hash_password(admin_password),
        status="active",
        role_id=admin_role.id,
    ))
    logger.info("Seeded admin user from INITIAL_ADMIN_PASSWORD env var")

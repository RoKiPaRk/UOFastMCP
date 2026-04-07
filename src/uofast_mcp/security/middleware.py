"""
FastAPI auth middleware and contextvars bridge.

Flow:
  HTTP Request
    → AuthMiddleware (pure ASGI — no BaseHTTPMiddleware, SSE-compatible)
       → extract Basic Auth credentials from Authorization header
       → validate → load user → store in _current_user_var ContextVar
    → FastAPI route / MCP SSE handler
       → get_current_user_from_context() reads the ContextVar
       → permission check via require_tool_permission()

Auth method: HTTP Basic Auth only.
  Authorization: Basic <base64(username:password)>
"""
from __future__ import annotations

import base64
import logging
from contextvars import ContextVar
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .database import AsyncSessionLocal
from .models import User
from .permissions import TOOL_PERMISSIONS
from .rbac import rbac_engine

logger = logging.getLogger(__name__)

# ContextVar carries the authenticated user for the duration of each request
_current_user_var: ContextVar[User | None] = ContextVar("current_user", default=None)

# Paths that don't require authentication
_PUBLIC_PATHS = frozenset({
    "/auth/login",
    "/health",
    "/favicon.ico",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/messages",  # MCP message POSTs — session_id UUID is the access proof
})


class AuthMiddleware:
    """Pure ASGI auth middleware — SSE-compatible (no BaseHTTPMiddleware buffering)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")

        # Allow public paths through without auth
        if path in _PUBLIC_PATHS or path.startswith("/admin"):
            await self.app(scope, receive, send)
            return

        # Extract Authorization header directly from ASGI scope
        headers: dict[bytes, bytes] = {k.lower(): v for k, v in scope.get("headers", [])}
        authorization = headers.get(b"authorization", b"").decode()

        user = await _extract_user_from_headers(authorization)
        if user is None:
            response = JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Not authenticated"},
                headers={"WWW-Authenticate": 'Basic realm="UOFast MCP"'},
            )
            await response(scope, receive, send)
            return

        token = _current_user_var.set(user)
        try:
            await self.app(scope, receive, send)
        finally:
            _current_user_var.reset(token)


async def _extract_user_from_headers(authorization: str) -> User | None:
    """Authenticate via HTTP Basic Auth only."""
    if not authorization.startswith("Basic "):
        return None
    async with AsyncSessionLocal() as session:
        try:
            decoded = base64.b64decode(authorization[6:]).decode("utf-8")
            username, password = decoded.split(":", 1)
            return await rbac_engine.authenticate_password(session, username, password)
        except Exception:
            return None


def get_current_user_from_context() -> User | None:
    """Read the authenticated user set by AuthMiddleware. Returns None if unset."""
    return _current_user_var.get()


# ---------------------------------------------------------------------------
# FastAPI Depends helpers (used in admin router and auth endpoints)
# ---------------------------------------------------------------------------

async def get_db_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def get_current_user(request: Request) -> User:
    """FastAPI Depends: returns the current user or raises 401."""
    user = get_current_user_from_context()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": 'Basic realm="UOFast MCP"'},
        )
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """FastAPI Depends: requires admin role or raises 403."""
    if user.role.role_name != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


async def require_tool_permission(
    tool_name: str,
    user: User,
    session: AsyncSession,
) -> None:
    """Check that user has the required permission for tool_name. Raises 403 if denied."""
    perm_key = TOOL_PERMISSIONS.get(tool_name)
    if perm_key is None:
        return  # tool has no permission requirement
    allowed = await rbac_engine.has_permission(session, user.id, perm_key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {perm_key} required for tool '{tool_name}'",
        )

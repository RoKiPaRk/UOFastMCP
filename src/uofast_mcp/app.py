"""
UOFast MCP Server — FastAPI Application Factory
================================================

Starts the MCP server over HTTP/SSE transport with HTTP Basic Auth,
RBAC enforcement, audit logging, and a SQLAdmin web UI.

Entry point:
    uvicorn src.uofast_mcp.app:app --host 0.0.0.0 --port 8000

Connect via CLI (easiest):
    claude mcp add --transport sse UOFastMCP http://localhost:8000/sse \\
      --header "Authorization: Basic <base64-of-user:pass>"

Or via config file (Claude Desktop / VSCode):
    {
      "mcpServers": {
        "UOFastMCP": {
          "url": "http://localhost:8000/sse",
          "headers": { "Authorization": "Basic <base64-of-user:pass>" }
        }
      }
    }

Visit http://localhost:8000/auth/login to get your ready-to-use command.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

# Auto-load .env if present (written by setup wizard, or manually created).
# Must run before any os.getenv() calls so the values are visible.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(".env"), override=False)  # override=False: real env vars win
except ImportError:
    pass  # python-dotenv not installed — env vars must be set manually

from fastapi import FastAPI
from mcp.server.sse import SseServerTransport
from sqladmin import Admin
from starlette.middleware.sessions import SessionMiddleware

from .admin.router import auth_router, router as admin_router
from .admin.ui import AdminAuth, ALL_VIEWS
from .security.database import engine, init_db
from .security.middleware import AuthMiddleware
from .server import app as mcp_server, initialize_server, connection_manager
from .setup.router import router as setup_router

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    # Secret key used for session encryption (Starlette SessionMiddleware)
    # and credential encryption (credential_store.py / Fernet key derivation).
    _secret_key = os.getenv("JWT_SECRET_KEY", "CHANGE_ME_IN_PRODUCTION")

    fast_app = FastAPI(
        title="UOFast MCP Server",
        description="Enterprise MCP server for U2 UniData/UniVerse with Basic Auth and RBAC",
        version="2.0.0",
        docs_url="/docs" if os.getenv("ENABLE_DOCS", "true").lower() == "true" else None,
    )

    # --- Session middleware (required by SQLAdmin for login cookies) ---
    fast_app.add_middleware(
        SessionMiddleware,
        secret_key=_secret_key,
        max_age=60 * 60 * 8,  # 8-hour sessions
    )

    # --- Auth middleware: validates Basic Auth on all non-public paths ---
    fast_app.add_middleware(AuthMiddleware)

    # --- Setup wizard (public — no auth required) ---
    fast_app.include_router(setup_router)

    # --- Auth REST endpoints (public) ---
    fast_app.include_router(auth_router)

    # --- Admin REST API (requires admin role) ---
    fast_app.include_router(admin_router, prefix="/admin/api")

    # --- SQLAdmin Web UI at /admin ---
    admin_ui = Admin(
        fast_app,
        engine,
        title="UOFast Security Admin",
        authentication_backend=AdminAuth(secret_key=_secret_key),
        base_url="/admin",
    )
    for view in ALL_VIEWS:
        admin_ui.add_view(view)

    # --- MCP SSE Transport ---
    # Mounted as pure ASGI apps (not FastAPI routes) so SSE streaming is not
    # double-wrapped — FastAPI would try to send a second http.response.start
    # after the handler returns, which uvicorn rejects.
    sse_transport = SseServerTransport("/messages")

    class _SseApp:
        async def __call__(self, scope, receive, send):
            if scope.get("type") == "http":
                # Starlette Mount appends the mount prefix ("/sse") to scope["root_path"].
                # connect_sse uses root_path to build the client messages URL, so it would
                # produce "/sse/messages" instead of "/messages".  Strip the prefix back.
                scope = {**scope, "root_path": scope.get("root_path", "").removesuffix("/sse")}
                async with sse_transport.connect_sse(scope, receive, send) as streams:
                    await mcp_server.run(
                        streams[0], streams[1], mcp_server.create_initialization_options()
                    )

    class _MessagesApp:
        async def __call__(self, scope, receive, send):
            if scope.get("type") == "http":
                await sse_transport.handle_post_message(scope, receive, send)

    fast_app.mount("/sse", _SseApp())
    fast_app.mount("/messages", _MessagesApp())

    # --- Health check (public) ---
    @fast_app.get("/health")
    async def health():
        return {"status": "ok", "service": "uofast-mcp"}

    # --- Lifecycle ---
    @fast_app.on_event("startup")
    async def startup():
        logger.info("Initialising security database...")
        await init_db()
        logger.info("Initialising UniData connections...")
        initialize_server()
        logger.info("UOFast MCP Server ready.")

    @fast_app.on_event("shutdown")
    async def shutdown():
        logger.info("Shutting down — closing all UniData connections...")
        if connection_manager:
            connection_manager.close_all_connections()

    return fast_app


app = create_app()

"""Admin REST API router — all endpoints require admin role."""
from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.responses import HTMLResponse, StreamingResponse

from ..security.auth import hash_password, verify_password
from ..security.database import AsyncSessionLocal
from ..security.middleware import get_db_session, require_admin
from ..security.models import AuditLog, Permission, Role, RolePermission, User
from ..security.rbac import rbac_engine
from .schemas import (
    AssignPermissionRequest,
    AuditLogOut,
    PermissionOut,
    RoleOut,
    UserCreate,
    UserOut,
    UserUpdate,
)

router = APIRouter(tags=["admin"])


# ---------------------------------------------------------------------------
# Auth endpoints (public — no admin required)
# ---------------------------------------------------------------------------

auth_router = APIRouter(prefix="/auth", tags=["auth"])


def _render_login_page(
    error: str | None = None,
    username: str | None = None,
    basic_token: str | None = None,
    role_name: str | None = None,
    host: str = "localhost:8000",
) -> str:
    error_block = f'<div class="alert alert-danger"><i class="fa-solid fa-circle-xmark me-2"></i>{error}</div>' if error else ""
    success_block = ""
    if username and basic_token:
        cli_cmd = (
            f'claude mcp add --transport sse UOFastMCP '
            f'http://{host}/sse '
            f'--header "Authorization: Basic {basic_token}"'
        )
        vscode_config = (
            '{\n'
            '  "servers": {\n'
            '    "UOFastMCP": {\n'
            '      "type": "sse",\n'
            f'      "url": "http://{host}/sse",\n'
            '      "headers": {\n'
            f'        "Authorization": "Basic {basic_token}"\n'
            '      }\n'
            '    }\n'
            '  }\n'
            '}'
        )
        claude_config = (
            '{\n'
            '  "mcpServers": {\n'
            '    "UOFastMCP": {\n'
            f'      "url": "http://{host}/sse",\n'
            '      "headers": {\n'
            f'        "Authorization": "Basic {basic_token}"\n'
            '      }\n'
            '    }\n'
            '  }\n'
            '}'
        )
        success_block = f"""
        <div class="alert alert-success mb-3">
          <i class="fa-solid fa-circle-check me-2"></i>
          Authenticated as <strong>{username}</strong>
          <span class="badge bg-primary ms-2">{role_name or 'user'}</span>
        </div>

        <h6 class="fw-semibold mb-2"><i class="fa-solid fa-terminal me-2"></i>Claude Code CLI</h6>
        <p class="small text-muted mb-2">Run once in your terminal:</p>
        <pre class="m-0 p-3 bg-dark text-white rounded font-monospace small" id="cliBlock">{cli_cmd}</pre>
        <div class="text-end mt-2 mb-4">
          <button class="btn btn-sm btn-primary"
            onclick="navigator.clipboard.writeText(document.getElementById('cliBlock').innerText);this.innerHTML='<i class=\\'fa-solid fa-check me-1\\'></i>Copied!'">
            <i class="fa-regular fa-copy me-1"></i>Copy command
          </button>
        </div>

        <h6 class="fw-semibold mb-2"><i class="fa-solid fa-file-code me-2"></i>Config File</h6>
        <ul class="nav nav-tabs mb-0" id="cfgTabs" role="tablist">
          <li class="nav-item" role="presentation">
            <button class="nav-link active small py-1 px-3" id="vscode-tab-btn"
              data-bs-toggle="tab" data-bs-target="#vscodeCfg" type="button">
              <i class="fa-brands fa-microsoft me-1"></i>VSCode
            </button>
          </li>
          <li class="nav-item" role="presentation">
            <button class="nav-link small py-1 px-3" id="claude-tab-btn"
              data-bs-toggle="tab" data-bs-target="#claudeCfg" type="button">
              <i class="fa-solid fa-robot me-1"></i>Claude Desktop
            </button>
          </li>
        </ul>
        <div class="tab-content border border-top-0 rounded-bottom mb-1">
          <div class="tab-pane fade show active p-3" id="vscodeCfg" role="tabpanel">
            <p class="small text-muted mb-2">Save as <code>.vscode/mcp.json</code> in your workspace root, then reload the window.</p>
            <pre class="m-0 p-3 bg-dark text-white rounded font-monospace small" id="vscodeBlock">{vscode_config}</pre>
            <div class="text-end mt-2">
              <button class="btn btn-sm btn-outline-secondary"
                onclick="navigator.clipboard.writeText(document.getElementById('vscodeBlock').innerText);this.textContent='Copied!'">
                Copy
              </button>
            </div>
          </div>
          <div class="tab-pane fade p-3" id="claudeCfg" role="tabpanel">
            <p class="small text-muted mb-2">Merge into <code>%APPDATA%\\Claude\\claude_desktop_config.json</code> (Windows) or <code>~/Library/Application Support/Claude/claude_desktop_config.json</code> (macOS), then restart Claude Desktop.</p>
            <pre class="m-0 p-3 bg-dark text-white rounded font-monospace small" id="claudeBlock">{claude_config}</pre>
            <div class="text-end mt-2">
              <button class="btn btn-sm btn-outline-secondary"
                onclick="navigator.clipboard.writeText(document.getElementById('claudeBlock').innerText);this.textContent='Copied!'">
                Copy
              </button>
            </div>
          </div>
        </div>"""
    form_block = "" if (username and basic_token) else f"""
        {error_block}
        <form method="post">
          <div class="mb-3">
            <label for="username" class="form-label fw-semibold">Username</label>
            <input type="text" name="username" id="username" class="form-control"
              placeholder="your username" autocomplete="username" required autofocus>
          </div>
          <div class="mb-3">
            <label for="password" class="form-label fw-semibold">Password</label>
            <input type="password" name="password" id="password" class="form-control"
              autocomplete="current-password" required>
          </div>
          <button type="submit" class="btn btn-primary w-100">
            <i class="fa-solid fa-right-to-bracket me-2"></i>Login &amp; Get Connection Config
          </button>
        </form>"""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>UOFast MCP — Login</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js" defer></script>
</head>
<body class="bg-light">
  <div class="container py-5" style="max-width:560px">
    <div class="text-center mb-4">
      <i class="fa-solid fa-database fa-2x text-primary"></i>
      <h4 class="mt-2 fw-bold">UOFast MCP Server</h4>
      <p class="text-muted small">Sign in to get your connection command</p>
    </div>
    <div class="card shadow-sm">
      <div class="card-body p-4">
        {success_block}
        {form_block}
      </div>
    </div>
    <p class="text-center text-muted small mt-3">
      <a href="/admin" class="text-decoration-none">Admin UI</a>
      &nbsp;·&nbsp;
      <a href="/health" class="text-decoration-none">Health</a>
    </p>
  </div>
</body>
</html>"""


@auth_router.get("/login", response_class=HTMLResponse)
async def login_page():
    return HTMLResponse(_render_login_page())


@auth_router.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    import base64 as _b64

    async with AsyncSessionLocal() as session:
        user = await rbac_engine.authenticate_password(session, username, password)

    if not user:
        return HTMLResponse(_render_login_page(error="Invalid username or password."), status_code=401)

    host = request.headers.get("host", "localhost:8000")
    basic_token = _b64.b64encode(f"{username}:{password}".encode()).decode()
    role_name = user.role.role_name if user.role else "readonly"
    return HTMLResponse(_render_login_page(
        username=username,
        basic_token=basic_token,
        role_name=role_name,
        host=host,
    ))


@auth_router.post("/provision")
async def provision_user(
    request: Request,
    _admin: Annotated[User, Depends(require_admin)],
):
    """
    Admin-only: create a user and return their ready-to-use ``claude mcp add`` command.

    Accepts JSON body: ``{"username", "password", "role_name", "email" (optional)}``.
    Returns the CLI command so the admin can send it directly to the new user.
    """
    import base64 as _b64
    from starlette.responses import JSONResponse

    body = await request.json()
    uname = body.get("username", "").strip()
    pwd = body.get("password", "").strip()
    role_name = body.get("role_name", "readonly").strip()
    email = body.get("email", "").strip() or None

    if not uname or not pwd:
        raise HTTPException(status_code=422, detail="username and password are required")

    async with AsyncSessionLocal() as session:
        # Check for existing user
        existing = await session.scalar(select(User).where(User.username == uname))
        if existing:
            raise HTTPException(status_code=409, detail=f"User '{uname}' already exists")

        # Resolve role
        role = await session.scalar(select(Role).where(Role.role_name == role_name))
        if not role:
            raise HTTPException(status_code=400, detail=f"Role '{role_name}' not found")

        user = User(
            username=uname,
            email=email,
            password_hash=hash_password(pwd),
            role_id=role.id,
            status="active",
        )
        session.add(user)
        await session.commit()

    host = request.headers.get("host", "localhost:8000")
    basic_token = _b64.b64encode(f"{uname}:{pwd}".encode()).decode()
    cli_cmd = (
        f'claude mcp add --transport sse unidata '
        f'http://{host}/sse '
        f'--header "Authorization: Basic {basic_token}"'
    )

    return JSONResponse({
        "username": uname,
        "role": role_name,
        "claude_command": cli_cmd,
    })


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@router.get("/users", response_model=list[UserOut])
async def list_users(
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    result = await session.execute(
        select(User)
        .options(selectinload(User.role))
        .offset(skip)
        .limit(limit)
        .order_by(User.id)
    )
    return result.scalars().all()


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    role = await session.scalar(select(Role).where(Role.role_name == body.role_name))
    if not role:
        raise HTTPException(status_code=404, detail=f"Role '{body.role_name}' not found")
    existing = await session.scalar(select(User).where(User.username == body.username))
    if existing:
        raise HTTPException(status_code=409, detail="Username already exists")
    user = User(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        status="active",
        role_id=role.id,
    )
    session.add(user)
    await session.flush()
    await session.refresh(user, ["role"])
    return user


@router.get("/users/{user_id}", response_model=UserOut)
async def get_user(
    user_id: int,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    user = await session.scalar(
        select(User).where(User.id == user_id).options(selectinload(User.role))
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.put("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    body: UserUpdate,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    user = await session.scalar(
        select(User).where(User.id == user_id).options(selectinload(User.role))
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if body.email is not None:
        user.email = body.email
    if body.status is not None:
        user.status = body.status
    if body.role_name is not None:
        role = await session.scalar(select(Role).where(Role.role_name == body.role_name))
        if not role:
            raise HTTPException(status_code=404, detail=f"Role '{body.role_name}' not found")
        user.role_id = role.id
    await session.flush()
    await session.refresh(user, ["role"])
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(
    user_id: int,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.status = "disabled"


# ---------------------------------------------------------------------------
# Roles & Permissions
# ---------------------------------------------------------------------------

@router.get("/roles", response_model=list[RoleOut])
async def list_roles(
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    result = await session.execute(select(Role).order_by(Role.id))
    return result.scalars().all()


@router.post("/roles", response_model=RoleOut, status_code=status.HTTP_201_CREATED)
async def create_role(
    role_name: str,
    description: str | None = None,
    _admin: Annotated[User, Depends(require_admin)] = None,
    session: Annotated[AsyncSession, Depends(get_db_session)] = None,
):
    existing = await session.scalar(select(Role).where(Role.role_name == role_name))
    if existing:
        raise HTTPException(status_code=409, detail="Role already exists")
    role = Role(role_name=role_name, description=description)
    session.add(role)
    await session.flush()
    return role


@router.get("/permissions", response_model=list[PermissionOut])
async def list_permissions(
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    result = await session.execute(select(Permission).order_by(Permission.permission_key))
    return result.scalars().all()


@router.post("/roles/{role_id}/permissions", status_code=status.HTTP_201_CREATED)
async def assign_permission_to_role(
    role_id: int,
    body: AssignPermissionRequest,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    role = await session.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    perm = await session.scalar(
        select(Permission).where(Permission.permission_key == body.permission_key)
    )
    if not perm:
        raise HTTPException(status_code=404, detail=f"Permission '{body.permission_key}' not found")
    existing = await session.scalar(
        select(RolePermission).where(
            RolePermission.role_id == role_id,
            RolePermission.permission_id == perm.id,
        )
    )
    if existing:
        return {"detail": "Permission already assigned"}
    session.add(RolePermission(role_id=role_id, permission_id=perm.id))
    return {"detail": "Permission assigned"}


@router.delete("/roles/{role_id}/permissions/{permission_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_permission_from_role(
    role_id: int,
    permission_id: int,
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    rp = await session.scalar(
        select(RolePermission).where(
            RolePermission.role_id == role_id,
            RolePermission.permission_id == permission_id,
        )
    )
    if not rp:
        raise HTTPException(status_code=404, detail="Assignment not found")
    await session.delete(rp)


# ---------------------------------------------------------------------------
# Audit Logs
# ---------------------------------------------------------------------------

@router.get("/audit-logs", response_model=list[AuditLogOut])
async def query_audit_logs(
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user_id: int | None = Query(None),
    tool_name: str | None = Query(None),
    result_status: str | None = Query(None),
    since: datetime | None = Query(None),
    until: datetime | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    q = select(AuditLog).order_by(AuditLog.timestamp.desc())
    if user_id is not None:
        q = q.where(AuditLog.user_id == user_id)
    if tool_name:
        q = q.where(AuditLog.tool_name == tool_name)
    if result_status:
        q = q.where(AuditLog.result_status == result_status)
    if since:
        q = q.where(AuditLog.timestamp >= since)
    if until:
        q = q.where(AuditLog.timestamp <= until)
    result = await session.execute(q.offset(skip).limit(limit))
    return result.scalars().all()


@router.get("/audit-logs/export")
async def export_audit_logs_csv(
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    since: datetime | None = Query(None),
    until: datetime | None = Query(None),
):
    q = select(AuditLog).order_by(AuditLog.timestamp.desc())
    if since:
        q = q.where(AuditLog.timestamp >= since)
    if until:
        q = q.where(AuditLog.timestamp <= until)
    result = await session.execute(q)
    logs = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "user_id", "tool_name", "action", "result_status",
                     "error_message", "timestamp", "ip_address", "params_summary"])
    for log in logs:
        writer.writerow([
            log.id, log.user_id, log.tool_name, log.action,
            log.result_status, log.error_message, log.timestamp,
            log.ip_address, log.params_summary,
        ])
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_logs.csv"},
    )

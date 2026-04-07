"""
UOFast MCP Server — Setup Wizard
=================================
Multi-step first-run configuration wizard at /setup.
All routes are public (no JWT required).

Steps:
  1. /setup/welcome      — prerequisites check
  2. /setup/security     — JWT secret + admin password
  3. /setup/connection   — UniData connection settings + live test
  4. /setup/complete     — write config, init DB, show .env
  5. /setup/client-setup — Claude Desktop / VSCode / CLI configs
"""
from __future__ import annotations

import asyncio
import base64
import configparser
import json
import os
import secrets
from datetime import datetime
from pathlib import Path

import uopy
from fastapi import APIRouter
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from starlette.requests import Request
from starlette.templating import Jinja2Templates

from ..security.auth import hash_password
from ..security.database import AsyncSessionLocal, init_db
from ..security.models import Role, User

router = APIRouter(prefix="/setup", tags=["setup"])
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


# ---------------------------------------------------------------------------
# Helpers — state detection
# ---------------------------------------------------------------------------

async def _is_already_configured() -> bool:
    """True if data/security.db exists AND an admin user row is present."""
    if not Path("data/security.db").exists():
        return False
    try:
        async with AsyncSessionLocal() as session:
            user = await session.scalar(select(User).where(User.username == "admin"))
            return user is not None
    except Exception:
        return False


def _check_prerequisites() -> list[dict]:
    import sys
    prereqs = []

    # Python version
    ok = sys.version_info >= (3, 11)
    prereqs.append({
        "label": "Python 3.11+",
        "ok": ok,
        "note": f"Found {sys.version_info.major}.{sys.version_info.minor}" if not ok else "",
    })

    # uopy importable
    try:
        import uopy as _u  # noqa: F401
        prereqs.append({"label": "uopy installed", "ok": True, "note": ""})
    except ImportError:
        prereqs.append({"label": "uopy installed", "ok": False, "note": "pip install uopy"})

    # data/ writable
    data_dir = Path("data")
    try:
        data_dir.mkdir(exist_ok=True)
        test_file = data_dir / ".write_test"
        test_file.write_text("ok")
        test_file.unlink()
        prereqs.append({"label": "data/ directory writable", "ok": True, "note": ""})
    except Exception as exc:
        prereqs.append({"label": "data/ directory writable", "ok": False, "note": str(exc)})

    # JWT secret env var
    has_secret = bool(os.getenv("JWT_SECRET_KEY"))
    prereqs.append({
        "label": "JWT_SECRET_KEY environment variable set",
        "ok": has_secret,
        "note": "The wizard will generate one — set it before restarting." if not has_secret else "",
    })

    return prereqs


# ---------------------------------------------------------------------------
# Helpers — validation
# ---------------------------------------------------------------------------

def _validate_security_form(form: dict) -> dict[str, str]:
    errors: dict[str, str] = {}
    if len(form.get("jwt_secret", "")) < 16:
        errors["jwt_secret"] = "JWT secret must be at least 16 characters."
    if not form.get("admin_email", "").strip():
        errors["admin_email"] = "Admin email is required."
    pw = form.get("admin_password", "")
    if len(pw) < 10:
        errors["admin_password"] = "Password must be at least 10 characters."
    elif pw != form.get("admin_password_confirm", ""):
        errors["admin_password"] = "Passwords do not match."
    return errors


def _validate_connection_form(form: dict) -> dict[str, str]:
    errors: dict[str, str] = {}
    for field, label in [
        ("conn_host", "Host"),
        ("conn_username", "Username"),
        ("conn_account", "Account Path"),
    ]:
        if not form.get(field, "").strip():
            errors[field] = f"{label} is required."
    try:
        port = int(form.get("conn_port", 0))
        if not (1 <= port <= 65535):
            raise ValueError
    except ValueError:
        errors["conn_port"] = "Port must be a number between 1 and 65535."
    return errors


def _connection_defaults() -> dict:
    return {
        "conn_name": "production",
        "conn_port": "31438",
        "conn_service": "udcs",
        "conn_auto_connect": True,
        "pool_min": "1",
        "pool_max": "5",
        "log_level": "INFO",
    }


# ---------------------------------------------------------------------------
# Helpers — setup execution
# ---------------------------------------------------------------------------

def _write_unidata_config(sess: dict) -> None:
    """Write unidata_config.ini atomically with encrypted password."""
    from ..utils.credential_store import encrypt_password, get_or_create_salt

    target = Path("unidata_config.ini")
    jwt_secret = sess.get("setup_jwt_secret", os.getenv("JWT_SECRET_KEY", ""))
    salt = get_or_create_salt(target)
    encrypted_password = encrypt_password(sess.get("setup_conn_password", ""), jwt_secret, salt)

    config = configparser.ConfigParser()
    config["encryption"] = {"salt": salt.hex()}
    config["server"] = {
        "min_connections": str(sess.get("setup_pool_min", 1)),
        "max_connections": str(sess.get("setup_pool_max", 5)),
        "log_level": sess.get("setup_log_level", "INFO"),
        "default_connection": sess.get("setup_conn_name", "production"),
    }
    conn_name = sess.get("setup_conn_name", "production")
    config[f"connection:{conn_name}"] = {
        "host": sess["setup_conn_host"],
        "port": str(sess.get("setup_conn_port", 31438)),
        "username": sess["setup_conn_username"],
        "password": encrypted_password,
        "account": sess["setup_conn_account"],
        "service": sess.get("setup_conn_service", "udcs"),
        "auto_connect": "true" if sess.get("setup_conn_auto_connect") else "false",
    }
    tmp = target.with_suffix(".ini.tmp")
    with tmp.open("w") as f:
        f.write("; UOFast MCP Server — Connection Configuration\n")
        f.write("; Passwords are Fernet-encrypted. Do not edit manually.\n\n")
        config.write(f)
    os.replace(tmp, target)


async def _create_or_update_admin(username: str, email: str, plain_password: str) -> None:
    async with AsyncSessionLocal() as session:
        admin_role = await session.scalar(select(Role).where(Role.role_name == "admin"))
        existing = await session.scalar(select(User).where(User.username == username))
        if existing:
            existing.email = email
            existing.password_hash = hash_password(plain_password)
            existing.status = "active"
        else:
            session.add(User(
                username=username,
                email=email,
                password_hash=hash_password(plain_password),
                status="active",
                role_id=admin_role.id,
            ))
        await session.commit()


def _build_env_content(jwt_secret: str, admin_password: str) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return (
        f"# UOFast MCP Server — Environment Variables\n"
        f"# Generated by Setup Wizard on {now}\n"
        f"# IMPORTANT: Store securely. Never commit to version control.\n\n"
        f"JWT_SECRET_KEY={jwt_secret}\n"
        f"INITIAL_ADMIN_PASSWORD={admin_password}\n"
        f"# DATABASE_URL=sqlite+aiosqlite:///./data/security.db\n"
        f"# ENABLE_DOCS=false\n"
    )


def _write_env_file(content: str) -> None:
    target = Path(".env")
    tmp = target.with_suffix(".tmp")
    tmp.write_text(content)
    os.replace(tmp, target)


async def _run_setup(request: Request) -> dict:
    result = {
        "env_file_content": "",
        "ini_written": False,
        "db_initialized": False,
        "admin_created": False,
        "errors": [],
    }
    sess = request.session
    jwt_secret = sess.get("setup_jwt_secret", secrets.token_hex(32))
    admin_username = sess.get("setup_admin_username", "admin")
    admin_email = sess.get("setup_admin_email", "admin@localhost")
    admin_password = sess.get("setup_admin_password", "")

    if not sess.get("setup_conn_skipped", False):
        try:
            _write_unidata_config(sess)
            result["ini_written"] = True
        except Exception as exc:
            result["errors"].append(f"Failed to write unidata_config.ini: {exc}")

    try:
        await init_db()
        result["db_initialized"] = True
    except Exception as exc:
        result["errors"].append(f"Failed to initialise database: {exc}")
        return result

    try:
        await _create_or_update_admin(admin_username, admin_email, admin_password)
        result["admin_created"] = True
    except Exception as exc:
        result["errors"].append(f"Failed to create admin user: {exc}")

    env_content = _build_env_content(jwt_secret, admin_password)
    try:
        _write_env_file(env_content)
    except Exception as exc:
        result["errors"].append(f"Could not write .env file: {exc}")
    result["env_file_content"] = env_content

    sess.pop("setup_conn_password", None)
    return result


def _build_client_configs(base_url: str, admin_username: str, admin_password: str) -> dict:
    sse_url = f"{base_url.rstrip('/')}/sse"
    basic_token = base64.b64encode(f"{admin_username}:{admin_password}".encode()).decode()

    claude_desktop_config = json.dumps({
        "mcpServers": {
            "UOFastMCP": {
                "url": sse_url,
                "headers": {"Authorization": f"Basic {basic_token}"},
            }
        }
    }, indent=2)

    vscode_config = json.dumps({
        "servers": {
            "UOFastMCP": {
                "type": "sse",
                "url": sse_url,
                "headers": {"Authorization": f"Basic {basic_token}"},
            }
        }
    }, indent=2)

    return {
        "sse_url": sse_url,
        "basic_token": basic_token,
        "claude_desktop_config": claude_desktop_config,
        "vscode_config": vscode_config,
        "cli_command": f'claude mcp add --transport sse UOFastMCP {sse_url} --header "Authorization: Basic {basic_token}"',
        "curl_command": f'curl -H "Authorization: Basic {basic_token}" {base_url.rstrip("/")}/health',
        "admin_username": admin_username,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("")
async def setup_root():
    return RedirectResponse("/setup/welcome", status_code=302)


@router.get("/welcome")
async def welcome_get(request: Request):
    already_done = await _is_already_configured()
    prereqs = _check_prerequisites()
    return templates.TemplateResponse(request, "welcome.html", {
        "step": 1,
        "already_configured": already_done,
        "prereqs": prereqs,
        "all_ok": all(p["ok"] for p in prereqs if p["label"] != "JWT_SECRET_KEY environment variable set"),
    })


@router.get("/security")
async def security_get(request: Request):
    already_done = await _is_already_configured()
    if already_done and not request.session.get("setup_complete"):
        return templates.TemplateResponse(request, "welcome.html", {
            "step": 1,
            "already_configured": True,
            "prereqs": [],
            "all_ok": True,
        })
    if "setup_jwt_secret" not in request.session:
        request.session["setup_jwt_secret"] = secrets.token_hex(32)
    return templates.TemplateResponse(request, "security.html", {
        "step": 2,
        "jwt_secret": request.session["setup_jwt_secret"],
        "errors": {},
        "form": {},
    })


@router.post("/security")
async def security_post(request: Request):
    already_done = await _is_already_configured()
    if already_done and not request.session.get("setup_complete"):
        return RedirectResponse("/setup/welcome", status_code=302)

    form = dict(await request.form())
    errors = _validate_security_form(form)
    if errors:
        return templates.TemplateResponse(request, "security.html", {
            "step": 2,
            "jwt_secret": form.get("jwt_secret", request.session.get("setup_jwt_secret", "")),
            "errors": errors,
            "form": form,
        })

    request.session["setup_jwt_secret"] = form["jwt_secret"]
    request.session["setup_admin_username"] = form.get("admin_username", "admin").strip()
    request.session["setup_admin_email"] = form["admin_email"].strip()
    request.session["setup_admin_password"] = form["admin_password"]
    request.session["setup_security_done"] = True
    return RedirectResponse("/setup/connection", status_code=303)


@router.get("/connection")
async def connection_get(request: Request):
    already_done = await _is_already_configured()
    if already_done and not request.session.get("setup_complete"):
        return templates.TemplateResponse(request, "welcome.html", {
            "step": 1,
            "already_configured": True,
            "prereqs": [],
            "all_ok": True,
        })
    if not request.session.get("setup_security_done"):
        return RedirectResponse("/setup/security", status_code=302)
    return templates.TemplateResponse(request, "connection.html", {
        "step": 3,
        "errors": {},
        "form": _connection_defaults(),
    })


@router.post("/connection")
async def connection_post(request: Request):
    already_done = await _is_already_configured()
    if already_done and not request.session.get("setup_complete"):
        return RedirectResponse("/setup/welcome", status_code=302)
    if not request.session.get("setup_security_done"):
        return RedirectResponse("/setup/security", status_code=302)

    form = dict(await request.form())

    if form.get("skip"):
        request.session["setup_conn_skipped"] = True
        return RedirectResponse("/setup/complete", status_code=303)

    errors = _validate_connection_form(form)
    if errors:
        return templates.TemplateResponse(request, "connection.html", {
            "step": 3,
            "errors": errors,
            "form": form,
        })

    request.session.update({
        "setup_conn_name": form.get("conn_name", "production").strip(),
        "setup_conn_host": form["conn_host"].strip(),
        "setup_conn_port": int(form.get("conn_port", 31438)),
        "setup_conn_username": form["conn_username"].strip(),
        "setup_conn_password": form.get("conn_password", ""),
        "setup_conn_account": form["conn_account"].strip(),
        "setup_conn_service": form.get("conn_service", "udcs").strip(),
        "setup_conn_auto_connect": "conn_auto_connect" in form,
        "setup_pool_min": int(form.get("pool_min") or 1),
        "setup_pool_max": int(form.get("pool_max") or 5),
        "setup_log_level": form.get("log_level", "INFO").upper(),
        "setup_conn_skipped": False,
    })
    return RedirectResponse("/setup/complete", status_code=303)


@router.post("/test-connection")
async def test_connection(request: Request):
    """AJAX — test uopy connectivity, returns JSON."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"success": False, "message": "Invalid request body"})

    host = str(body.get("host", "")).strip()
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    account = str(body.get("account", "")).strip()
    service = str(body.get("service", "udcs")).strip()
    try:
        port = int(body.get("port", 31438))
    except (TypeError, ValueError):
        port = 31438

    if not all([host, username, account]):
        return JSONResponse({"success": False, "message": "Host, username, and account are required"})

    loop = asyncio.get_running_loop()
    try:
        conn = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: uopy.connect(
                    host=host, user=username, password=password,
                    account=account, service=service, port=port,
                ),
            ),
            timeout=10.0,
        )
        await loop.run_in_executor(None, conn.close)
        return JSONResponse({"success": True, "message": f"Connected to {host}:{port} — {account}"})
    except asyncio.TimeoutError:
        return JSONResponse({"success": False, "message": f"Timed out after 10s ({host}:{port})"})
    except Exception as exc:
        return JSONResponse({"success": False, "message": f"Connection failed: {exc}"})


@router.get("/complete")
async def complete_get(request: Request):
    already_done = await _is_already_configured()
    if already_done and not request.session.get("setup_complete") and not request.session.get("setup_security_done"):
        return templates.TemplateResponse(request, "welcome.html", {
            "step": 1,
            "already_configured": True,
            "prereqs": [],
            "all_ok": True,
        })
    if not request.session.get("setup_security_done"):
        return RedirectResponse("/setup/security", status_code=302)

    result = await _run_setup(request)
    request.session["setup_complete"] = True
    return templates.TemplateResponse(request, "complete.html", {
        "step": 4,
        "result": result,
    })


@router.get("/client-setup")
async def client_setup_get(request: Request):
    if not request.session.get("setup_complete"):
        return RedirectResponse("/setup/complete", status_code=302)

    base_url = str(request.base_url).rstrip("/")
    admin_username = request.session.get("setup_admin_username", "admin")
    admin_password = request.session.pop("setup_admin_password", "")
    configs = _build_client_configs(base_url, admin_username, admin_password)

    return templates.TemplateResponse(request, "client_setup.html", {
        "step": 5,
        **configs,
    })

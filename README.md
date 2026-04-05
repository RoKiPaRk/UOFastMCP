# UOFast MCP Server

Enterprise Model Context Protocol (MCP) server for U2 UniData/UniVerse databases, with JWT authentication, role-based access control (RBAC), audit logging, and a web-based security admin UI.

## What's New in v2

| Feature | v1 (old) | v2 (current) |
|---|---|---|
| Transport | stdio (subprocess) | HTTP/SSE (network service) |
| Authentication | None | JWT · API keys · HTTP Basic Auth |
| Authorization | None | RBAC — per-tool permissions |
| Audit logging | None | SQLite audit log of every tool call |
| Admin UI | None | Web UI at `/admin` |
| User self-service | None | Login page at `/auth/login` — get connection config instantly |

---

## Quick Start (Local Dev)

### 1. Install

```bash
pip install uofast-mcp
# or from source:
pip install -e .
```

### 2. Set required environment variables

```bash
# Windows
set JWT_SECRET_KEY=your-long-random-secret-here
set INITIAL_ADMIN_PASSWORD=YourStrongPassword123!

# macOS/Linux
export JWT_SECRET_KEY=your-long-random-secret-here
export INITIAL_ADMIN_PASSWORD=YourStrongPassword123!
```

Generate a secure secret key:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 3. Start the server

```bash
# via console script (after pip install):
uofast-mcp

# or directly:
uvicorn uofast_mcp.app:app --reload --port 8000
```

On first startup the server will:
- Create `data/security.db` (SQLite database)
- Seed default roles, permissions, and the admin user

### 4. Verify it's running

```
GET http://localhost:8000/health
→ {"status": "ok", "service": "uofast-mcp"}
```

Open the admin UI: **http://localhost:8000/admin**
Login with `admin` / `<INITIAL_ADMIN_PASSWORD>`

---

## Connecting Clients

1. **Log in** at **http://localhost:8000/auth/login** with your username and password
2. **Copy** the `claude mcp add` command shown on the page
3. **Run it** in your terminal — done

```bash
claude mcp add --transport sse unidata http://localhost:8000/sse --header "Authorization: Basic <your-basic-token>"
```

One command, works on Windows/macOS/Linux. No config file editing needed.

> **Manual config:** The login page also has a collapsible JSON config block you can paste into `claude_desktop_config.json` or VSCode MCP settings if you prefer.

---

## User Setup

### Quick path — Admin provisions the user (one step)

The admin can create a user and get their ready-to-use CLI command in a single API call:

```bash
curl -X POST http://localhost:8000/auth/provision \
  -u admin:YourAdminPassword \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "SecurePass123!", "role_name": "developer"}'
```

Response:
```json
{
  "username": "alice",
  "role": "developer",
  "claude_command": "claude mcp add --transport sse unidata http://localhost:8000/sse --header \"Authorization: Basic YWxpY2U6U2VjdXJlUGFzczEyMyE=\""
}
```

Send the `claude_command` value to the user — they run it and they're connected.

### Alternative — Admin UI + self-service login

1. Open **http://localhost:8000/admin** → **Users → Create** → fill in username, email, role
2. Tell the user to visit **http://localhost:8000/auth/login** and log in with their credentials
3. The login page shows the `claude mcp add` command — user copies and runs it

### (Optional) API Keys for service accounts

For CI pipelines or long-lived integrations, generate an API key via the Admin UI (**Users → Generate API Token**) or REST API. API keys never expire unless you set a date.

---

## Roles & Permissions

### Pre-built Roles

| Role | Permissions |
|---|---|
| `admin` | All permissions + admin UI access |
| `developer` | Connections, files, records (read/write), DICT (read/write/delete), BP programs (read/write/compile), commands |
| `analyst` | Connections (read), files (read), records (read), DICT (read), commands |
| `readonly` | Connections (read), files (read), records (read), DICT (read) |
| `service_account` | Same as readonly — customise as needed |

### Tool → Permission Mapping

| Tool | Required Permission |
|---|---|
| `list_connections` | `unidata.connection.read` |
| `add_connection`, `close_connection` | `unidata.connection.manage` |
| `list_files` | `unidata.files.read` |
| `select_records`, `read_record`, `query_file`, `read_record_with_fields`, `get_dict_items`, `query_with_dict_fields` | `unidata.record.read` / `unidata.dict.read` |
| `write_record_with_fields` | `unidata.record.write` |
| `execute_command` | `unidata.command.execute` |
| `read_dict_item` | `unidata.dict.read` |
| `write_dict_item`, `update_dict_item` | `unidata.dict.write` |
| `delete_dict_item` | `unidata.dict.delete` |
| `read_bp_program` | `unidata.bp.read` |
| `write_bp_program` | `unidata.bp.compile` |
| `compile_bp_program` | `unidata.bp.compile` |

### Customise Role Permissions

**Via Admin UI:** Roles → select role → add/remove permissions

**Via REST API:**
```bash
# Add a permission to a role
curl -X POST http://localhost:8000/admin/api/roles/<role-id>/permissions \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"permission_key": "unidata.record.write"}'

# Remove a permission
curl -X DELETE http://localhost:8000/admin/api/roles/<role-id>/permissions/<permission-id> \
  -H "Authorization: Bearer <admin-token>"
```

---

## Admin Web UI

Browse to **http://localhost:8000/admin** — login with admin credentials.

| Section | What you can do |
|---|---|
| **Users** | Create, search, edit (role/status), deactivate users |
| **Roles** | Create roles, view assigned permissions |
| **Permissions** | View all tool permissions |
| **Role Permissions** | Assign/remove permissions from roles |
| **API Tokens** | View active tokens, deactivate |
| **Audit Logs** | Browse all tool calls, filter by user/tool/status; read-only |

---

## Audit Logs

Every tool call is logged with: user, tool name, parameters (sanitised — passwords never stored), result status, timestamp, IP address.

**View in Admin UI:** Audit Logs section

**Via REST API:**
```bash
# Recent logs
curl http://localhost:8000/admin/api/audit-logs \
  -H "Authorization: Bearer <admin-token>"

# Filter by tool and status
curl "http://localhost:8000/admin/api/audit-logs?tool_name=write_record_with_fields&result_status=denied" \
  -H "Authorization: Bearer <admin-token>"

# Export as CSV
curl http://localhost:8000/admin/api/audit-logs/export \
  -H "Authorization: Bearer <admin-token>" \
  -o audit_logs.csv
```

---

## U2 UniData Connection Configuration

Connection settings are loaded in this order:

1. **`unidata_config.ini`** (recommended — supports multiple named connections)
2. **Environment variables** (single connection fallback)
3. **`add_connection` tool** (on-demand from Claude)

### INI config file

```ini
[server]
min_connections = 1
max_connections = 10
log_level = INFO
default_connection = production

[connection:production]
host = your-unidata-host
port = 31438
username = your-username
password = your-password
account = C:\U2\UD83\DEMO
service = udcs
auto_connect = true

[connection:test]
host = your-test-host
port = 31438
username = your-username
password = your-password
account = C:\U2\UD83\TEST
service = udcs
auto_connect = false
```

### Environment variables (single connection)

| Variable | Required | Default |
|---|---|---|
| `UNIDATA_HOST` | Yes | — |
| `UNIDATA_USERNAME` | Yes | — |
| `UNIDATA_PASSWORD` | Yes | — |
| `UNIDATA_ACCOUNT` | Yes | — |
| `UNIDATA_PORT` | No | `31438` |
| `UNIDATA_SERVICE` | No | `udcs` |
| `UNIDATA_MIN_CONNECTIONS` | No | `0` (no minimum) |
| `UNIDATA_MAX_CONNECTIONS` | No | `0` (unlimited) |

---

## Environment Variables Reference

| Variable | Required | Description |
|---|---|---|
| `JWT_SECRET_KEY` | **Yes** | JWT signing secret — keep long and random |
| `INITIAL_ADMIN_PASSWORD` | **Yes (first run)** | Password for the seeded `admin` account |
| `DATABASE_URL` | No | Defaults to `sqlite+aiosqlite:///./data/security.db` |
| `JWT_ALGORITHM` | No | `HS256` (default) or `RS256` (production) |
| `JWT_EXPIRE_MINUTES` | No | `60` (default) |
| `ENABLE_DOCS` | No | `true` (default) — set `false` to hide `/docs` in production |

Copy `.env.example` to `.env` for a full template.

---

## API Endpoints

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/health` | GET | None | Health check |
| `/sse` | GET | JWT / API Key / Basic Auth | MCP SSE connection |
| `/messages` | POST | JWT / API Key / Basic Auth | MCP message handler |
| `/auth/login` | GET/POST | None | **User login page** — returns ready-to-use connection configs |
| `/auth/token` | POST | None | Get JWT token (`?username=&password=`) |
| `/admin` | GET | Admin session | Web admin UI |
| `/admin/api/users` | GET/POST | Admin JWT | List / create users |
| `/admin/api/users/{id}` | GET/PUT/DELETE | Admin JWT | Get / update / deactivate user |
| `/admin/api/roles` | GET/POST | Admin JWT | List / create roles |
| `/admin/api/roles/{id}/permissions` | POST/DELETE | Admin JWT | Assign / remove permissions |
| `/admin/api/permissions` | GET | Admin JWT | List all permissions |
| `/admin/api/users/{id}/api-tokens` | GET/POST | Admin JWT | List / create API tokens |
| `/admin/api/api-tokens/{id}` | DELETE | Admin JWT | Revoke API token |
| `/admin/api/audit-logs` | GET | Admin JWT | Query audit log |
| `/admin/api/audit-logs/export` | GET | Admin JWT | Export audit log as CSV |
| `/docs` | GET | None | Interactive API docs (Swagger UI) |

---

## Project Structure

```
UOFastMCP/
├── src/uofast_mcp/
│   ├── app.py                    # FastAPI factory — entry point
│   ├── server.py                 # MCP tool definitions (24 tools)
│   ├── security/
│   │   ├── models.py             # SQLAlchemy ORM models
│   │   ├── database.py           # DB engine + seeder (create_all, no migrations)
│   │   ├── auth.py               # JWT + API key + password helpers
│   │   ├── rbac.py               # RBACEngine (permission checks)
│   │   ├── audit.py              # Audit logger
│   │   ├── permissions.py        # Tool → permission mapping
│   │   └── middleware.py         # FastAPI auth middleware
│   ├── admin/
│   │   ├── router.py             # Admin REST API
│   │   ├── schemas.py            # Pydantic request/response schemas
│   │   └── ui.py                 # SQLAdmin web UI views
│   ├── setup/
│   │   ├── router.py             # Setup wizard routes
│   │   └── templates/            # Jinja2 HTML templates (Bootstrap 5)
│   ├── core/
│   │   ├── connection_manager.py # U2 connection pooling
│   │   └── uopy_operations.py    # U2 database operations
│   └── utils/
│       └── config_loader.py      # INI config loader
├── data/                         # SQLite DB (gitignored)
├── security_config.yaml          # Security settings template
├── unidata_config.ini            # U2 connection config (gitignored)
├── .env.example                  # Environment variable template
├── pyproject.toml
└── requirements.txt
```

---

## Troubleshooting

### 401 Unauthorized
- Token missing or expired — get a new token at `/auth/login` or `POST /auth/token`
- Check header format: `Bearer <jwt>` · `ApiKey <key>` · `Basic <base64(user:pass)>`
- Basic auth: re-generate your token at `/auth/login` if you changed your password

### 403 Forbidden
- User's role doesn't have the required permission
- Check Audit Logs for `result_status=denied` entries
- Admin UI → Roles → verify permissions assigned to user's role

### Server won't start
- `JWT_SECRET_KEY` not set — required at startup
- Port 8000 in use — use `--port 8001`
- Missing `data/` directory — the server creates it automatically

### Database errors
- Delete `data/security.db` and restart to reset (loses all users/audit logs)

### U2 connection fails
- Verify UniData server is reachable: `ping <host>`
- Check credentials in `unidata_config.ini` or environment variables
- Use `add_connection` tool from Claude to test manually

---

## License

MIT License — © 2025 RokiPark. All rights reserved.

Developed by [RokiPark](https://github.com/RokiPark/UOFastMCP).

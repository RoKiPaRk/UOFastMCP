# UOFastMCP

Enterprise Model Context Protocol (MCP) server for U2 UniData/UniVerse databases.
Provides JWT authentication, role-based access control (RBAC), audit logging, and a web-based security admin UI.

**Developer:** [RokiPark](https://github.com/RoKiPaRk/UOFastMCP) · **License:** MIT · **Python:** 3.11+

---

## Features

| Feature | Detail |
|---|---|
| Transport | HTTP/SSE — works over a network, no subprocess needed |
| Authentication | JWT · HTTP Basic Auth |
| Authorization | RBAC — per-tool permissions enforced on every call |
| Audit logging | SQLite log of every tool call (user, tool, params, status, IP, timestamp) |
| Admin UI | Web UI at `/admin` — manage users, roles, permissions, audit logs |
| User self-service | Login page at `/auth/login` — returns ready-to-use `claude mcp add` command |
| Setup wizard | First-run wizard at `/setup` — guided configuration via browser |
| ORM support | `uofast-orm` package — typed model classes for U2 files |

---

## Requirements

- **Python 3.11 or 3.12** — [download from python.org](https://www.python.org/downloads/)
  - During installation on Windows, check **"Add Python to PATH"**
  - Verify: `python --version`

---

## First-Time Installation

### 1. Create a local folder and virtual environment

**Windows:**
```cmd
mkdir C:\UOFastMCP
cd C:\UOFastMCP
python -m venv .venv
.venv\Scripts\activate
```

**macOS / Linux:**
```bash
mkdir ~/UOFastMCP
cd ~/UOFastMCP
python3 -m venv .venv
source .venv/bin/activate
```

Your prompt will change to show `(.venv)` — the virtual environment is active and packages will install into this folder only.

### 2. Install UOFastMCP

```bash
pip install uofast-mcp
```

> **Requires v1.0.2 or later.** Earlier versions have a Jinja2 compatibility bug that causes errors on the `/setup` page. If you have an older version installed, upgrade with:
> ```bash
> pip install --upgrade uofast-mcp
> ```

To verify the install:
```bash
uofast-mcp --help
```

> **Returning after a restart?** Re-activate the virtual environment first:
> - Windows: `C:\UOFastMCP\.venv\Scripts\activate`
> - macOS/Linux: `source ~/UOFastMCP/.venv/bin/activate`

### 3. Set the admin password (optional but recommended)

On first startup, if no password is configured, the default admin password is **`changeme123!`**

To set your own password before first run:

**Windows:**
```cmd
set INITIAL_ADMIN_PASSWORD=YourStrongPassword123!
```

**macOS / Linux:**
```bash
export INITIAL_ADMIN_PASSWORD=YourStrongPassword123!
```

> This password is only used once — on first startup to seed the `admin` account. Change it immediately after login via **Admin UI → Users** if you used the default.

---

## Quick Start

### 1. Set the JWT secret key (required)

**Windows:**
```cmd
set JWT_SECRET_KEY=your-long-random-secret-here
```

**macOS / Linux:**
```bash
export JWT_SECRET_KEY=your-long-random-secret-here
```

Generate a secure value:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 2. Start the server

```bash
uofast-mcp
```

On first startup the server will:
- Create `data/security.db` (SQLite)
- Seed default roles, permissions, and the `admin` user

### 3. Open the setup wizard

Go to **http://localhost:8000/setup** — the wizard guides you through:
- Verifying prerequisites
- Setting JWT secret and admin password
- Configuring your U2 connection
- Generating your Claude connection command

### 4. Verify

```
GET http://localhost:8000/health
→ {"status": "ok", "service": "uofast-mcp"}
```

**Default credentials (first run):**
- Username: `admin`
- Password: `changeme123!` ← change this immediately, or set `INITIAL_ADMIN_PASSWORD` before first startup

---

## Connecting Claude

### Quickest path — login page

1. Open **http://localhost:8000/auth/login**
2. Log in with your username and password
3. Copy the `claude mcp add` command shown on the page and run it

```bash
claude mcp add --transport sse unidata http://localhost:8000/sse --header "Authorization: Basic <your-token>"
```

### Admin provisions a user (one step)

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

Send the `claude_command` to the user — they run it once and are connected.

---

## MCP Tools (20 tools)

### Connection management
| Tool | Description |
|---|---|
| `list_connections` | List all cached connections |
| `add_connection` | Add a named connection to the cache |
| `close_connection` | Close and remove a connection |

### File & record operations
| Tool | Description |
|---|---|
| `list_files` | List files in the current U2 account |
| `select_records` | SELECT records — returns matching IDs |
| `read_record` | Read a record by ID (raw attribute array) |
| `query_file` | Query a file and return full record data |
| `read_record_with_fields` | Read named DICT fields from a record |
| `write_record_with_fields` | Write named DICT fields to a record |

### Dictionary (DICT) management
| Tool | Description |
|---|---|
| `get_dict_items` | List DICT field definitions for a file |
| `query_with_dict_fields` | Query a file returning specific DICT fields |
| `read_dict_item` | Read a single DICT item definition |
| `write_dict_item` | Create or overwrite a DICT item |
| `update_dict_item` | Update an existing DICT item |
| `delete_dict_item` | Delete a DICT item |

### Commands & BP programs
| Tool | Description |
|---|---|
| `execute_command` | Execute a UniQuery command (LIST, COUNT, SELECT, etc.) |
| `read_bp_program` | Read UniBasic source code from a BP file |
| `write_bp_program` | Write UniBasic source code to a BP file |
| `compile_bp_program` | Compile a BP program — returns BASIC compiler output |

---

## Roles & Permissions

### Pre-built roles

| Role | Permissions |
|---|---|
| `admin` | All permissions + admin UI access |
| `developer` | Connections, files, records (read/write), DICT (read/write/delete), BP (read/write/compile), commands |
| `analyst` | Connections (read), files (read), records (read), DICT (read), commands |
| `readonly` | Connections (read), files (read), records (read), DICT (read) |
| `service_account` | Same as readonly — customise via Admin UI |

### Tool → permission mapping

| Permission | Tools |
|---|---|
| `unidata.connection.read` | `list_connections` |
| `unidata.connection.manage` | `add_connection`, `close_connection` |
| `unidata.files.read` | `list_files` |
| `unidata.record.read` | `select_records`, `read_record`, `query_file`, `read_record_with_fields`, `query_with_dict_fields` |
| `unidata.record.write` | `write_record_with_fields` |
| `unidata.dict.read` | `get_dict_items`, `query_with_dict_fields`, `read_dict_item` |
| `unidata.dict.write` | `write_dict_item`, `update_dict_item` |
| `unidata.dict.delete` | `delete_dict_item` |
| `unidata.command.execute` | `execute_command` |
| `unidata.bp.read` | `read_bp_program` |
| `unidata.bp.compile` | `write_bp_program`, `compile_bp_program` |

### Customise via REST API

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -d "username=admin&password=YourAdminPassword" | jq -r .access_token)

# Add permission to a role
curl -X POST http://localhost:8000/admin/api/roles/<role-id>/permissions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"permission_key": "unidata.record.write"}'

# Remove permission
curl -X DELETE http://localhost:8000/admin/api/roles/<role-id>/permissions/<permission-id> \
  -H "Authorization: Bearer $TOKEN"
```

---

## Admin Web UI

Browse to **http://localhost:8000/admin** — login with admin credentials.

| Section | What you can do |
|---|---|
| **Users** | Create, search, edit (role/status), deactivate |
| **Roles** | Create roles, view assigned permissions |
| **Permissions** | View all tool permissions |
| **Role Permissions** | Assign/remove permissions from roles |
| **Audit Logs** | Browse all tool calls, filter by user/tool/status — read-only |

---

## Audit Logs

Every tool call is logged with: user, tool name, parameters (sanitised — passwords never stored), result status, timestamp, IP address.

```bash
# Recent logs
curl http://localhost:8000/admin/api/audit-logs \
  -H "Authorization: Bearer $TOKEN"

# Filter by tool and status
curl "http://localhost:8000/admin/api/audit-logs?tool_name=write_record_with_fields&result_status=denied" \
  -H "Authorization: Bearer $TOKEN"

# Export as CSV
curl http://localhost:8000/admin/api/audit-logs/export \
  -H "Authorization: Bearer $TOKEN" -o audit_logs.csv
```

---

## U2 Connection Configuration

Settings are loaded in this order (first match wins per connection):

1. **`unidata_config.ini`** — supports multiple named connections (recommended)
2. **Environment variables** — single connection fallback

### unidata_config.ini

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
| `UNIDATA_MIN_CONNECTIONS` | No | `0` |
| `UNIDATA_MAX_CONNECTIONS` | No | `0` (unlimited) |

---

## Environment Variables Reference

| Variable | Required | Description |
|---|---|---|
| `JWT_SECRET_KEY` | **Yes** | JWT signing secret — keep long and random |
| `INITIAL_ADMIN_PASSWORD` | **Yes (first run)** | Password for the seeded `admin` account |
| `DATABASE_URL` | No | Defaults to `sqlite+aiosqlite:///./data/security.db` |
| `JWT_ALGORITHM` | No | `HS256` (default) or `RS256` |
| `JWT_EXPIRE_MINUTES` | No | `60` |
| `ENABLE_DOCS` | No | `true` — set `false` to hide `/docs` in production |

Copy `.env.example` to `.env` for a full template.

---

## API Endpoints

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/health` | GET | None | Health check |
| `/sse` | GET | JWT / Basic | MCP SSE connection |
| `/messages` | POST | JWT / Basic | MCP message handler |
| `/auth/login` | GET/POST | None | User login page — returns ready-to-use connection config |
| `/auth/provision` | POST | Admin Basic | Create user + return their `claude mcp add` command |
| `/admin` | GET | Admin session | Web admin UI |
| `/admin/api/users` | GET/POST | Admin JWT | List / create users |
| `/admin/api/users/{id}` | GET/PUT/DELETE | Admin JWT | Get / update / deactivate user |
| `/admin/api/roles` | GET/POST | Admin JWT | List / create roles |
| `/admin/api/roles/{id}/permissions` | POST/DELETE | Admin JWT | Assign / remove permissions |
| `/admin/api/permissions` | GET | Admin JWT | List all permissions |
| `/admin/api/audit-logs` | GET | Admin JWT | Query audit log |
| `/admin/api/audit-logs/export` | GET | Admin JWT | Export audit log as CSV |
| `/setup` | GET | None | First-run setup wizard |
| `/docs` | GET | None | Swagger UI (disable via `ENABLE_DOCS=false`) |

---

## Project Structure

```
UOFastMCP/
├── src/uofast_mcp/
│   ├── app.py                    # FastAPI factory + SSE mount
│   ├── server.py                 # MCP tool definitions (20 tools)
│   ├── security/
│   │   ├── models.py             # SQLAlchemy ORM models
│   │   ├── database.py           # DB engine + seeder (create_all)
│   │   ├── auth.py               # JWT + password helpers
│   │   ├── rbac.py               # Permission enforcement
│   │   ├── audit.py              # Audit logger
│   │   ├── permissions.py        # Tool → permission mapping
│   │   └── middleware.py         # FastAPI auth middleware
│   ├── admin/
│   │   ├── router.py             # Admin + auth REST API
│   │   ├── schemas.py            # Pydantic request/response schemas
│   │   └── ui.py                 # SQLAdmin web UI views
│   ├── setup/
│   │   ├── router.py             # Setup wizard routes
│   │   └── templates/            # Jinja2 HTML templates (Bootstrap 5)
│   ├── core/
│   │   ├── connection_manager.py # U2 connection pooling
│   │   └── uopy_operations.py    # U2 database operations
│   └── utils/
│       ├── config_loader.py      # INI config loader
│       └── credential_store.py   # Credential helpers
├── data/                         # SQLite DB — created at runtime (gitignored)
├── security_config.yaml          # Security settings
├── unidata_config.ini            # U2 connection config (gitignored)
├── .env.example                  # Environment variable template
└── pyproject.toml
```

---

## Troubleshooting

### 401 Unauthorized
- Get a new token at `/auth/login`
- Header format: `Basic <base64(user:pass)>` or `Bearer <jwt>`

### 403 Forbidden
- User's role lacks the required permission
- Admin UI → Roles → verify permissions assigned to the role
- Check Audit Logs for `result_status=denied` entries

### Server won't start
- `JWT_SECRET_KEY` not set — required at startup
- Port 8000 in use — `uvicorn uofast_mcp.app:app --port 8001`

### Database errors
- Delete `data/security.db` and restart to reset (loses all users/audit logs)

### U2 connection fails
- Verify host reachable: `ping <host>`
- Check credentials in `unidata_config.ini` or env vars
- Use `add_connection` tool from Claude to test on-demand

---

## License

MIT License — © 2025 RokiPark. All rights reserved.

Developed by [RokiPark](https://github.com/RoKiPaRk/UOFastMCP).

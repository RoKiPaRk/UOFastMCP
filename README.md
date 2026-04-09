# UOFastMCP

Enterprise MCP server for U2 UniData/UniVerse — JWT auth, RBAC, audit logging, **built-in admin UI** to simplify the setup process.

**Developer:** [RokiPark](https://github.com/RoKiPaRk/UOFastMCP) · **License:** MIT · **Python:** 3.11+

---

## Install & Run

```bash
# 1. Create a folder and virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. Install
pip install uofast-mcp

# 3. Set required env var
export JWT_SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
# Windows: set JWT_SECRET_KEY=<paste output of above>

# 4. Start
uofast-mcp
```

Server starts at **http://localhost:8000**

---

## First-Time Setup

1. Open **http://localhost:8000/admin**
2. Log in: `admin` / `changeme123!`

![Admin login](docs/screenshots/admin-login.png)

3. Click **Server Setup** in the left menu
4. Follow the 5-step wizard:
   - Check prerequisites
   - Set JWT secret + change admin password
   - Configure your U2 connection (with live test)
   - Review generated `.env` and `unidata_config.ini`
   - Copy your Claude / VSCode / CLI connection config

![Setup wizard — U2 connection step](docs/screenshots/setup-connection.png)

---

## Connect Claude

Run the command from Step 5 of the wizard, or get it any time from **http://localhost:8000/auth/login**.

```bash
claude mcp add --transport sse UOFastMCP http://localhost:8000/sse \
  --header "Authorization: Basic <your-base64-token>"
```

---

## MCP Tools (20 tools)

| Category | Tools |
|---|---|
| Connections | `list_connections`, `add_connection`, `close_connection` |
| Files & Records | `list_files`, `select_records`, `read_record`, `query_file`, `read_record_with_fields`, `write_record_with_fields` |
| Dictionary | `get_dict_items`, `query_with_dict_fields`, `read_dict_item`, `write_dict_item`, `update_dict_item`, `delete_dict_item` |
| Commands & BP | `execute_command`, `read_bp_program`, `write_bp_program`, `compile_bp_program` |

---

## Roles

| Role | Access |
|---|---|
| `admin` | Everything |
| `developer` | Read/write records, DICT, BP + manage connections |
| `analyst` | Read records, DICT + execute commands |
| `readonly` | Read connections, files, records, DICT |
| `service_account` | Same as readonly — customisable |

Manage users and permissions at **http://localhost:8000/admin**.

---

## Admin UI

**http://localhost:8000/admin** — login with admin credentials.

| Section | Purpose |
|---|---|
| Users | Create/edit users, assign roles |
| Roles / Permissions | Manage RBAC |
| Audit Logs | Every tool call logged — read-only |
| Server Setup | Change password, JWT secret, U2 connection |

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `JWT_SECRET_KEY` | Yes | — | Long random string — keep secret |
| `INITIAL_ADMIN_PASSWORD` | No | `changeme123!` | Admin password on first startup |
| `DATABASE_URL` | No | `sqlite+aiosqlite:///./data/security.db` | Security DB location |
| `ENABLE_DOCS` | No | `true` | Set `false` to hide `/docs` in production |

---

## API Endpoints

| Endpoint | Auth | Description |
|---|---|---|
| `GET /health` | None | Health check |
| `GET /sse` | Basic | MCP SSE connection |
| `GET/POST /auth/login` | None | Login page — returns ready-to-use connection config |
| `POST /auth/provision` | Admin | Create user + return their connection command |
| `GET /admin` | Admin session | Web admin UI |
| `GET /admin/setup` | Admin session | Server setup wizard |
| `GET /docs` | None | Swagger UI |

---

## Troubleshooting

**Server won't start** — `JWT_SECRET_KEY` not set, or port 8000 in use (`uvicorn uofast_mcp.app:app --port 8001`).

**401 Unauthorized** — get credentials from `/auth/login`.

**403 Forbidden** — user's role lacks the required permission; check Admin → Role Permissions.

**U2 connection fails** — re-run Server Setup wizard to update credentials and test live.

**Reset everything** — delete `data/security.db` and restart (loses all users and audit logs).

---

## License

MIT — © 2025 RokiPark. All rights reserved.

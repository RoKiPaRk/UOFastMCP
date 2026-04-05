# Changelog

© 2025 RokiPark. All rights reserved.

All notable changes to this project will be documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.0.0] — 2026-04-04

### Added
- HTTP/SSE transport via FastAPI + uvicorn (replaces stdio)
- JWT + API Key + HTTP Basic Auth authentication
- RBAC: Users → Roles → Permissions (per-tool enforcement, 24 tools)
- SQLite audit log of every tool call
- Security Admin Web UI at `/admin` (SQLAdmin)
- User self-service login page at `/auth/login` with ready-to-use `claude mcp add` command
- Setup wizard at `/setup` for first-run guided configuration
- `uofast-orm` PyPI package integration (replaces local UOFastORM/)
- `uofast-mcp` console script entry point

### Changed
- Minimum Python version raised to 3.11
- Removed Docker/Azure deployment (run directly via uvicorn)
- Removed Alembic migrations (schema created via SQLAlchemy `create_all`)

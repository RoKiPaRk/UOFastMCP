# Changelog

© 2025 RokiPark. All rights reserved.

All notable changes to this project will be documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.0.6] — 2026-04-06

### Fixed
- Rewrote setup/router.py from scratch — clean implementation with correct
  Starlette 0.36+ `TemplateResponse(request, name, context)` API on all 10 calls.
  Removed all Jinja2 cache workarounds that were causing cascading errors.

## [1.0.5] — 2026-04-05

### Fixed
- Updated all `TemplateResponse` calls to Starlette 0.36+ API: `request` is now the first positional argument, not a key inside the context dict. This was the root cause of `AttributeError: 'dict' object has no attribute 'split'` on fresh installs with current Starlette (0.36+).
- Removed Jinja2 cache workarounds — no longer needed with correct Starlette API usage.

### Added
- Python 3.13 support confirmed; added to classifiers

## [1.0.4] — 2026-04-05

### Fixed
- Attempted `cache_size=0` via Jinja2 `Environment` — caused `unexpected keyword argument` error on Starlette's `Jinja2Templates(env=...)` path

## [1.0.3] — 2026-04-05

### Fixed
- Set `cache_size=0` on Jinja2Templates — partially fixed but caused `unexpected keyword argument` error on some Starlette versions

## [1.0.2] — 2026-04-05

### Fixed
- Pinned `jinja2>=3.1.6` in package dependencies (partial fix — did not help users with 3.1.5 already installed)

## [1.0.1] — 2026-04-04

### Changed
- Updated PyPI metadata: description, keywords, classifiers, `Framework :: FastAPI`
- Added `[project.optional-dependencies] dev` extras for contributors

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

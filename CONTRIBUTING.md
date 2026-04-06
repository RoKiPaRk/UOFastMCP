# Contributing to UOFastMCP

© 2025 RokiPark. All rights reserved.

## Setup

```bash
git clone https://github.com/RoKiPaRk/UOFastMCP.git
cd UOFastMCP
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Running locally

```bash
cp .env.example .env        # fill in your values
uofast-mcp
# or: uvicorn uofast_mcp.app:app --reload --port 8000
```

## Code style

```bash
ruff check src/
ruff format src/
```

## Tests

```bash
pytest tests/ -v
```

## Submitting changes

1. Fork the repo and create a branch from `main`
2. Make your changes — keep commits focused
3. Ensure `ruff check` and `pytest` pass
4. Open a pull request against `main`

## Security

**Never commit credentials.** `unidata_config.ini` and `.env` are gitignored.
If you accidentally commit a secret, rotate it immediately and open a security issue.

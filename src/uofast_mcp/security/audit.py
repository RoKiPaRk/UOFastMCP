"""Fire-and-forget audit logging to the AuditLog table."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from .database import AsyncSessionLocal
from .models import AuditLog

logger = logging.getLogger(__name__)

# Fields whose values should never be stored in audit log params
_SENSITIVE_KEYS = frozenset({
    "password", "passwd", "secret", "token", "api_key", "apikey",
    "authorization", "credential", "credentials",
})


def _sanitize_params(params: dict[str, Any]) -> dict[str, Any]:
    """Remove sensitive fields from params before storing."""
    return {
        k: ("***" if k.lower() in _SENSITIVE_KEYS else v)
        for k, v in params.items()
    }


class AuditLogger:
    def log_event(
        self,
        *,
        user_id: int | None,
        tool_name: str,
        action: str,
        params: dict[str, Any] | None = None,
        result_status: str,
        error_message: str | None = None,
        ip_address: str | None = None,
    ) -> None:
        """Schedule a fire-and-forget DB insert. Non-blocking."""
        asyncio.create_task(
            self._write_log(
                user_id=user_id,
                tool_name=tool_name,
                action=action,
                params=params or {},
                result_status=result_status,
                error_message=error_message,
                ip_address=ip_address,
            )
        )

    async def _write_log(
        self,
        *,
        user_id: int | None,
        tool_name: str,
        action: str,
        params: dict[str, Any],
        result_status: str,
        error_message: str | None,
        ip_address: str | None,
    ) -> None:
        try:
            clean_params = _sanitize_params(params)
            async with AsyncSessionLocal() as session:
                session.add(AuditLog(
                    user_id=user_id,
                    tool_name=tool_name,
                    action=action,
                    params_summary=json.dumps(clean_params, default=str),
                    result_status=result_status,
                    error_message=error_message,
                    timestamp=datetime.now(tz=timezone.utc),
                    ip_address=ip_address,
                ))
                await session.commit()
        except Exception:
            logger.exception("Failed to write audit log entry")


audit_logger = AuditLogger()

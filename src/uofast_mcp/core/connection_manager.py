"""
Connection Manager Module
==========================

Manages U2 Unidata connection pooling with min/max limits.

Pool per named connection config:
- On startup, `min_connections` sessions are pre-opened synchronously.
- When a tool needs a session it calls `async with manager.session(name)`.
- Released sessions go back into the pool; errored sessions are discarded.
- New sessions are created on demand up to `max_connections` (0 = unlimited).
- If the pool is at max, the caller waits asynchronously for a release.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import defaultdict
from typing import Any, Dict, Optional

import uopy

logger = logging.getLogger("uofast-mcp.connection")


# ---------------------------------------------------------------------------
# Single connection wrapper (unchanged public API)
# ---------------------------------------------------------------------------

class UnidataConnection:
    """Manages a single U2 Unidata session lifecycle."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        account: str,
        service: str = "udcs",
        name: str = "default",
    ):
        self.name = name
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.account = account
        self.service = service
        self.conn = None

    def connect(self) -> uopy.Session:
        if self.conn is None:
            logger.info(
                "[%s] Connecting to %s:%s account %s",
                self.name, self.host, self.port, self.account,
            )
            self.conn = uopy.connect(
                host=self.host,
                user=self.username,
                password=self.password,
                account=self.account,
                service=self.service,
                port=self.port,
            )
            logger.info("[%s] Connected successfully", self.name)
        return self.conn

    def disconnect(self):
        if self.conn:
            logger.info("[%s] Disconnecting from Unidata", self.name)
            try:
                self.conn.close()
            except Exception as exc:
                logger.warning("[%s] Error during disconnect: %s", self.name, exc)
            self.conn = None

    def is_connected(self) -> bool:
        return self.conn is not None

    def reconnect(self) -> uopy.Session:
        if not self.is_connected():
            logger.info("[%s] Reconnecting...", self.name)
            self.connect()
        return self.conn


# ---------------------------------------------------------------------------
# Connection pool manager
# ---------------------------------------------------------------------------

class ConnectionManager:
    """
    Connection pool for U2 Unidata.

    One pool (asyncio.Queue) per named connection config.
    Pool size is bounded by min_connections (floor) and max_connections (ceiling).
    """

    def __init__(
        self,
        default_connection_name: str = "default",
        min_connections: int = 0,
        max_connections: int = 0,
    ):
        """
        Args:
            default_connection_name: Name used when no name is given to acquire/session.
            min_connections: Pre-open this many sessions per config at startup.
            max_connections: Hard cap on total sessions per config (0 = unlimited).
        """
        self._default_connection_name = default_connection_name
        self._min_connections = min_connections
        self._max_connections = max_connections

        # Connection parameters per name (auto_connect stripped out)
        self._configs: Dict[str, dict] = {}

        # Available sessions per name (producer/consumer queue)
        self._pool: Dict[str, asyncio.Queue] = {}

        # Total sessions (available + checked-out) per name
        self._total: Dict[str, int] = defaultdict(int)

        # Serialises new-connection creation to avoid race conditions
        self._create_lock: asyncio.Lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _queue(self, name: str) -> asyncio.Queue:
        if name not in self._pool:
            self._pool[name] = asyncio.Queue()
        return self._pool[name]

    def _make_conn(self, name: str) -> UnidataConnection:
        """Build a UnidataConnection from the stored config (does NOT connect)."""
        if name not in self._configs:
            raise RuntimeError(
                f"No configuration registered for connection '{name}'. "
                "Use the add_connection tool or unidata_config.ini to add one."
            )
        return UnidataConnection(name=name, **self._configs[name])

    # ------------------------------------------------------------------
    # Startup / config registration
    # ------------------------------------------------------------------

    def register_config(self, name: str, config: dict) -> None:
        """Store connection parameters (strips auto_connect key)."""
        self._configs[name] = {k: v for k, v in config.items() if k != "auto_connect"}

    def warm_connections(self, name: str, count: int) -> None:
        """
        Synchronously pre-open `count` sessions for the named config.

        Call this from synchronous startup code; uopy.connect() is blocking.
        Sessions are placed in the pool queue ready for immediate use.
        """
        if name not in self._configs:
            raise RuntimeError(f"No config registered for '{name}'")

        to_open = max(0, count - self._total[name])
        q = self._queue(name)

        opened = 0
        for _ in range(to_open):
            if self._max_connections > 0 and self._total[name] >= self._max_connections:
                break
            conn = self._make_conn(name)
            conn.connect()
            q.put_nowait(conn)
            self._total[name] += 1
            opened += 1

        logger.info("[%s] Pool warmed: %d session(s) open", name, self._total[name])

    # ------------------------------------------------------------------
    # Acquire / Release (async)
    # ------------------------------------------------------------------

    async def acquire(self, name: Optional[str] = None) -> UnidataConnection:
        """
        Borrow a connection from the pool.

        1. Returns an available session immediately if the pool is non-empty.
        2. Creates a new session if under max_connections.
        3. Waits asynchronously if at max until one is released.
        """
        if name is None:
            name = self._default_connection_name

        q = self._queue(name)

        # 1 — Try the pool first (no waiting)
        try:
            conn = q.get_nowait()
            if not conn.is_connected():
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, conn.connect)
            return conn
        except asyncio.QueueEmpty:
            pass

        # 2 — Create a new session if under the cap
        async with self._create_lock:
            under_max = (
                self._max_connections == 0
                or self._total[name] < self._max_connections
            )
            if under_max:
                conn = self._make_conn(name)
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, conn.connect)
                self._total[name] += 1
                return conn

        # 3 — At max: wait for a release
        logger.info(
            "[%s] Pool at max (%d), waiting for available session…",
            name, self._max_connections,
        )
        conn = await q.get()
        if not conn.is_connected():
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, conn.connect)
        return conn

    def release(self, conn: UnidataConnection) -> None:
        """Return a healthy connection to the pool."""
        self._queue(conn.name).put_nowait(conn)

    @contextlib.asynccontextmanager
    async def session(self, name: Optional[str] = None):
        """
        Async context manager — acquire a uopy.Session, yield it, then release.

        Usage::

            async with connection_manager.session() as uopy_session:
                ops = UnidataOperations(uopy_session)
                ...

        On exception the connection is closed and removed from the pool total so
        the next acquire can open a fresh one.
        """
        conn = await self.acquire(name)
        try:
            yield conn.conn  # raw uopy.Session
        except Exception:
            # Discard potentially broken session rather than returning it
            try:
                conn.disconnect()
            except Exception:
                pass
            self._total[conn.name] -= 1
            raise
        else:
            self.release(conn)

    # ------------------------------------------------------------------
    # Admin / management methods
    # ------------------------------------------------------------------

    def close_connection(self, name: str) -> bool:
        """Drain and close all pooled sessions for a named config."""
        if name not in self._configs and name not in self._pool:
            logger.warning("Connection '%s' not found", name)
            return False

        if name in self._pool:
            q = self._pool[name]
            while True:
                try:
                    conn = q.get_nowait()
                    conn.disconnect()
                    self._total[name] -= 1
                except asyncio.QueueEmpty:
                    break
            del self._pool[name]

        self._configs.pop(name, None)
        self._total.pop(name, None)
        logger.info("Connection pool '%s' closed", name)
        return True

    def close_all_connections(self) -> None:
        """Close every pool."""
        for name in list(self._configs.keys()):
            self.close_connection(name)
        logger.info("All connection pools closed")

    def get_or_create_connection(
        self,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> "ConnectionManager":
        """
        Legacy/convenience method: register a config and warm the pool synchronously.

        Used by initialize_server() auto-connect logic and the add_connection tool.
        Returns self so callers that check truthiness still work.
        """
        if name is None:
            name = self._default_connection_name
        if config is not None:
            self.register_config(name, config)
        warm_count = max(1, self._min_connections)
        if name in self._configs:
            self.warm_connections(name, warm_count)
        return self

    def list_connections(self) -> Dict[str, Dict[str, str]]:
        """Return a summary of every configured connection pool."""
        result = {}
        for conn_name, cfg in self._configs.items():
            q = self._pool.get(conn_name)
            available = q.qsize() if q else 0
            total = self._total[conn_name]
            result[conn_name] = {
                "host": cfg["host"],
                "port": str(cfg["port"]),
                "account": cfg["account"],
                "status": "Connected" if total > 0 else "Disconnected",
                "pool_total": str(total),
                "pool_available": str(available),
            }
        return result

    def has_connection(self, name: Optional[str] = None) -> bool:
        if name is None:
            name = self._default_connection_name
        return name in self._configs

    def connection_count(self) -> int:
        """Total open sessions across all pools."""
        return sum(self._total.values())

    def check_pool_health(self) -> dict:
        """Return a health summary for the default connection pool."""
        active = self.connection_count()
        return {
            "active": active,
            "min_connections": self._min_connections,
            "max_connections": self._max_connections,
            "below_minimum": self._min_connections > 0 and active < self._min_connections,
            "at_maximum": self._max_connections > 0 and active >= self._max_connections,
        }

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def default_connection_name(self) -> str:
        return self._default_connection_name

    @default_connection_name.setter
    def default_connection_name(self, value: str) -> None:
        self._default_connection_name = value

    @property
    def min_connections(self) -> int:
        return self._min_connections

    @property
    def max_connections(self) -> int:
        return self._max_connections

    # ------------------------------------------------------------------
    # Deprecated shim (keep until server.py is fully migrated)
    # ------------------------------------------------------------------

    def ensure_connection(self, name: Optional[str] = None) -> uopy.Session:
        """
        Deprecated synchronous accessor — use ``async with session()`` instead.

        Returns the first available session from the pool without removing it.
        Raises RuntimeError if no sessions are open.
        """
        if name is None:
            name = self._default_connection_name
        q = self._pool.get(name)
        if q and not q.empty():
            # Peek: get + put back
            conn = q.get_nowait()
            q.put_nowait(conn)
            if not conn.is_connected():
                conn.connect()
            return conn.conn
        raise RuntimeError(
            f"No available sessions in pool '{name}'. "
            "Ensure auto_connect=true or warm_connections() has been called."
        )

"""
UOFast MCP - U2 Unidata MCP Server
===================================

A Model Context Protocol (MCP) server for U2 Unidata databases.

Provides tools for:
- Connection management
- File queries and operations
- Record operations
- Custom UniQuery commands
"""

__version__ = "1.1.0"
__author__ = "RokiPark"
__copyright__ = "Copyright (c) 2025 RokiPark"

__all__ = ["__version__", "run"]


def run() -> None:
    """Entry point for the ``uofast-mcp`` console script."""
    import uvicorn
    uvicorn.run(
        "uofast_mcp.app:app",
        host="0.0.0.0",
        port=8000,
        # Keep HTTP connections alive for 75 s — just under the common 80 s
        # proxy/load-balancer idle timeout so SSE streams aren't killed silently.
        timeout_keep_alive=75,
        # Graceful shutdown: finish in-flight SSE sessions before exiting.
        timeout_graceful_shutdown=10,
        log_level="info",
    )

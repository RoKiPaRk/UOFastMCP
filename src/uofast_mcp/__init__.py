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

__version__ = "1.0.8"
__author__ = "RokiPark"
__copyright__ = "Copyright (c) 2025 RokiPark"

__all__ = ["__version__", "run"]


def run() -> None:
    """Entry point for the ``uofast-mcp`` console script."""
    import uvicorn
    uvicorn.run("uofast_mcp.app:app", host="0.0.0.0", port=8000)

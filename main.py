"""
Main entry point for UOFast MCP Server.

This module provides the entry point for running the Unidata MCP server.
"""

import sys
from pathlib import Path

# Add src directory to path
src_dir = Path(__file__).parent / "src"
sys.path.insert(0, str(src_dir))

from src.uofast_mcp import run

if __name__ == "__main__":
    run()

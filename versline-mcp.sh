#!/bin/bash
# versline MCP server entry point
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}$SCRIPT_DIR/src"
exec "$SCRIPT_DIR/venv/bin/python3" -m versline.mcp.server "$@"

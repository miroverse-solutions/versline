#!/bin/bash
# versline MCP server entry point
cd "$(dirname "$0")"
export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}$(pwd)/src"
exec python3 -m versline.mcp.server "$@"

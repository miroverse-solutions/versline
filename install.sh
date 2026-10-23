#!/usr/bin/env sh
# Versline installer for macOS/Linux.
# Usage:  curl -LsSf https://raw.githubusercontent.com/miroverse-solutions/versline/main/install.sh | sh
set -eu

if ! command -v uv >/dev/null 2>&1; then
    echo "Installing uv (Python tool manager)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    PATH="$HOME/.local/bin:$PATH"
    export PATH
fi

echo "Installing Versline..."
uv tool install --force --python 3.12 "git+https://github.com/miroverse-solutions/versline"
uv tool update-shell >/dev/null 2>&1 || true

echo
echo "Done. Open a NEW terminal, then run:  versline init"

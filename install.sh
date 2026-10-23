#!/usr/bin/env sh
# Versline installer for macOS/Linux. Installs the latest GitHub release; no git or Python needed.
# Usage:  curl -LsSf https://raw.githubusercontent.com/miroverse-solutions/versline/main/install.sh | sh
set -eu

REPO="miroverse-solutions/versline"

if ! command -v uv >/dev/null 2>&1; then
    echo "Installing uv (Python tool manager)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    PATH="$HOME/.local/bin:$PATH"
    export PATH
fi

echo "Finding the latest Versline release..."
WHEEL_URL=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" \
    | grep -o '"browser_download_url": *"[^"]*\.whl"' \
    | head -n 1 \
    | sed 's/.*"\(https[^"]*\)"/\1/') || true

if [ -z "${WHEEL_URL:-}" ]; then
    echo "No published release with a .whl file was found at https://github.com/$REPO/releases" >&2
    exit 1
fi

echo "Installing $WHEEL_URL"
uv tool install --force --python 3.12 "$WHEEL_URL"
uv tool update-shell >/dev/null 2>&1 || true

echo
echo "Done. Open a NEW terminal, then run:  versline init"

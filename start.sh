#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────
# start.sh – launch the Temp-Mon backend server
# ──────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load PORT from .env if present
PORT=$(grep -E "^PORT=" .env 2>/dev/null | cut -d= -f2 | tr -d '[:space:]') || PORT=8000

echo "Starting Temp-Mon on port ${PORT}..."
echo "Open http://$(hostname -I | awk '{print $1}'):${PORT}"

exec python3 backend/main.py

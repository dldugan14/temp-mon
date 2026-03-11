#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────
# start.sh – launch the Temp-Mon backend server
# ──────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/.venv"

if [[ ! -f "$VENV_DIR/bin/python" ]]; then
  echo "ERROR: Virtual environment not found. Run ./install.sh first."
  exit 1
fi

# Activate venv
# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

# Load PORT from .env if present
PORT=$(grep -E "^PORT=" .env 2>/dev/null | cut -d= -f2 | tr -d '[:space:]') || PORT=8000

# If managed service is already running, don't start a duplicate instance.
if command -v systemctl >/dev/null 2>&1; then
  if systemctl is-active --quiet temp-mon.service; then
    echo "temp-mon.service is already running."
    echo "Open http://$(hostname -I | awk '{print $1}'):${PORT}"
    echo "Use: sudo systemctl restart temp-mon"
    exit 0
  fi
fi

# Avoid hard crash when the chosen port is already occupied.
if command -v ss >/dev/null 2>&1; then
  if ss -ltn "( sport = :${PORT} )" | grep -q LISTEN; then
    echo "ERROR: Port ${PORT} is already in use."
    echo "Stop the process using it, or choose a different PORT in .env."
    if command -v lsof >/dev/null 2>&1; then
      lsof -iTCP:"${PORT}" -sTCP:LISTEN || true
    fi
    exit 1
  fi
fi

echo "Starting Temp-Mon on port ${PORT}..."
echo "Open http://$(hostname -I | awk '{print $1}'):${PORT}"

exec python3 backend/main.py

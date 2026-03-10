#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────
# install.sh – one-time setup for temp-mon on Raspberry Pi
# ──────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/.venv"

echo "==> [1/4] Creating Python virtual environment..."
python3 -m venv "$VENV_DIR"
# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

echo "    Installing Python dependencies into venv..."
pip install --upgrade pip --quiet
pip install -r backend/requirements.txt --quiet

# RPi.GPIO – only install on actual Pi hardware
if [[ "$(uname -m)" == arm* || "$(uname -m)" == aarch64 ]]; then
  echo "==> [1a] Raspberry Pi detected – installing RPi.GPIO..."
  pip install RPi.GPIO --quiet
  # Enable 1-Wire interface (required for DS18B20)
  BOOT_CFG="/boot/firmware/config.txt"
  [[ -f "$BOOT_CFG" ]] || BOOT_CFG="/boot/config.txt"   # older Pi OS path
  if ! grep -q "^dtoverlay=w1-gpio" "$BOOT_CFG" 2>/dev/null; then
    echo "dtoverlay=w1-gpio" | sudo tee -a "$BOOT_CFG" > /dev/null
    echo "    NOTE: Added 1-Wire overlay to $BOOT_CFG – a reboot is required."
  fi
else
  echo "    Not running on Pi – skipping RPi.GPIO (simulation mode will be used)"
fi

echo "==> [2/4] Installing Node.js dependencies..."
cd frontend
npm install --silent
cd ..

echo "==> [3/4] Building frontend..."
cd frontend
npm run build
cd ..

echo "==> [4/4] Done!"
echo ""
echo "  Start the server with:  ./start.sh"
echo "  Then open:              http://localhost:8000"
echo "  (venv location: $VENV_DIR)"

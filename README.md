# 🌡️ Temp-Mon

A lightweight temperature monitoring control panel for Raspberry Pi 4 B+.  
Monitors **8 × DS18B20** sensors over 1-Wire and controls **2 relays** (fan + battery power) via GPIO based on configurable temperature bounds.

---

## Architecture

```
┌─────────────────────────────────────────┐
│          Raspberry Pi 4 B+              │
│                                         │
│  ┌──────────────┐   ┌────────────────┐  │
│  │  DS18B20 ×8  │   │  Relay Board   │  │
│  │  (1-Wire)    │   │  Fan: GPIO 17  │  │
│  └──────┬───────┘   │  Bat: GPIO 27  │  │
│         │           └───────┬────────┘  │
│  ┌──────▼───────────────────▼────────┐  │
│  │   Python FastAPI Backend          │  │
│  │   • Reads sensors every N sec     │  │
│  │   • Evaluates temp thresholds     │  │
│  │   • Controls relays (hysteresis)  │  │
│  │   • Serves React UI + SSE stream  │  │
│  └───────────────────────────────────┘  │
│                  ↕ SSE / REST           │
│  ┌───────────────────────────────────┐  │
│  │   React + MUI Frontend (built)    │  │
│  │   • Live temp gauge cards         │  │
│  │   • Relay status + manual ctrl    │  │
│  │   • Threshold display             │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

---

## Requirements

| Component | Minimum |
|-----------|---------|
| Raspberry Pi 4 B+ | Raspberry Pi OS Bookworm (64-bit) |
| Python | 3.9+ |
| Node.js | 18+ (for building frontend only) |
| DS18B20 sensors | Up to 8, on single 1-Wire bus |
| Relay board | 2-channel, Active-HIGH |

**Wiring:**

| Signal | Pin (BCM) |
|--------|-----------|
| 1-Wire data (DS18B20) | GPIO 4 (default) |
| Fan relay | GPIO 17 |
| Battery relay | GPIO 27 |

> Pin numbers are configurable in `.env`.

---

## Quick Start

### 1 – Clone / copy to Pi

```bash
git clone <repo> ~/temp-mon
cd ~/temp-mon
```

### 2 – Configure

Edit `.env` to match your hardware and desired thresholds:

```ini
FAN_ON_TEMP=30.0      # Any sensor >= this → fan ON
FAN_OFF_TEMP=25.0     # All sensors <= this → fan OFF
BAT_ON_TEMP=40.0      # Any sensor >= this → battery relay ON
BAT_OFF_TEMP=35.0     # All sensors <= this → battery relay OFF

FAN_RELAY_PIN=17
BAT_RELAY_PIN=27

POLL_INTERVAL=5       # Seconds between sensor reads
PORT=8000
SIMULATE=false        # Set true for testing without hardware
```

### 3 – Install dependencies & build UI

```bash
chmod +x install.sh start.sh
./install.sh
```

> **First run only.** This installs Python packages, enables the 1-Wire overlay, installs npm deps, builds the React frontend into `frontend/dist/`, and enables `temp-mon.service` for automatic startup.

### 4 – Start

```bash
./start.sh
```

Open `http://<pi-ip>:8000` in any browser on your network.

---

## Autostart (systemd)

Autostart is configured automatically by `./install.sh`.

```bash
sudo systemctl status temp-mon --no-pager
sudo journalctl -u temp-mon -f   # view logs
```

---

## Project Structure

```
temp-mon/
├── .env                      # All configuration (thresholds, pins, port)
├── install.sh                # One-time setup script
├── start.sh                  # Launch script
├── temp-mon.service          # systemd unit for autostart
│
├── backend/
│   ├── main.py               # FastAPI app, SSE, REST, static serving
│   ├── controller.py         # Control loop, threshold logic, relay actuation
│   ├── sensors.py            # DS18B20 1-Wire reader (+ simulation mode)
│   ├── relay.py              # GPIO relay abstraction (+ simulation mode)
│   └── requirements.txt
│
└── frontend/
    ├── package.json
    ├── vite.config.ts
    ├── index.html
    └── src/
        ├── App.tsx
        ├── main.tsx
        ├── theme.ts          # MUI dark theme
        ├── types.ts          # Shared TypeScript interfaces
        ├── hooks/
        │   └── useSystemState.ts   # SSE connection + relay API calls
        └── components/
            ├── Header.tsx          # Title + connection status
            ├── SensorGrid.tsx      # 4×2 grid of sensor cards
            ├── SensorCard.tsx      # Individual sensor (temp + colour bar)
            ├── RelayPanel.tsx      # Fan & battery relay status + override
            └── ConfigBounds.tsx    # Threshold display
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/status` | Snapshot of current system state |
| GET | `/api/stream` | SSE stream – pushes JSON on every poll |
| POST | `/api/relay/{fan\|battery}/override?state=true\|false` | Force relay on/off |
| DELETE | `/api/relay/{fan\|battery}/override` | Return relay to auto mode |

---

## Relay Control Logic

Hysteretic (deadband) control prevents rapid relay cycling:

```
Fan ON   → when max(sensors) ≥ FAN_ON_TEMP
Fan OFF  → when max(sensors) ≤ FAN_OFF_TEMP

Battery ON  → when max(sensors) ≥ BAT_ON_TEMP
Battery OFF → when max(sensors) ≤ BAT_OFF_TEMP
```

Manual overrides from the UI take priority over automatic control until explicitly released.

---

## Development (non-Pi)

Set `SIMULATE=true` in `.env`. The backend will generate slowly-drifting fake temperatures so the full UI can be tested without any hardware.

```bash
# Terminal 1 – backend (with hot reload)
cd backend
pip install fastapi uvicorn python-dotenv
uvicorn main:app --reload --port 8000

# Terminal 2 – frontend dev server (proxies /api to :8000)
cd frontend
npm install
npm run dev
```

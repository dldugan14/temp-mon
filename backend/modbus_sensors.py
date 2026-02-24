"""
RS485 / Modbus RTU temperature sensor reader.

Expects sensors that expose a signed 16-bit temperature value in a single
holding register (function code 0x03). Raw value * MODBUS_TEMP_SCALE = °C.
This covers the vast majority of cheap RS485 temperature sensor modules.

Falls back to safeSimulation when SIMULATE=true or MODBUS_ENABLED=false.
"""
from __future__ import annotations

import logging
import math
import os
import random
import time
from dataclasses import dataclass
from typing import List

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
SIMULATE       = os.getenv("SIMULATE", "false").lower() == "true"
ENABLED        = os.getenv("MODBUS_ENABLED", "true").lower() == "true"
PORT           = os.getenv("MODBUS_PORT", "/dev/ttyUSB0")
BAUD           = int(os.getenv("MODBUS_BAUD", "9600"))
UNIT_IDS_RAW   = os.getenv("MODBUS_UNIT_IDS", "1,2,3")
UNIT_IDS: list[int] = [int(u.strip()) for u in UNIT_IDS_RAW.split(",") if u.strip()]
TEMP_REGISTER  = int(os.getenv("MODBUS_TEMP_REGISTER", "0"))
TEMP_SCALE     = float(os.getenv("MODBUS_TEMP_SCALE", "0.1"))
TIMEOUT        = float(os.getenv("MODBUS_TIMEOUT", "1.0"))


@dataclass
class ModbusSensorReading:
    unit_id: int
    sensor_id: str   # e.g. "mb-01"
    name: str        # e.g. "Modbus 1"
    bus: str         # always "modbus"
    temperature: float
    error: bool


# ── Simulated state ───────────────────────────────────────────────────────────
_sim_temps: dict[int, float] = {uid: 24.0 + random.uniform(-3, 3) for uid in UNIT_IDS}
_sim_dirs:  dict[int, float] = {uid: random.choice([-1, 1]) * 0.08 for uid in UNIT_IDS}


def _simulate() -> List[ModbusSensorReading]:
    readings: List[ModbusSensorReading] = []
    for uid in UNIT_IDS:
        _sim_temps[uid] += _sim_dirs[uid] + random.uniform(-0.03, 0.03)
        if _sim_temps[uid] > 52:
            _sim_dirs[uid] = -abs(_sim_dirs[uid])
        elif _sim_temps[uid] < 18:
            _sim_dirs[uid] = abs(_sim_dirs[uid])
        readings.append(
            ModbusSensorReading(
                unit_id=uid,
                sensor_id=f"mb-{uid:02d}",
                name=f"Modbus {uid}",
                bus="modbus",
                temperature=round(_sim_temps[uid], 2),
                error=False,
            )
        )
    return readings


# ── Real hardware ─────────────────────────────────────────────────────────────
_client = None


def _get_client():
    """Return (and lazily create) the shared Modbus RTU client."""
    global _client
    if _client is not None:
        return _client
    try:
        from pymodbus.client import ModbusSerialClient  # type: ignore
        _client = ModbusSerialClient(
            port=PORT,
            baudrate=BAUD,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=TIMEOUT,
        )
        if not _client.connect():
            log.error("Modbus: could not open %s", PORT)
            _client = None
        else:
            log.info("Modbus RTU connected on %s @ %d baud", PORT, BAUD)
    except Exception as exc:
        log.error("Modbus init failed: %s", exc)
        _client = None
    return _client


def _read_unit(uid: int, client) -> float | None:
    """Read one signed 16-bit holding register from a unit. Returns °C or None."""
    try:
        rr = client.read_holding_registers(TEMP_REGISTER, count=1, slave=uid)
        if rr.isError():
            return None
        raw = rr.registers[0]
        # Interpret as signed 16-bit (two's complement)
        if raw > 0x7FFF:
            raw -= 0x10000
        return round(raw * TEMP_SCALE, 2)
    except Exception as exc:
        log.debug("Modbus unit %d read error: %s", uid, exc)
        return None


def read_all() -> List[ModbusSensorReading]:
    """Return readings for every configured Modbus unit."""
    if not ENABLED:
        return []
    if SIMULATE:
        return _simulate()

    client = _get_client()
    readings: List[ModbusSensorReading] = []

    for uid in UNIT_IDS:
        if client:
            temp = _read_unit(uid, client)
        else:
            temp = None

        readings.append(
            ModbusSensorReading(
                unit_id=uid,
                sensor_id=f"mb-{uid:02d}",
                name=f"Modbus {uid}",
                bus="modbus",
                temperature=temp if temp is not None else float("nan"),
                error=temp is None,
            )
        )

    return readings

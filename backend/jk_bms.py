"""
JK BMS RS485 Modbus reader.

Reads pack voltage, current, SOC, cell voltages, and temperatures from
JK BMS via RS485/Modbus RTU protocol.

Falls back to simulation when SIMULATE=true or JK_BMS_ENABLED=false.
"""
from __future__ import annotations

import logging
import os
import random
import time
from dataclasses import dataclass
from typing import List, Optional

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
SIMULATE       = os.getenv("SIMULATE", "false").lower() == "true"
ENABLED        = os.getenv("JK_BMS_ENABLED", "false").lower() == "true"
PORT           = os.getenv("JK_BMS_PORT", "/dev/serial0")
BAUD           = int(os.getenv("JK_BMS_BAUD", "115200"))
UNIT_ID        = int(os.getenv("JK_BMS_UNIT_ID", "1"))
TIMEOUT        = float(os.getenv("JK_BMS_TIMEOUT", "1.0"))
NUM_CELLS      = int(os.getenv("JK_BMS_NUM_CELLS", "16"))
BAUD_CANDIDATES_RAW = os.getenv("JK_BMS_BAUD_CANDIDATES", f"{BAUD},9600,19200,38400,115200")
UNIT_CANDIDATES_RAW = os.getenv("JK_BMS_UNIT_CANDIDATES", f"{UNIT_ID},1,2,3,4")

# JK BMS common register map (may vary by model)
REG_PACK_VOLTAGE = 0x70      # 0.01V per unit
REG_PACK_CURRENT = 0x71      # 0.01A per unit (signed)
REG_SOC          = 0x72      # 0.01% per unit
REG_CELL_START   = 0x73      # Cell voltages, 0.001V per unit
REG_TEMP_START   = 0x80      # Temperatures, 0.1°C per unit


@dataclass
class BMSReading:
    pack_voltage: float       # V
    pack_current: float       # A (negative = discharge)
    soc: float                # %
    cell_voltages: List[float]  # V
    temperatures: List[float]   # °C
    error: bool = False
    error_message: str | None = None
    timestamp: float = 0.0


# ── Simulated state ───────────────────────────────────────────────────────────
_sim_soc = 75.0
_sim_current = -5.0  # discharging
_sim_temps = [25.0 + random.uniform(-2, 2) for _ in range(4)]
_sim_cells = [3.3 + random.uniform(-0.05, 0.05) for _ in range(NUM_CELLS)]


def _simulate() -> BMSReading:
    """Return simulated BMS data with slow drift."""
    global _sim_soc, _sim_current, _sim_temps, _sim_cells
    
    # Drift current slightly
    _sim_current += random.uniform(-0.3, 0.3)
    _sim_current = max(-50, min(50, _sim_current))
    
    # Update SOC based on current (very rough simulation)
    if _sim_current < 0:  # discharging
        _sim_soc -= 0.02
    else:  # charging
        _sim_soc += 0.05
    _sim_soc = max(0, min(100, _sim_soc))
    
    # Drift temps
    for i in range(len(_sim_temps)):
        _sim_temps[i] += random.uniform(-0.1, 0.1)
        _sim_temps[i] = max(15, min(45, _sim_temps[i]))
    
    # Drift cells slightly
    for i in range(len(_sim_cells)):
        _sim_cells[i] += random.uniform(-0.002, 0.002)
        _sim_cells[i] = max(2.5, min(4.2, _sim_cells[i]))
    
    pack_voltage = sum(_sim_cells)
    
    return BMSReading(
        pack_voltage=round(pack_voltage, 2),
        pack_current=round(_sim_current, 2),
        soc=round(_sim_soc, 1),
        cell_voltages=[round(v, 3) for v in _sim_cells],
        temperatures=[round(t, 1) for t in _sim_temps],
        timestamp=time.time(),
    )


# ── Real hardware ─────────────────────────────────────────────────────────────
_client = None
_disabled_due_to_error = False
_active_baud = BAUD
_active_unit_id = UNIT_ID
_last_error: str | None = None


def _parse_int_list(raw: str) -> list[int]:
    values: list[int] = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            value = int(item)
            if value not in values:
                values.append(value)
        except ValueError:
            continue
    return values


def _is_plausible_pack(pack_regs: list[int]) -> bool:
    if len(pack_regs) < 3:
        return False
    pack_voltage = pack_regs[0] * 0.01
    soc = pack_regs[2] * 0.01
    return 1.0 <= pack_voltage <= 120.0 and 0.0 <= soc <= 100.0


def _get_client():
    """Return (and lazily create) the shared Modbus RTU client for JK BMS."""
    global _client, _disabled_due_to_error, _active_baud, _active_unit_id, _last_error
    if _client is not None:
        return _client
    if _disabled_due_to_error:
        return None

    baud_candidates = _parse_int_list(BAUD_CANDIDATES_RAW)
    unit_candidates = _parse_int_list(UNIT_CANDIDATES_RAW)
    if not baud_candidates:
        baud_candidates = [BAUD]
    if not unit_candidates:
        unit_candidates = [UNIT_ID]

    try:
        from pymodbus.client import ModbusSerialClient  # type: ignore
        for baud in baud_candidates:
            candidate = ModbusSerialClient(
                port=PORT,
                baudrate=baud,
                bytesize=8,
                parity="N",
                stopbits=1,
                timeout=TIMEOUT,
            )
            if not candidate.connect():
                continue

            matched = False
            for unit in unit_candidates:
                try:
                    rr = candidate.read_holding_registers(REG_PACK_VOLTAGE, count=3, slave=unit)
                    if rr.isError():
                        continue
                    if not _is_plausible_pack(rr.registers):
                        continue
                    _client = candidate
                    _active_baud = baud
                    _active_unit_id = unit
                    _last_error = None
                    matched = True
                    log.info(
                        "JK BMS connected on %s @ %d baud (unit %d)",
                        PORT,
                        _active_baud,
                        _active_unit_id,
                    )
                    break
                except Exception:
                    continue

            if matched:
                break

            candidate.close()

        if _client is None:
            _last_error = (
                "No valid Modbus response from JK BMS. Check JK_BMS_BAUD/UNIT_ID, "
                "A/B wiring, and that your BMS model uses Modbus RTU on RS485."
            )
            log.error("JK BMS read probe failed on %s (%s)", PORT, _last_error)
            _disabled_due_to_error = True
    except Exception as exc:
        log.error("JK BMS init failed: %s", exc)
        _last_error = str(exc)
        _disabled_due_to_error = True
        _client = None
    return _client


def _read_registers(client, start: int, count: int) -> Optional[List[int]]:
    """Read holding registers, return list or None on error."""
    global _last_error
    try:
        rr = client.read_holding_registers(start, count=count, slave=_active_unit_id)
        if rr.isError():
            _last_error = f"Modbus error reading register 0x{start:04X}"
            return None
        return rr.registers
    except Exception as exc:
        _last_error = str(exc)
        log.debug("JK BMS register read error at 0x%X: %s", start, exc)
        return None


def read() -> Optional[BMSReading]:
    """Return current BMS reading, or None if disabled/error."""
    if not ENABLED:
        return None
    if SIMULATE:
        return _simulate()

    client = _get_client()
    if not client:
        return BMSReading(
            pack_voltage=0.0,
            pack_current=0.0,
            soc=0.0,
            cell_voltages=[],
            temperatures=[],
            error=True,
            error_message=_last_error or "JK BMS connection failed",
            timestamp=time.time(),
        )

    # Read pack-level data
    pack_regs = _read_registers(client, REG_PACK_VOLTAGE, 3)
    if pack_regs is None:
        return BMSReading(
            pack_voltage=0.0,
            pack_current=0.0,
            soc=0.0,
            cell_voltages=[],
            temperatures=[],
            error=True,
            error_message=_last_error or "JK BMS pack registers not readable",
            timestamp=time.time(),
        )

    pack_voltage = pack_regs[0] * 0.01
    pack_current_raw = pack_regs[1]
    if pack_current_raw > 0x7FFF:
        pack_current_raw -= 0x10000  # signed 16-bit
    pack_current = pack_current_raw * 0.01
    soc = pack_regs[2] * 0.01

    # Read cell voltages
    cell_regs = _read_registers(client, REG_CELL_START, NUM_CELLS)
    cell_voltages = []
    if cell_regs:
        for v in cell_regs:
            cell_voltages.append(v * 0.001)

    # Read temperatures (assuming 4 temp sensors)
    temp_regs = _read_registers(client, REG_TEMP_START, 4)
    temperatures = []
    if temp_regs:
        for t in temp_regs:
            if t > 0x7FFF:
                t -= 0x10000  # signed
            temperatures.append(t * 0.1)

    return BMSReading(
        pack_voltage=round(pack_voltage, 2),
        pack_current=round(pack_current, 2),
        soc=round(soc, 1),
        cell_voltages=[round(v, 3) for v in cell_voltages],
        temperatures=[round(t, 1) for t in temperatures],
        error=False,
        error_message=None,
        timestamp=time.time(),
    )

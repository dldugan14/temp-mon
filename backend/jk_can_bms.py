"""
JK BMS CAN telemetry decoder.

Listens on SocketCAN for JK BMS telemetry frames and maps them into the
same BMSReading model used by the UI.

Default frame mapping (configurable via env):
- Pack frame (JK_BMS_CAN_PACK_ID, default 0x351):
    bytes 0-1: pack voltage raw (uint16, big-endian)  * JK_BMS_CAN_VOLTAGE_SCALE
    bytes 2-3: pack current raw (int16/uint16)        * JK_BMS_CAN_CURRENT_SCALE
    byte 4   : SOC raw (uint8)                        * JK_BMS_CAN_SOC_SCALE
- Temp frame (JK_BMS_CAN_TEMP_ID, default 0x355):
    bytes 0..3: temperatures with JK_BMS_CAN_TEMP_OFFSET applied
- Cell frames (JK_BMS_CAN_CELL_BASE_ID..+N-1, default 0x360..0x363):
    each frame contains up to 4 cell voltages (uint16 big-endian) scaled by
    JK_BMS_CAN_CELL_SCALE.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field

from can_commander import CanStatus
from jk_bms import BMSReading

log = logging.getLogger(__name__)

ENABLED = os.getenv("JK_BMS_CAN_ENABLED", "true").lower() == "true"
INTERFACE = os.getenv("CAN_INTERFACE", "can0")
NO_FRAME_TIMEOUT = float(os.getenv("JK_BMS_CAN_NO_FRAME_TIMEOUT", "10.0"))

PACK_ID = int(os.getenv("JK_BMS_CAN_PACK_ID", "0x351"), 0)
TEMP_ID = int(os.getenv("JK_BMS_CAN_TEMP_ID", "0x355"), 0)
CELL_BASE_ID = int(os.getenv("JK_BMS_CAN_CELL_BASE_ID", "0x360"), 0)
CELL_FRAME_COUNT = int(os.getenv("JK_BMS_CAN_CELL_FRAME_COUNT", "4"))

VOLTAGE_SCALE = float(os.getenv("JK_BMS_CAN_VOLTAGE_SCALE", "0.1"))
CURRENT_SCALE = float(os.getenv("JK_BMS_CAN_CURRENT_SCALE", "0.1"))
SOC_SCALE = float(os.getenv("JK_BMS_CAN_SOC_SCALE", "1.0"))
CELL_SCALE = float(os.getenv("JK_BMS_CAN_CELL_SCALE", "0.001"))

CURRENT_SIGNED = os.getenv("JK_BMS_CAN_CURRENT_SIGNED", "true").lower() == "true"
CURRENT_OFFSET = int(os.getenv("JK_BMS_CAN_CURRENT_OFFSET", "0"))
TEMP_OFFSET = float(os.getenv("JK_BMS_CAN_TEMP_OFFSET", "-40"))


@dataclass
class _CanTelemetry:
    pack_voltage: float | None = None
    pack_current: float | None = None
    soc: float | None = None
    temperatures: list[float] = field(default_factory=list)
    cells: dict[int, float] = field(default_factory=dict)
    frames_seen: int = 0
    last_frame_at: float | None = None
    error_message: str | None = "Waiting for JK BMS CAN frames..."


_state = _CanTelemetry()


def _interface_exists(name: str) -> bool:
    return os.path.exists(f"/sys/class/net/{name}")


def _u16be(data: bytes, idx: int) -> int:
    return (data[idx] << 8) | data[idx + 1]


def _s16be(data: bytes, idx: int) -> int:
    value = _u16be(data, idx)
    return value - 0x10000 if value > 0x7FFF else value


def _decode_pack(data: bytes) -> None:
    if len(data) < 5:
        return
    _state.pack_voltage = round(_u16be(data, 0) * VOLTAGE_SCALE, 2)

    if CURRENT_SIGNED:
        current_raw = _s16be(data, 2)
    else:
        current_raw = _u16be(data, 2) - CURRENT_OFFSET
    _state.pack_current = round(current_raw * CURRENT_SCALE, 2)

    _state.soc = round(data[4] * SOC_SCALE, 1)


def _decode_temps(data: bytes) -> None:
    temps: list[float] = []
    for byte in data[:4]:
        temps.append(round(byte + TEMP_OFFSET, 1))
    _state.temperatures = temps


def _decode_cells(arbitration_id: int, data: bytes) -> None:
    frame_index = arbitration_id - CELL_BASE_ID
    if frame_index < 0 or frame_index >= CELL_FRAME_COUNT:
        return

    base_cell_index = frame_index * 4
    for i in range(0, min(len(data), 8), 2):
        if i + 1 >= len(data):
            break
        cell_number = base_cell_index + (i // 2) + 1
        raw = _u16be(data, i)
        if raw == 0:
            continue
        _state.cells[cell_number] = round(raw * CELL_SCALE, 3)


def _decode_frame(arbitration_id: int, data: bytes) -> None:
    _state.frames_seen += 1
    _state.last_frame_at = time.time()

    if arbitration_id == PACK_ID:
        _decode_pack(data)
    elif arbitration_id == TEMP_ID:
        _decode_temps(data)
    elif CELL_BASE_ID <= arbitration_id < CELL_BASE_ID + CELL_FRAME_COUNT:
        _decode_cells(arbitration_id, data)

    has_pack = _state.pack_voltage is not None and _state.pack_current is not None and _state.soc is not None
    if has_pack:
        _state.error_message = None
    else:
        _state.error_message = (
            f"CAN frames received ({_state.frames_seen}) but no pack decode yet. "
            "Check JK_BMS_CAN_* frame IDs/scales for your BMS protocol."
        )


def get_latest() -> BMSReading | None:
    if not ENABLED:
        return None

    now = time.time()
    if _state.last_frame_at is None:
        return BMSReading(
            pack_voltage=0.0,
            pack_current=0.0,
            soc=0.0,
            cell_voltages=[],
            temperatures=[],
            error=True,
            error_message=_state.error_message,
            timestamp=now,
        )

    if now - _state.last_frame_at > NO_FRAME_TIMEOUT:
        return BMSReading(
            pack_voltage=0.0,
            pack_current=0.0,
            soc=0.0,
            cell_voltages=[],
            temperatures=[],
            error=True,
            error_message=f"No JK BMS CAN frames for {int(now - _state.last_frame_at)}s",
            timestamp=now,
        )

    if _state.pack_voltage is None or _state.pack_current is None or _state.soc is None:
        return BMSReading(
            pack_voltage=0.0,
            pack_current=0.0,
            soc=0.0,
            cell_voltages=[],
            temperatures=[],
            error=True,
            error_message=_state.error_message,
            timestamp=now,
        )

    cell_voltages = [_state.cells[k] for k in sorted(_state.cells.keys())]
    return BMSReading(
        pack_voltage=_state.pack_voltage,
        pack_current=_state.pack_current,
        soc=_state.soc,
        cell_voltages=cell_voltages,
        temperatures=list(_state.temperatures),
        error=False,
        error_message=None,
        timestamp=now,
    )


async def run(can_status: CanStatus) -> None:
    if not ENABLED:
        log.info("JK CAN BMS decoder disabled")
        return

    try:
        import can  # type: ignore
    except ImportError:
        _state.error_message = "python-can not installed"
        log.error("JK CAN BMS: python-can not installed")
        return

    while True:
        if not can_status.enabled:
            _state.error_message = "CAN disabled"
            await asyncio.sleep(1)
            continue

        if not _interface_exists(INTERFACE):
            _state.error_message = f"CAN interface '{INTERFACE}' not found"
            await asyncio.sleep(1)
            continue

        try:
            bus = can.Bus(channel=INTERFACE, interface="socketcan")
            log.info("JK CAN BMS decoder listening on %s", INTERFACE)

            try:
                while can_status.enabled:
                    try:
                        msg = await asyncio.to_thread(bus.recv, 1.0)
                    except asyncio.CancelledError:
                        return
                    if msg is None:
                        continue
                    _decode_frame(msg.arbitration_id, bytes(msg.data))
            finally:
                bus.shutdown()
        except asyncio.CancelledError:
            return
        except Exception as exc:
            _state.error_message = f"JK CAN BMS error: {exc}"
            log.error(_state.error_message)
            await asyncio.sleep(2)

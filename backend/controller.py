"""
Temp-Mon background control loop.

Reads all sensors (1-Wire DS18B20 + RS485 Modbus) every POLL_INTERVAL
seconds, evaluates thresholds, and actuates the fan / battery relays.

CAN bus relay commands are handled in a parallel async task.
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List

from sensors import SensorReading, read_all as read_1wire
from modbus_sensors import read_all as read_modbus, ModbusSensorReading
from relay import Relay, cleanup_all
import can_commander
from can_commander import CanStatus

# ── Feature flags (initial values from env; can be toggled at runtime) ────────────
CAN_ENABLED = os.getenv("CAN_ENABLED", "true").lower() == "true"

log = logging.getLogger(__name__)

# ── Config from env ────────────────────────────────────────────────────────────
FAN_ON_TEMP  = float(os.getenv("FAN_ON_TEMP",  "30.0"))
FAN_OFF_TEMP = float(os.getenv("FAN_OFF_TEMP", "25.0"))
BAT_ON_TEMP  = float(os.getenv("BAT_ON_TEMP",  "40.0"))
BAT_OFF_TEMP = float(os.getenv("BAT_OFF_TEMP", "35.0"))
FAN_PIN      = int(os.getenv("FAN_RELAY_PIN",  "17"))
BAT_PIN      = int(os.getenv("BAT_RELAY_PIN",  "27"))
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "5"))


@dataclass
class RelayStatus:
    name: str
    pin: int
    state: bool
    is_overridden: bool


@dataclass
class SystemState:
    sensors: List[Dict[str, Any]]
    relays: Dict[str, RelayStatus]
    timestamp: float
    fan_on_temp: float
    fan_off_temp: float
    bat_on_temp: float
    bat_off_temp: float


class Controller:
    def __init__(self) -> None:
        self.fan_relay = Relay("fan", FAN_PIN)
        self.bat_relay = Relay("battery", BAT_PIN)
        self.can_status = CanStatus()
        self._last_state: SystemState | None = None
        self._listeners: list[asyncio.Queue] = []

    # ── Subscriber pattern for SSE ─────────────────────────────────────────────

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=10)
        self._listeners.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        try:
            self._listeners.remove(q)
        except ValueError:
            pass

    def _broadcast(self, state: SystemState) -> None:
        dead = []
        for q in self._listeners:
            try:
                q.put_nowait(self._serialise(state))
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self._listeners.remove(q)

    # ── Serialisation ──────────────────────────────────────────────────────────

    def _serialise(self, state: SystemState) -> Dict[str, Any]:
        sensors = []
        for s in state.sensors:
            temp = s["temperature"]
            sensors.append({
                **s,
                "temperature": None if (temp is None or (isinstance(temp, float) and math.isnan(temp))) else temp,
            })
        return {
            "sensors": sensors,
            "relays": {
                k: {"name": v.name, "pin": v.pin, "state": v.state, "is_overridden": v.is_overridden}
                for k, v in state.relays.items()
            },
            "timestamp": state.timestamp,
            "config": {
                "fan_on_temp":   state.fan_on_temp,
                "fan_off_temp":  state.fan_off_temp,
                "bat_on_temp":   state.bat_on_temp,
                "bat_off_temp":  state.bat_off_temp,
                "poll_interval": POLL_INTERVAL,
            },
            "can": self.can_status.to_dict(),
        }

    # ── Sensor merging + control logic ────────────────────────────────────────

    @staticmethod
    def _merge_sensors(
        onewire: List[SensorReading],
        modbus: List[ModbusSensorReading],
    ) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        idx = 0
        for r in list(onewire) + list(modbus):  # type: ignore[operator]
            result.append({
                "index":       idx,
                "sensor_id":   r.sensor_id,
                "name":        r.name,
                "bus":         r.bus,
                "temperature": r.temperature,
                "error":       r.error,
            })
            idx += 1
        return result

    @staticmethod
    def _valid_temps(sensor_dicts: List[Dict[str, Any]]) -> List[float]:
        return [
            s["temperature"] for s in sensor_dicts
            if not s["error"]
            and s["temperature"] is not None
            and not math.isnan(s["temperature"])
        ]

    def _evaluate(self, sensor_dicts: List[Dict[str, Any]]) -> None:
        temps = self._valid_temps(sensor_dicts)
        if not temps:
            return
        max_temp = max(temps)
        if max_temp >= FAN_ON_TEMP:
            self.fan_relay.set_auto(True)
        elif max_temp <= FAN_OFF_TEMP:
            self.fan_relay.set_auto(False)
        if max_temp >= BAT_ON_TEMP:
            self.bat_relay.set_auto(True)
        elif max_temp <= BAT_OFF_TEMP:
            self.bat_relay.set_auto(False)

    def _build_state(self, sensor_dicts: List[Dict[str, Any]]) -> SystemState:
        return SystemState(
            sensors=sensor_dicts,
            relays={
                "fan":     RelayStatus("fan",     FAN_PIN, self.fan_relay.state, self.fan_relay.is_overridden),
                "battery": RelayStatus("battery", BAT_PIN, self.bat_relay.state, self.bat_relay.is_overridden),
            },
            timestamp=time.time(),
            fan_on_temp=FAN_ON_TEMP,
            fan_off_temp=FAN_OFF_TEMP,
            bat_on_temp=BAT_ON_TEMP,
            bat_off_temp=BAT_OFF_TEMP,
        )

    def set_can_enabled(self, enabled: bool) -> None:
        """Toggle the CAN commander on or off at runtime."""
        self.can_status.enabled = enabled
        log.info("CAN commander %s at runtime", "enabled" if enabled else "disabled")
        self._refresh_state(force_broadcast=True)

    def can_relay_callback(self, relay_name: str, action: str) -> None:
        """Called by the CAN listener when a valid relay command frame arrives."""
        target = self.fan_relay if relay_name == "fan" else self.bat_relay
        if action == "on":
            target.set_override(True)
        elif action == "off":
            target.set_override(False)
        elif action == "auto":
            target.clear_override()
        if self._last_state:
            state = self._build_state(self._last_state.sensors)
            self._last_state = state
            self._broadcast(state)

    # ── Public helpers for REST ────────────────────────────────────────────────

    def get_current(self) -> Dict[str, Any] | None:
        if self._last_state:
            return self._serialise(self._last_state)
        return None

    def override_relay(self, name: str, state: bool) -> bool:
        relay = {"fan": self.fan_relay, "battery": self.bat_relay}.get(name)
        if relay is None:
            return False
        relay.set_override(state)
        self._refresh_state(force_broadcast=True)
        return True

    def clear_relay_override(self, name: str) -> bool:
        relay = {"fan": self.fan_relay, "battery": self.bat_relay}.get(name)
        if relay is None:
            return False
        relay.clear_override()
        self._refresh_state(force_broadcast=True)
        return True

    def _refresh_state(self, sensor_dicts: List[Dict[str, Any]] | None = None, force_broadcast: bool = False) -> None:
        if sensor_dicts is None and self._last_state:
            sensor_dicts = self._last_state.sensors
        if sensor_dicts:
            state = self._build_state(sensor_dicts)
            self._last_state = state
            if force_broadcast:
                self._broadcast(state)

    # ── Main sensor-polling loop ──────────────────────────────────────────────

    async def run(self) -> None:
        log.info("Controller started – poll every %ss", POLL_INTERVAL)

        # Start CAN commander – it loops forever and respects can_status.enabled at runtime
        asyncio.create_task(
            can_commander.run(self.can_status, self.can_relay_callback),
            name="can-commander",
        )

        try:
            while True:
                try:
                    onewire = read_1wire()
                    modbus  = read_modbus()
                    sensor_dicts = self._merge_sensors(onewire, modbus)
                    self._evaluate(sensor_dicts)
                    state = self._build_state(sensor_dicts)
                    self._last_state = state
                    self._broadcast(state)
                except Exception as exc:
                    log.error("Controller loop error: %s", exc)
                await asyncio.sleep(POLL_INTERVAL)
        finally:
            cleanup_all([self.fan_relay, self.bat_relay])
            log.info("Controller stopped, relays off")

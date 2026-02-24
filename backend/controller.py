"""
Background control loop.
Reads all sensors every POLL_INTERVAL seconds, evaluates thresholds, and
actuates the fan / battery relays accordingly.
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, List

from sensors import SensorReading, read_all
from relay import Relay, cleanup_all

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

    @staticmethod
    def _serialise(state: SystemState) -> Dict[str, Any]:
        sensors = []
        for s in state.sensors:
            temp = s["temperature"]
            sensors.append({**s, "temperature": None if (temp is None or (isinstance(temp, float) and math.isnan(temp))) else temp})
        return {
            "sensors": sensors,
            "relays": {
                k: {"name": v.name, "pin": v.pin, "state": v.state, "is_overridden": v.is_overridden}
                for k, v in state.relays.items()
            },
            "timestamp": state.timestamp,
            "config": {
                "fan_on_temp":  state.fan_on_temp,
                "fan_off_temp": state.fan_off_temp,
                "bat_on_temp":  state.bat_on_temp,
                "bat_off_temp": state.bat_off_temp,
                "poll_interval": POLL_INTERVAL,
            },
        }

    # ── Control logic ──────────────────────────────────────────────────────────

    @staticmethod
    def _valid_temps(readings: List[SensorReading]) -> List[float]:
        return [r.temperature for r in readings if not r.error and not math.isnan(r.temperature)]

    def _evaluate(self, readings: List[SensorReading]) -> None:
        temps = self._valid_temps(readings)
        if not temps:
            return

        max_temp = max(temps)
        min_temp = min(temps)

        # Hysteretic control
        if max_temp >= FAN_ON_TEMP:
            self.fan_relay.set_auto(True)
        elif max_temp <= FAN_OFF_TEMP:
            self.fan_relay.set_auto(False)

        if max_temp >= BAT_ON_TEMP:
            self.bat_relay.set_auto(True)
        elif max_temp <= BAT_OFF_TEMP:
            self.bat_relay.set_auto(False)

    def _build_state(self, readings: List[SensorReading]) -> SystemState:
        sensor_dicts = [
            {
                "index": r.index,
                "sensor_id": r.sensor_id,
                "name": r.name,
                "temperature": r.temperature,
                "error": r.error,
            }
            for r in readings
        ]
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

    def _refresh_state(self, readings: List[SensorReading] | None = None, force_broadcast: bool = False) -> None:
        if readings is None and self._last_state:
            # Re-use last sensor data, just refresh relay status
            last_sensors = [
                SensorReading(
                    index=s["index"], sensor_id=s["sensor_id"],
                    name=s["name"], temperature=s["temperature"] or float("nan"),
                    error=s["error"],
                )
                for s in self._last_state.sensors
            ]
            readings = last_sensors
        if readings:
            state = self._build_state(readings)
            self._last_state = state
            if force_broadcast:
                self._broadcast(state)

    # ── Main loop ──────────────────────────────────────────────────────────────

    async def run(self) -> None:
        log.info("Controller started – poll every %ss", POLL_INTERVAL)
        try:
            while True:
                try:
                    readings = read_all()
                    self._evaluate(readings)
                    state = self._build_state(readings)
                    self._last_state = state
                    self._broadcast(state)
                except Exception as exc:
                    log.error("Controller loop error: %s", exc)
                await asyncio.sleep(POLL_INTERVAL)
        finally:
            cleanup_all([self.fan_relay, self.bat_relay])
            log.info("Controller stopped, relays off")

"""
DS18B20 1-Wire temperature sensor reader.
Falls back to simulation when SIMULATE=true or hardware is absent.
"""
from __future__ import annotations

import glob
import math
import os
import random
import time
from dataclasses import dataclass, field
from typing import List

SIMULATE = os.getenv("SIMULATE", "false").lower() == "true"
W1_BASE = "/sys/bus/w1/devices"
NUM_SENSORS = 8

# Simulated state – drifts slowly so the UI looks alive
_sim_temps: list[float] = [22.0 + random.uniform(-2, 2) for _ in range(NUM_SENSORS)]
_sim_direction: list[float] = [random.choice([-1, 1]) * 0.1 for _ in range(NUM_SENSORS)]


@dataclass
class SensorReading:
    index: int          # 0-based (across all sensors combined)
    sensor_id: str      # e.g. "28-0000089abcd1"
    name: str           # "Sensor 1" .. "Sensor 8"
    temperature: float  # °C
    error: bool = False
    bus: str = "1wire"  # "1wire" | "modbus"


def _discover_devices() -> List[str]:
    """Return list of DS18B20 device paths, sorted."""
    return sorted(glob.glob(os.path.join(W1_BASE, "28-*")))


def _read_device(dev_path: str) -> float | None:
    """Parse /w1_slave and return temperature in °C, or None on error."""
    slave = os.path.join(dev_path, "w1_slave")
    try:
        with open(slave) as f:
            lines = f.readlines()
        if len(lines) < 2 or "YES" not in lines[0]:
            return None
        t_pos = lines[1].find("t=")
        if t_pos == -1:
            return None
        return int(lines[1][t_pos + 2:]) / 1000.0
    except OSError:
        return None


def _simulate() -> List[SensorReading]:
    """Return slowly-drifting simulated readings."""
    global _sim_temps, _sim_direction
    readings: List[SensorReading] = []
    for i in range(NUM_SENSORS):
        _sim_temps[i] += _sim_direction[i] + random.uniform(-0.05, 0.05)
        # Bounce between 15 °C and 55 °C
        if _sim_temps[i] > 55:
            _sim_direction[i] = -abs(_sim_direction[i])
        elif _sim_temps[i] < 15:
            _sim_direction[i] = abs(_sim_direction[i])
        readings.append(
            SensorReading(
                index=i,
                sensor_id=f"28-sim{i:012x}",
                name=f"Sensor {i + 1}",
                temperature=round(_sim_temps[i], 2),
                bus="1wire",
            )
        )
    return readings


def read_all() -> List[SensorReading]:
    """Return readings for all 8 sensors (padded with errors if fewer found)."""
    if SIMULATE:
        return _simulate()

    devices = _discover_devices()
    readings: List[SensorReading] = []

    for i in range(NUM_SENSORS):
        if i < len(devices):
            dev = devices[i]
            sensor_id = os.path.basename(dev)
            temp = _read_device(dev)
            if temp is not None:
                readings.append(
                    SensorReading(
                        index=i,
                        sensor_id=sensor_id,
                        name=f"Sensor {i + 1}",
                        temperature=round(temp, 2),
                        bus="1wire",
                    )
                )
            else:
                readings.append(
                    SensorReading(index=i, sensor_id=sensor_id, name=f"Sensor {i + 1}",
                                  temperature=float("nan"), error=True, bus="1wire")
                )
        else:
            readings.append(
                SensorReading(index=i, sensor_id=f"28-missing{i}", name=f"Sensor {i + 1}",
                              temperature=float("nan"), error=True, bus="1wire")
            )

    return readings

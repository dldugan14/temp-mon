"""
GPIO relay controller.
Falls back to a software-only simulation on non-Pi hardware or when SIMULATE=true.
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

SIMULATE = os.getenv("SIMULATE", "false").lower() == "true"
ACTIVE_HIGH = True  # GPIO HIGH = relay energised

# GPIO will only be imported on real hardware
_gpio = None

def _init_gpio():
    global _gpio
    if _gpio is not None:
        return
    try:
        import RPi.GPIO as GPIO  # type: ignore
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        _gpio = GPIO
        log.info("RPi.GPIO initialised (BCM mode)")
    except Exception as exc:
        log.warning("RPi.GPIO unavailable – relay in simulation mode: %s", exc)
        _gpio = None


class Relay:
    """Represents a single relay output."""

    def __init__(self, name: str, pin: int):
        self.name = name
        self.pin = pin
        self._state: bool = False      # True = ON
        self._override: bool | None = None  # None = auto

        if not SIMULATE:
            _init_gpio()
            if _gpio:
                _gpio.setup(pin, _gpio.OUT, initial=(_gpio.HIGH if ACTIVE_HIGH else _gpio.LOW)
                            if False else (_gpio.LOW if ACTIVE_HIGH else _gpio.HIGH))

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _apply(self, state: bool) -> None:
        self._state = state
        if _gpio and not SIMULATE:
            level = _gpio.HIGH if (state == ACTIVE_HIGH) else _gpio.LOW
            _gpio.output(self.pin, level)
        log.debug("Relay %s → %s (pin %d)", self.name, "ON" if state else "OFF", self.pin)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def set_auto(self, desired: bool) -> None:
        """Called by the controller; has no effect if manually overridden."""
        if self._override is None:
            self._apply(desired)

    def set_override(self, state: bool) -> None:
        """Manually force the relay state."""
        self._override = state
        self._apply(state)

    def clear_override(self) -> None:
        """Return to automatic control."""
        self._override = None

    @property
    def state(self) -> bool:
        return self._state

    @property
    def is_overridden(self) -> bool:
        return self._override is not None

    def cleanup(self) -> None:
        self._apply(False)


def cleanup_all(relays: list[Relay]) -> None:
    """Turn off all relays and release GPIO."""
    for r in relays:
        r.cleanup()
    if _gpio and not SIMULATE:
        try:
            _gpio.cleanup()
        except Exception:
            pass

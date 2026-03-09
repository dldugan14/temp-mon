"""
CAN bus relay commander.

Listens on a SocketCAN interface (MCP2515 → can0) for relay control frames
and dispatches them to the controller's relay objects.

Frame format (arbitration ID = CAN_RELAY_CMD_ID):
  byte[0]  relay selector   0 = fan   1 = battery
  byte[1]  command          0 = force OFF
                            1 = force ON
                            2 = return to AUTO (clear override)

All other frames are silently ignored.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
ENABLED       = os.getenv("CAN_ENABLED", "false").lower() == "true"
INTERFACE     = os.getenv("CAN_INTERFACE", "can0")
BITRATE       = int(os.getenv("CAN_BITRATE", "500000"))
CMD_ID_RAW    = os.getenv("CAN_RELAY_CMD_ID", "0x100")
CMD_ID        = int(CMD_ID_RAW, 0)   # int(s, 0) handles "0x100" and "256" both
SIMULATE      = os.getenv("SIMULATE", "false").lower() == "true"

RELAY_MAP     = {0: "fan", 1: "battery"}
COMMAND_MAP   = {0: "off", 1: "on", 2: "auto"}


def _is_no_such_device(exc: Exception) -> bool:
    text = str(exc).lower()
    return "no such device" in text or "errno 19" in text


def _interface_exists(name: str) -> bool:
    return os.path.exists(f"/sys/class/net/{name}")


class CanStatus:
    """Mutable status object shared with the controller for UI reporting."""

    def __init__(self) -> None:
        self.enabled: bool = ENABLED
        self.interface: str = INTERFACE
        self.last_cmd_at: float | None = None
        self.last_cmd_relay: str | None = None
        self.last_cmd_action: str | None = None
        self.error: str | None = None
        self.frame_count: int = 0

    def record_command(self, relay: str, action: str) -> None:
        self.last_cmd_at = time.time()
        self.last_cmd_relay = relay
        self.last_cmd_action = action
        self.frame_count += 1
        self.error = None

    def record_error(self, msg: str) -> None:
        self.error = msg

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "interface": self.interface,
            "last_cmd_at": self.last_cmd_at,
            "last_cmd_relay": self.last_cmd_relay,
            "last_cmd_action": self.last_cmd_action,
            "error": self.error,
            "frame_count": self.frame_count,
        }


async def run(status: CanStatus, relay_callback) -> None:
    """
    Async task that loops forever, respecting status.enabled at runtime.
    relay_callback("fan" | "battery", "on" | "off" | "auto")

    When status.enabled is False the loop idles (1 s sleep) so that setting
    it back to True re-activates the bus without restarting the process.
    """
    if SIMULATE:
        log.info("CAN commander in simulation mode – no real CAN bus")
        status.error = "simulation mode"
        # Keep looping so runtime enable/disable changes are reflected in status
        while True:
            await asyncio.sleep(5)

    try:
        import can  # type: ignore
    except ImportError:
        msg = "python-can not installed – CAN commander inactive"
        log.error(msg)
        status.record_error(msg)
        return   # No point looping without the library

    while True:
        if not status.enabled:
            await asyncio.sleep(1)
            continue

        if not _interface_exists(INTERFACE):
            status.enabled = False
            status.record_error(
                f"CAN disabled: interface '{INTERFACE}' not found. "
                "Enable CAN hardware or set CAN_ENABLED=false."
            )
            log.warning("CAN interface %s not found - disabling CAN runtime", INTERFACE)
            await asyncio.sleep(1)
            continue

        # Bring up the CAN interface if not already up
        await _ensure_interface_up(status)

        try:
            bus = can.Bus(channel=INTERFACE, interface="socketcan")
            log.info("CAN commander listening on %s (ID 0x%X)", INTERFACE, CMD_ID)
            status.error = None

            reader = can.AsyncBufferedReader()
            notifier = can.Notifier(bus, [reader], loop=asyncio.get_event_loop())

            try:
                async for msg in reader:
                    # Honour runtime disable – break so bus gets shut down cleanly
                    if not status.enabled:
                        log.info("CAN commander disabled at runtime – closing bus")
                        break

                    if msg.arbitration_id != CMD_ID:
                        continue
                    if len(msg.data) < 2:
                        log.debug("CAN: short frame ignored")
                        continue

                    relay_idx   = msg.data[0]
                    command_idx = msg.data[1]

                    relay_name = RELAY_MAP.get(relay_idx)
                    action     = COMMAND_MAP.get(command_idx)

                    if relay_name is None or action is None:
                        log.warning(
                            "CAN: unknown relay=%d cmd=%d – ignored",
                            relay_idx, command_idx,
                        )
                        continue

                    log.info("CAN → relay=%s action=%s", relay_name, action)
                    status.record_command(relay_name, action)
                    relay_callback(relay_name, action)

            finally:
                notifier.stop()
                bus.shutdown()

        except Exception as exc:
            msg = f"CAN error: {exc}"
            log.error(msg)
            status.record_error(msg)
            if _is_no_such_device(exc):
                status.enabled = False
                status.record_error(
                    f"CAN disabled: interface '{INTERFACE}' not found. "
                    "Enable CAN hardware or set CAN_ENABLED=false."
                )
                log.warning("CAN interface %s not found - disabling CAN runtime", INTERFACE)
            await asyncio.sleep(5 if status.enabled else 1)  # back-off before retry


async def _ensure_interface_up(status: CanStatus) -> None:
    """Attempt to bring up the SocketCAN interface if it is down."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ip", "link", "set", INTERFACE, "up",
            "type", "can", "bitrate", str(BITRATE),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode().strip()
            # "already up" / "busy" is not a real error
            if "already" not in err.lower() and "busy" not in err.lower() and err:
                log.warning("ip link set %s up: %s", INTERFACE, err)
                status.record_error(f"interface bring-up: {err}")
        else:
            log.info("Brought up %s at %d bps", INTERFACE, BITRATE)
    except FileNotFoundError:
        log.warning("'ip' command not found – assuming %s is already up", INTERFACE)

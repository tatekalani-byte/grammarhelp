"""Talk to one connected Wii Remote / Wii U Pro Controller over HID.

The transport is anything with write(bytes), read(timeout_ms) -> bytes | None
and close(). In practice it is HidTransport; the tests use a fake controller.
"""

from __future__ import annotations

import logging
import time

from . import protocol as p
from .controllers import (
    DEFAULT_ACCEL_CALIBRATION,
    Inputs,
    decode_guitar,
    decode_pro,
    decode_wiimote,
    parse_accel_calibration,
)

log = logging.getLogger(__name__)

REPLY_TIMEOUT = 1.0
STATUS_RETRIES = 3
SILENCE_BEFORE_PING = 1.0
SILENCE_BEFORE_GIVING_UP = 3.0
CONNECT_RUMBLE_SECONDS = 0.25

REPORT_MODES = {
    p.ExtensionType.GUITAR: p.MODE_BUTTONS_ACCEL_EXT16,
    p.ExtensionType.PRO_CONTROLLER: p.MODE_EXT21,
}


class TransportError(Exception):
    """The HID device went away or refused a read/write."""


class NotResponding(Exception):
    """The device never answered; usually a paired controller that is switched off."""


class Disconnected(Exception):
    """A working controller stopped talking (turned off, out of range, batteries)."""


class HidTransport:
    def __init__(self, path: bytes):
        from .hidbackend import hid

        self._device = hid.device()
        try:
            self._device.open_path(path)
        except (OSError, ValueError) as exc:
            raise TransportError(f"could not open device: {exc}") from exc

    def write(self, data: bytes) -> None:
        try:
            written = self._device.write(bytes(data))
        except (OSError, ValueError) as exc:
            raise TransportError(f"write failed: {exc}") from exc
        if written < 0:
            raise TransportError("write failed")

    def read(self, timeout_ms: int) -> bytes | None:
        try:
            # hidapi treats a 0 ms timeout as "wait forever".
            data = self._device.read(64, max(1, timeout_ms))
        except (OSError, ValueError) as exc:
            raise TransportError(f"read failed: {exc}") from exc
        return bytes(data) if data else None

    def close(self) -> None:
        try:
            self._device.close()
        except Exception:  # closing a vanished device can fail; nothing to do about it
            pass


class WiiDevice:
    def __init__(self, transport, player: int = 1, clock=time.monotonic):
        self.transport = transport
        self.player = player
        self.clock = clock
        self.kind = p.ExtensionType.NONE
        self.status: p.Status | None = None
        self._calibration = DEFAULT_ACCEL_CALIBRATION
        self._rumble = False
        self._rumble_until = 0.0
        self._last_report = 0.0
        self._pinged = False

    # ---- setup -------------------------------------------------------------

    def connect(self) -> None:
        """Handshake: find out what is plugged in and start the data stream."""
        status = None
        for _ in range(STATUS_RETRIES):
            self._send(p.status_request())
            status = self._wait_for(p.IN_STATUS)
            if status is not None:
                break
        if status is None:
            raise NotResponding("no reply to a status request")
        self._configure(p.parse_status(status))
        self._rumble = True
        self._rumble_until = self.clock() + CONNECT_RUMBLE_SECONDS
        self._send(p.set_leds(self.player, rumble=True))

    def _configure(self, status: p.Status) -> None:
        self.status = status
        if status.extension_connected:
            self.kind = self._identify_extension()
        else:
            self.kind = p.ExtensionType.NONE
        if self.kind is p.ExtensionType.GUITAR:
            self._calibration = self._read_accel_calibration()
        self._send(p.set_leds(self.player, self._rumble))
        self._start_reporting()
        self._last_report = self.clock()
        self._pinged = False

    def _start_reporting(self) -> None:
        mode = REPORT_MODES.get(self.kind, p.MODE_BUTTONS)
        self._send(p.set_report_mode(mode, continuous=True, rumble=self._rumble))

    def _identify_extension(self) -> p.ExtensionType:
        # Writing 0x55 then 0x00 turns on the extension without encryption.
        for _ in range(2):
            if (self._write_register(p.EXT_INIT1_ADDR, b"\x55")
                    and self._write_register(p.EXT_INIT2_ADDR, b"\x00")):
                ext_id = self._read(p.EXT_ID_ADDR, 6)
                if ext_id is not None:
                    kind = p.identify_extension(ext_id)
                    log.debug("extension id %s -> %s", ext_id.hex(), kind.value)
                    return kind
        log.warning("Could not identify the attached extension")
        return p.ExtensionType.UNKNOWN

    def _read_accel_calibration(self):
        data = self._read(p.ACCEL_CALIBRATION_ADDR, 10, space=p.MEMORY_EEPROM)
        return parse_accel_calibration(data) if data else DEFAULT_ACCEL_CALIBRATION

    def _write_register(self, address: int, data: bytes) -> bool:
        self._send(p.write_memory(address, data, rumble=self._rumble))
        reply = self._wait_for(p.IN_ACK, lambda r: p.parse_ack(r).report == p.OUT_WRITE_MEMORY)
        return reply is not None and p.parse_ack(reply).error == 0

    def _read(self, address: int, size: int, space: int = p.MEMORY_REGISTERS) -> bytes | None:
        self._send(p.read_memory(address, size, space, rumble=self._rumble))
        reply = self._wait_for(
            p.IN_READ_DATA, lambda r: p.parse_read_reply(r).address_low == address & 0xFFFF
        )
        if reply is None:
            return None
        parsed = p.parse_read_reply(reply)
        return parsed.data if parsed.error == 0 else None

    def _wait_for(self, report_id: int, accept=lambda report: True) -> bytes | None:
        deadline = self.clock() + REPLY_TIMEOUT
        while True:
            remaining = deadline - self.clock()
            if remaining <= 0:
                return None
            report = self.transport.read(max(1, int(remaining * 1000)))
            if report and report[0] == report_id and accept(report):
                return report

    # ---- running -----------------------------------------------------------

    def poll(self, timeout: float = 0.1) -> Inputs | None:
        """Read one report. Returns decoded inputs for data reports, else None.

        Raises Disconnected when the controller has gone quiet for too long.
        """
        now = self.clock()
        if self._rumble and now >= self._rumble_until:
            self._rumble = False
            self._send(p.set_leds(self.player, rumble=False))

        report = self.transport.read(int(timeout * 1000))
        now = self.clock()
        if not report:
            silence = now - self._last_report
            if silence > SILENCE_BEFORE_GIVING_UP:
                raise Disconnected("controller stopped responding")
            if silence > SILENCE_BEFORE_PING and not self._pinged:
                self._pinged = True
                self._send(p.status_request(self._rumble))
            return None

        self._last_report = now
        self._pinged = False
        report_id = report[0]
        if report_id == p.IN_STATUS:
            self._on_status(p.parse_status(report))
            return None
        if p.is_data_report(report_id):
            return self._decode(report)
        return None

    def _on_status(self, status: p.Status) -> None:
        # Any status report switches the controller back to buttons-only
        # reporting, so the mode always has to be set again.
        previous = self.status
        if previous is None or previous.extension_connected != status.extension_connected:
            old_kind = self.kind
            self._configure(status)
            if self.kind is not old_kind:
                log.info("Player %d: now a %s", self.player, describe(self.kind))
        else:
            self.status = status
            self._start_reporting()

    def _decode(self, report: bytes) -> Inputs | None:
        buttons, accel, ext = p.split_data_report(report)
        if self.kind is p.ExtensionType.GUITAR:
            if ext is None or len(ext) < 6:
                return None
            return decode_guitar(ext, buttons, accel, self._calibration)
        if self.kind is p.ExtensionType.PRO_CONTROLLER:
            if ext is None or len(ext) < 11:
                return None
            return decode_pro(ext)
        if buttons is None:
            return None
        return decode_wiimote(buttons)

    def _send(self, report: bytes) -> None:
        self.transport.write(report)

    def close(self) -> None:
        try:
            self._send(p.set_leds(0, rumble=False))
        except TransportError:
            pass
        self.transport.close()


def describe(kind: p.ExtensionType) -> str:
    if kind is p.ExtensionType.NONE:
        return "Wii Remote"
    if kind in (p.ExtensionType.GUITAR, p.ExtensionType.PRO_CONTROLLER):
        return kind.value
    return f"Wii Remote with a {kind.value} (only the Wii Remote's own buttons are used)"

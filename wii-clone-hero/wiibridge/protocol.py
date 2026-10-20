"""Low-level Wii Remote HID protocol: report IDs, report builders and parsers.

Everything that speaks Bluetooth to a Wii Remote, a Wii Remote Plus or a Wii U
Pro Controller uses the same set of numbered HID reports. Output reports go
from the PC to the controller, input reports come back. References:
https://wiibrew.org/wiki/Wiimote and the Linux hid-wiimote driver.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

NINTENDO_VID = 0x057E
WIIMOTE_PIDS = (
    0x0306,  # Wii Remote (RVL-CNT-01)
    0x0330,  # Wii Remote Plus (RVL-CNT-01-TR) and Wii U Pro Controller (RVL-CNT-01-UC)
)

# Output reports (PC -> controller). The low bit of the first payload byte of
# every output report is the rumble motor.
OUT_LEDS = 0x11
OUT_REPORT_MODE = 0x12
OUT_STATUS_REQUEST = 0x15
OUT_WRITE_MEMORY = 0x16
OUT_READ_MEMORY = 0x17

# Input reports (controller -> PC).
IN_STATUS = 0x20
IN_READ_DATA = 0x21
IN_ACK = 0x22

# Data reporting modes we use.
MODE_BUTTONS = 0x30  # core buttons only
MODE_BUTTONS_ACCEL_EXT16 = 0x35  # core buttons, accelerometer, 16 extension bytes
MODE_EXT21 = 0x3D  # 21 extension bytes, nothing else

MEMORY_EEPROM = 0x00
MEMORY_REGISTERS = 0x04

EXT_INIT1_ADDR = 0xA400F0
EXT_INIT2_ADDR = 0xA400FB
EXT_ID_ADDR = 0xA400FA
ACCEL_CALIBRATION_ADDR = 0x0016

# Where the (buttons, accelerometer, extension) bytes live in each data report.
# Each entry is ((start, end) or None) for those three fields.
_DATA_LAYOUT = {
    0x30: ((1, 3), None, None),
    0x31: ((1, 3), (3, 6), None),
    0x32: ((1, 3), None, (3, 11)),
    0x33: ((1, 3), (3, 6), None),
    0x34: ((1, 3), None, (3, 22)),
    0x35: ((1, 3), (3, 6), (6, 22)),
    0x36: ((1, 3), None, (13, 22)),
    0x37: ((1, 3), (3, 6), (16, 22)),
    0x3D: (None, None, (1, 22)),
}


class ExtensionType(enum.Enum):
    NONE = "none"
    GUITAR = "Guitar Hero guitar"
    PRO_CONTROLLER = "Wii U Pro Controller"
    DRUMS = "Guitar Hero drums"
    TURNTABLE = "DJ Hero turntable"
    NUNCHUK = "Nunchuk"
    CLASSIC = "Classic Controller"
    BALANCE_BOARD = "Balance Board"
    UNKNOWN = "unknown extension"


_EXTENSION_IDS = {
    bytes.fromhex("0000a4200103"): ExtensionType.GUITAR,
    bytes.fromhex("0000a4200120"): ExtensionType.PRO_CONTROLLER,
    bytes.fromhex("0100a4200103"): ExtensionType.DRUMS,
    bytes.fromhex("0300a4200103"): ExtensionType.TURNTABLE,
    bytes.fromhex("0000a4200000"): ExtensionType.NUNCHUK,
    bytes.fromhex("0000a4200101"): ExtensionType.CLASSIC,
    bytes.fromhex("0100a4200101"): ExtensionType.CLASSIC,
    bytes.fromhex("0000a4200402"): ExtensionType.BALANCE_BOARD,
}


def identify_extension(ext_id: bytes) -> ExtensionType:
    return _EXTENSION_IDS.get(bytes(ext_id), ExtensionType.UNKNOWN)


def _rumble_bit(rumble: bool) -> int:
    return 0x01 if rumble else 0x00


def player_led_bits(player: int) -> int:
    """LED pattern for player 1-4; players 5-7 use two LEDs like the Wii does. 0 is all off."""
    patterns = {0: 0x0, 1: 0x1, 2: 0x2, 3: 0x4, 4: 0x8, 5: 0x9, 6: 0xA, 7: 0xC}
    return patterns.get(player, 0xF)


def set_leds(player: int, rumble: bool = False) -> bytes:
    return bytes([OUT_LEDS, (player_led_bits(player) << 4) | _rumble_bit(rumble)])


def set_report_mode(mode: int, continuous: bool = True, rumble: bool = False) -> bytes:
    flags = (0x04 if continuous else 0x00) | _rumble_bit(rumble)
    return bytes([OUT_REPORT_MODE, flags, mode])


def status_request(rumble: bool = False) -> bytes:
    return bytes([OUT_STATUS_REQUEST, _rumble_bit(rumble)])


def write_memory(address: int, data: bytes, space: int = MEMORY_REGISTERS,
                 rumble: bool = False) -> bytes:
    if not 1 <= len(data) <= 16:
        raise ValueError("a single write carries 1-16 bytes")
    payload = bytes(data) + bytes(16 - len(data))
    return bytes([OUT_WRITE_MEMORY, space | _rumble_bit(rumble)]) + address.to_bytes(3, "big") \
        + bytes([len(data)]) + payload


def read_memory(address: int, size: int, space: int = MEMORY_REGISTERS,
                rumble: bool = False) -> bytes:
    return bytes([OUT_READ_MEMORY, space | _rumble_bit(rumble)]) + address.to_bytes(3, "big") \
        + size.to_bytes(2, "big")


@dataclass(frozen=True)
class Status:
    extension_connected: bool
    battery_low: bool
    battery_level: int  # 0-255, a full set of batteries reads about 200

    @property
    def battery_percent(self) -> int:
        return min(100, round(self.battery_level * 100 / 200))


def parse_status(report: bytes) -> Status:
    flags = report[3]
    return Status(
        extension_connected=bool(flags & 0x02),
        battery_low=bool(flags & 0x01),
        battery_level=report[6],
    )


@dataclass(frozen=True)
class ReadReply:
    address_low: int  # low 16 bits of the address that was read
    error: int  # 0 = OK, 7 = write-only register, 8 = no such address
    data: bytes


def parse_read_reply(report: bytes) -> ReadReply:
    size = (report[3] >> 4) + 1
    return ReadReply(
        address_low=int.from_bytes(report[4:6], "big"),
        error=report[3] & 0x0F,
        data=bytes(report[6:6 + size]),
    )


@dataclass(frozen=True)
class Ack:
    report: int
    error: int


def parse_ack(report: bytes) -> Ack:
    return Ack(report=report[3], error=report[4])


def is_data_report(report_id: int) -> bool:
    return report_id in _DATA_LAYOUT


def split_data_report(report: bytes):
    """Return (buttons, accel, extension) byte strings from a data report.

    A field the report doesn't carry is None. A report that is shorter than its
    mode says (which shouldn't happen) also yields None for the missing parts.
    """
    layout = _DATA_LAYOUT[report[0]]
    parts = []
    for span in layout:
        if span is None or len(report) < span[1]:
            parts.append(None)
        else:
            parts.append(bytes(report[span[0]:span[1]]))
    return tuple(parts)

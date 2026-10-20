"""Turn raw report bytes into named buttons and axes.

Decoders are stateless: calibration that has to be learned over time (whammy
range, tilt) lives in mapping.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Inputs:
    buttons: frozenset = frozenset()
    # Normalized sticks are -1..1 with +y meaning up. Raw values are kept as-is.
    axes: dict = field(default_factory=dict)
    # Gravity vector in g units, or None when the report carries no accelerometer data.
    accel: tuple | None = None


@dataclass(frozen=True)
class AccelCalibration:
    zero: tuple = (512, 512, 512)
    one_g: tuple = (616, 616, 616)


DEFAULT_ACCEL_CALIBRATION = AccelCalibration()


def parse_accel_calibration(data: bytes) -> AccelCalibration:
    """Parse the 10-byte block the Wii Remote stores at EEPROM 0x16."""
    if len(data) < 8:
        return DEFAULT_ACCEL_CALIBRATION

    def ten_bit(msb_bytes, lsb):
        return (
            (msb_bytes[0] << 2) | ((lsb >> 4) & 0x3),
            (msb_bytes[1] << 2) | ((lsb >> 2) & 0x3),
            (msb_bytes[2] << 2) | (lsb & 0x3),
        )

    zero = ten_bit(data[0:3], data[3])
    one_g = ten_bit(data[4:7], data[7])
    if any(g <= z for z, g in zip(zero, one_g)):
        return DEFAULT_ACCEL_CALIBRATION
    return AccelCalibration(zero=zero, one_g=one_g)


_CORE_BUTTONS = (
    (0, 0x01, "wm_left"),
    (0, 0x02, "wm_right"),
    (0, 0x04, "wm_down"),
    (0, 0x08, "wm_up"),
    (0, 0x10, "wm_plus"),
    (1, 0x01, "wm_two"),
    (1, 0x02, "wm_one"),
    (1, 0x04, "wm_b"),
    (1, 0x08, "wm_a"),
    (1, 0x10, "wm_minus"),
    (1, 0x80, "wm_home"),
)


def decode_core_buttons(buttons: bytes) -> set:
    """Wii Remote buttons. These are active-high, unlike extension buttons."""
    return {name for byte, mask, name in _CORE_BUTTONS if buttons[byte] & mask}


def decode_accel(buttons: bytes, accel: bytes, calibration: AccelCalibration) -> tuple:
    raw = (
        (accel[0] << 2) | ((buttons[0] >> 5) & 0x3),
        (accel[1] << 2) | ((buttons[1] >> 4) & 0x2),
        (accel[2] << 2) | ((buttons[1] >> 5) & 0x2),
    )
    return tuple(
        (r - z) / (g - z) for r, z, g in zip(raw, calibration.zero, calibration.one_g)
    )


def decode_wiimote(buttons: bytes) -> Inputs:
    return Inputs(buttons=frozenset(decode_core_buttons(buttons)))


# Extension buttons are active-low: a cleared bit means pressed.
_GUITAR_BUTTONS = (
    (5, 0x10, "green"),
    (5, 0x40, "red"),
    (5, 0x08, "yellow"),
    (5, 0x20, "blue"),
    (5, 0x80, "orange"),
    (5, 0x01, "strum_up"),
    (4, 0x40, "strum_down"),
    (4, 0x04, "plus"),
    (4, 0x10, "minus"),
)

GUITAR_STICK_CENTER = 32
GUITAR_STICK_RANGE = 26
TOUCH_STRIP_NONE = 0x0F


def _normalize(value, center, span, deadzone):
    v = (value - center) / span
    if abs(v) < deadzone:
        return 0.0
    return max(-1.0, min(1.0, v))


def decode_guitar(ext: bytes, buttons: bytes | None = None, accel: bytes | None = None,
                  calibration: AccelCalibration = DEFAULT_ACCEL_CALIBRATION) -> Inputs:
    pressed = {name for byte, mask, name in _GUITAR_BUTTONS if not ext[byte] & mask}
    if buttons is not None:
        pressed |= decode_core_buttons(buttons)

    sx, sy = ext[0] & 0x3F, ext[1] & 0x3F
    if sx == 0 and sy == 0:  # guitars without a stick report zeros
        stick_x = stick_y = 0.0
    else:
        stick_x = _normalize(sx, GUITAR_STICK_CENTER, GUITAR_STICK_RANGE, 0.2)
        stick_y = _normalize(sy, GUITAR_STICK_CENTER, GUITAR_STICK_RANGE, 0.2)

    axes = {
        "stick_x": stick_x,
        "stick_y": stick_y,
        "whammy_raw": ext[3] & 0x1F,
        "touch_raw": ext[2] & 0x1F,
        # Guitar Hero 3 guitars set this bit; they have no touch strip.
        "gh3": 1 if ext[0] & 0x80 else 0,
    }
    gravity = None
    if buttons is not None and accel is not None:
        gravity = decode_accel(buttons, accel, calibration)
    return Inputs(buttons=frozenset(pressed), axes=axes, accel=gravity)


# Touch strip (World Tour and later guitars): raw value -> frets touched.
_TOUCH_STRIP = {}
for _values, _frets in (
    ((0x04, 0x05), ("green",)),
    ((0x06, 0x07, 0x08, 0x09), ("green", "red")),
    ((0x0A, 0x0B, 0x0C), ("red",)),
    ((0x0D, 0x0E, 0x10, 0x11), ("red", "yellow")),
    ((0x12, 0x13), ("yellow",)),
    ((0x14, 0x15, 0x16), ("yellow", "blue")),
    ((0x17, 0x18, 0x19), ("blue",)),
    ((0x1A, 0x1B, 0x1C, 0x1D, 0x1E), ("blue", "orange")),
    ((0x1F,), ("orange",)),
):
    for _value in _values:
        _TOUCH_STRIP[_value] = frozenset(_frets)


def touch_strip_frets(raw: int) -> frozenset:
    return _TOUCH_STRIP.get(raw, frozenset())


_PRO_BUTTONS = (
    (8, 0x80, "right"),
    (8, 0x40, "down"),
    (8, 0x20, "l"),
    (8, 0x10, "minus"),
    (8, 0x08, "home"),
    (8, 0x04, "plus"),
    (8, 0x02, "r"),
    (9, 0x80, "zl"),
    (9, 0x40, "b"),
    (9, 0x20, "y"),
    (9, 0x10, "a"),
    (9, 0x08, "x"),
    (9, 0x04, "zr"),
    (9, 0x02, "left"),
    (9, 0x01, "up"),
    (10, 0x02, "lstick"),
    (10, 0x01, "rstick"),
)

PRO_STICK_CENTER = 0x800
PRO_STICK_RANGE = 0x400


def decode_pro(ext: bytes) -> Inputs:
    pressed = {name for byte, mask, name in _PRO_BUTTONS if not ext[byte] & mask}

    def stick(lo, hi):
        return _normalize(ext[lo] | ((ext[hi] & 0x0F) << 8), PRO_STICK_CENTER, PRO_STICK_RANGE, 0.1)

    axes = {
        "lx": stick(0, 1),
        "rx": stick(2, 3),
        "ly": stick(4, 5),
        "ry": stick(6, 7),
    }
    return Inputs(buttons=frozenset(pressed), axes=axes)

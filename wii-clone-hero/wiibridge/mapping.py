"""Map decoded controller inputs onto a virtual Xbox 360 controller.

The guitar layout copies a real Xbox 360 Guitar Hero guitar, which is what
Clone Hero and most guides expect:

    green A, red B, yellow Y, blue X, orange LB,
    strum up/down = D-pad up/down, + = Start, - = Back (star power),
    whammy = right stick X, tilt = right stick Y (and also holds Back).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .controllers import TOUCH_STRIP_NONE, Inputs, touch_strip_frets
from .protocol import ExtensionType


@dataclass(frozen=True)
class PadState:
    buttons: frozenset = frozenset()
    lx: float = 0.0
    ly: float = 0.0
    rx: float = 0.0
    ry: float = 0.0
    lt: float = 0.0
    rt: float = 0.0


@dataclass
class Options:
    tilt: bool = True
    tilt_threshold: float = 0.45  # fraction of the way from "held normally" to "neck straight up"
    touch_strip: bool = False


GUITAR_BUTTONS = {
    "green": "A",
    "red": "B",
    "yellow": "Y",
    "blue": "X",
    "orange": "LB",
    "strum_up": "UP",
    "strum_down": "DOWN",
    "plus": "START",
    "minus": "BACK",
    "wm_home": "GUIDE",
}

PRO_BUTTONS = {
    "a": "A",
    "b": "B",
    "x": "X",
    "y": "Y",
    "l": "LB",
    "r": "RB",
    "minus": "BACK",
    "plus": "START",
    "home": "GUIDE",
    "lstick": "LS",
    "rstick": "RS",
    "up": "UP",
    "down": "DOWN",
    "left": "LEFT",
    "right": "RIGHT",
}

# A bare Wii Remote held sideways, D-pad under the left thumb.
WIIMOTE_BUTTONS = {
    "wm_up": "LEFT",
    "wm_down": "RIGHT",
    "wm_left": "DOWN",
    "wm_right": "UP",
    "wm_two": "A",
    "wm_one": "B",
    "wm_a": "X",
    "wm_b": "Y",
    "wm_plus": "START",
    "wm_minus": "BACK",
    "wm_home": "GUIDE",
}


def _remap(buttons, table):
    return frozenset(table[b] for b in buttons if b in table)


class WiimoteMapper:
    def map(self, inputs: Inputs) -> PadState:
        return PadState(buttons=_remap(inputs.buttons, WIIMOTE_BUTTONS))


class ProMapper:
    def map(self, inputs: Inputs) -> PadState:
        axes = inputs.axes
        return PadState(
            buttons=_remap(inputs.buttons, PRO_BUTTONS),
            lx=axes.get("lx", 0.0),
            ly=axes.get("ly", 0.0),
            rx=axes.get("rx", 0.0),
            ry=axes.get("ry", 0.0),
            lt=1.0 if "zl" in inputs.buttons else 0.0,
            rt=1.0 if "zr" in inputs.buttons else 0.0,
        )


class GuitarMapper:
    """Guitar mapping plus the calibration it learns while you play.

    Whammy: the resting and fully-pressed values differ between guitars, so the
    range grows to fit whatever the bar reports. Push it all the way once.

    Tilt: the Wii Remote inside the guitar has its X axis pointing at the floor
    when the guitar is held normally and its Y axis pointing at the floor when
    the neck points straight up, so the angle between the two is the tilt.
    Press 1 on the Wii Remote while holding the guitar normally, or 2 while
    holding the neck straight up, to recalibrate either end.
    """

    WHAMMY_DEFAULT_SPAN = 8
    TILT_SMOOTHING = 0.3
    TILT_HYSTERESIS = 0.1

    def __init__(self, options: Options | None = None, log=None):
        self.options = options or Options()
        self.log = log or (lambda message: None)
        self.whammy_min = None
        self.whammy_max = None
        self.tilt_neutral = 0.0
        self.tilt_full = math.pi / 2
        self._angle = None
        self._tilted = False
        self._previous_buttons = frozenset()

    def map(self, inputs: Inputs) -> PadState:
        pressed = set(inputs.buttons)
        newly_pressed = inputs.buttons - self._previous_buttons
        self._previous_buttons = inputs.buttons

        axes = inputs.axes
        if self.options.touch_strip and not axes.get("gh3"):
            touch = axes.get("touch_raw", TOUCH_STRIP_NONE)
            if touch != TOUCH_STRIP_NONE:
                pressed |= touch_strip_frets(touch)

        buttons = set(_remap(pressed, GUITAR_BUTTONS))
        tilt = self._tilt(inputs.accel, newly_pressed)
        if self._tilted:
            buttons.add("BACK")

        return PadState(
            buttons=frozenset(buttons),
            lx=axes.get("stick_x", 0.0),
            ly=axes.get("stick_y", 0.0),
            rx=self._whammy(axes.get("whammy_raw")) * 2 - 1,
            ry=tilt * 2 - 1,
        )

    def _whammy(self, raw) -> float:
        if raw is None:
            return 0.0
        if self.whammy_min is None or raw < self.whammy_min:
            self.whammy_min = raw
        if self.whammy_max is None or raw > self.whammy_max:
            self.whammy_max = raw
        top = max(self.whammy_max, self.whammy_min + self.WHAMMY_DEFAULT_SPAN)
        return max(0.0, min(1.0, (raw - self.whammy_min) / (top - self.whammy_min)))

    def _tilt(self, gravity, newly_pressed) -> float:
        if not self.options.tilt or gravity is None:
            self._tilted = False
            return 0.0

        gx, gy, _ = gravity
        if math.hypot(gx, gy) < 0.4:
            # Lying face up or face down: the angle is meaningless, call it level.
            angle = self.tilt_neutral
        else:
            angle = math.atan2(abs(gy), abs(gx))

        if self._angle is None:
            self._angle = angle
        else:
            self._angle += (angle - self._angle) * self.TILT_SMOOTHING

        if "wm_one" in newly_pressed:
            self.tilt_neutral = angle
            self.log(f"Tilt: resting angle set to {math.degrees(angle):.0f} degrees")
        if "wm_two" in newly_pressed:
            self.tilt_full = angle
            self.log(f"Tilt: full-tilt angle set to {math.degrees(angle):.0f} degrees")

        span = self.tilt_full - self.tilt_neutral
        if abs(span) < math.radians(10):
            span = math.copysign(math.radians(10), span or 1.0)
        tilt = max(0.0, min(1.0, (self._angle - self.tilt_neutral) / span))

        threshold = self.options.tilt_threshold
        if self._tilted:
            self._tilted = tilt > threshold - self.TILT_HYSTERESIS
        else:
            self._tilted = tilt >= threshold
        return tilt


def mapper_for(kind: ExtensionType, options: Options | None = None, log=None):
    if kind is ExtensionType.GUITAR:
        return GuitarMapper(options, log)
    if kind is ExtensionType.PRO_CONTROLLER:
        return ProMapper()
    return WiimoteMapper()

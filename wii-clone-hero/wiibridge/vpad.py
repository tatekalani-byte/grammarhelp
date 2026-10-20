"""Virtual Xbox 360 controllers that games (Clone Hero) can see.

Windows: ViGEmBus through the `vgamepad` package.
Linux:   /dev/uinput through the `evdev` package.
"""

from __future__ import annotations

import sys

from .mapping import PadState


class SetupError(Exception):
    """The virtual controller driver is missing or not usable."""


class VigemPad:
    def __init__(self):
        try:
            import vgamepad
        except ImportError as exc:
            raise SetupError(
                "The 'vgamepad' package is missing. Install it with:\n"
                "    python -m pip install vgamepad\n"
                "(it also installs the ViGEmBus driver; accept that installer)."
            ) from exc
        try:
            self._pad = vgamepad.VX360Gamepad()
        except Exception as exc:
            raise SetupError(
                "Could not create a virtual Xbox 360 controller. The ViGEmBus driver is\n"
                "probably not installed. Get it from\n"
                "    https://github.com/nefarius/ViGEmBus/releases\n"
                f"install it, reboot, and try again. (Error: {exc})"
            ) from exc
        b = vgamepad.XUSB_BUTTON
        self._buttons = {
            "A": b.XUSB_GAMEPAD_A,
            "B": b.XUSB_GAMEPAD_B,
            "X": b.XUSB_GAMEPAD_X,
            "Y": b.XUSB_GAMEPAD_Y,
            "LB": b.XUSB_GAMEPAD_LEFT_SHOULDER,
            "RB": b.XUSB_GAMEPAD_RIGHT_SHOULDER,
            "BACK": b.XUSB_GAMEPAD_BACK,
            "START": b.XUSB_GAMEPAD_START,
            "GUIDE": b.XUSB_GAMEPAD_GUIDE,
            "LS": b.XUSB_GAMEPAD_LEFT_THUMB,
            "RS": b.XUSB_GAMEPAD_RIGHT_THUMB,
            "UP": b.XUSB_GAMEPAD_DPAD_UP,
            "DOWN": b.XUSB_GAMEPAD_DPAD_DOWN,
            "LEFT": b.XUSB_GAMEPAD_DPAD_LEFT,
            "RIGHT": b.XUSB_GAMEPAD_DPAD_RIGHT,
        }

    def update(self, state: PadState) -> None:
        pad = self._pad
        for name, flag in self._buttons.items():
            if name in state.buttons:
                pad.press_button(flag)
            else:
                pad.release_button(flag)
        pad.left_joystick_float(state.lx, state.ly)
        pad.right_joystick_float(state.rx, state.ry)
        pad.left_trigger_float(state.lt)
        pad.right_trigger_float(state.rt)
        pad.update()

    def close(self) -> None:
        # vgamepad unplugs the virtual controller when the object is freed.
        self._pad = None


class UinputPad:
    STICK_MAX = 32767
    TRIGGER_MAX = 255

    def __init__(self):
        try:
            from evdev import AbsInfo, UInput, UInputError, ecodes as e
        except ImportError as exc:
            raise SetupError(
                "The 'evdev' package is missing. Install it with:\n"
                "    python -m pip install evdev"
            ) from exc
        self._e = e
        self._buttons = {
            "A": e.BTN_A,
            "B": e.BTN_B,
            "X": e.BTN_X,
            "Y": e.BTN_Y,
            "LB": e.BTN_TL,
            "RB": e.BTN_TR,
            "BACK": e.BTN_SELECT,
            "START": e.BTN_START,
            "GUIDE": e.BTN_MODE,
            "LS": e.BTN_THUMBL,
            "RS": e.BTN_THUMBR,
        }
        stick = AbsInfo(0, -self.STICK_MAX - 1, self.STICK_MAX, 16, 128, 0)
        trigger = AbsInfo(0, 0, self.TRIGGER_MAX, 0, 0, 0)
        hat = AbsInfo(0, -1, 1, 0, 0, 0)
        capabilities = {
            e.EV_KEY: list(self._buttons.values()),
            e.EV_ABS: [
                (e.ABS_X, stick), (e.ABS_Y, stick), (e.ABS_Z, trigger),
                (e.ABS_RX, stick), (e.ABS_RY, stick), (e.ABS_RZ, trigger),
                (e.ABS_HAT0X, hat), (e.ABS_HAT0Y, hat),
            ],
        }
        try:
            # Xbox 360 USB IDs so SDL-based games apply their standard 360 layout.
            self._ui = UInput(capabilities, name="Wii Bridge (Xbox 360 layout)",
                              vendor=0x045E, product=0x028E, version=0x110, bustype=e.BUS_USB)
        except (OSError, UInputError) as exc:
            raise SetupError(
                "Could not open /dev/uinput to create a virtual controller. See the\n"
                "Linux section of README.md for the udev rule that allows it.\n"
                f"(Error: {exc})"
            ) from exc

    def update(self, state: PadState) -> None:
        e, ui = self._e, self._ui
        for name, code in self._buttons.items():
            ui.write(e.EV_KEY, code, 1 if name in state.buttons else 0)
        # Linux axes point down for +Y, the opposite of XInput.
        ui.write(e.EV_ABS, e.ABS_X, self._stick(state.lx))
        ui.write(e.EV_ABS, e.ABS_Y, self._stick(-state.ly))
        ui.write(e.EV_ABS, e.ABS_RX, self._stick(state.rx))
        ui.write(e.EV_ABS, e.ABS_RY, self._stick(-state.ry))
        ui.write(e.EV_ABS, e.ABS_Z, round(state.lt * self.TRIGGER_MAX))
        ui.write(e.EV_ABS, e.ABS_RZ, round(state.rt * self.TRIGGER_MAX))
        b = state.buttons
        ui.write(e.EV_ABS, e.ABS_HAT0X, ("RIGHT" in b) - ("LEFT" in b))
        ui.write(e.EV_ABS, e.ABS_HAT0Y, ("DOWN" in b) - ("UP" in b))
        ui.syn()

    def _stick(self, value: float) -> int:
        return round(max(-1.0, min(1.0, value)) * self.STICK_MAX)

    def close(self) -> None:
        self._ui.close()


def create_pad():
    if sys.platform == "win32":
        return VigemPad()
    if sys.platform.startswith("linux"):
        return UinputPad()
    raise SetupError("Virtual controllers are only supported on Windows and Linux.")

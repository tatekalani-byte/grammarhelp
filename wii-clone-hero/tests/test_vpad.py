import sys
import types
import unittest
from unittest import mock

from wiibridge.mapping import PadState
from wiibridge.vpad import SetupError, UinputPad, VigemPad

GUITAR_STATE = PadState(buttons=frozenset({"A", "LB", "DOWN", "BACK"}), rx=0.5, ry=-1.0, lt=1.0)


def fake_vgamepad(fail=False):
    """Stand-in for the vgamepad package with the same names and button values."""
    module = types.ModuleType("vgamepad")

    class XUSB_BUTTON:
        XUSB_GAMEPAD_DPAD_UP = 0x0001
        XUSB_GAMEPAD_DPAD_DOWN = 0x0002
        XUSB_GAMEPAD_DPAD_LEFT = 0x0004
        XUSB_GAMEPAD_DPAD_RIGHT = 0x0008
        XUSB_GAMEPAD_START = 0x0010
        XUSB_GAMEPAD_BACK = 0x0020
        XUSB_GAMEPAD_LEFT_THUMB = 0x0040
        XUSB_GAMEPAD_RIGHT_THUMB = 0x0080
        XUSB_GAMEPAD_LEFT_SHOULDER = 0x0100
        XUSB_GAMEPAD_RIGHT_SHOULDER = 0x0200
        XUSB_GAMEPAD_GUIDE = 0x0400
        XUSB_GAMEPAD_A = 0x1000
        XUSB_GAMEPAD_B = 0x2000
        XUSB_GAMEPAD_X = 0x4000
        XUSB_GAMEPAD_Y = 0x8000

    class VX360Gamepad:
        def __init__(self):
            if fail:
                raise Exception("VIGEM_ERROR_BUS_NOT_FOUND")
            self.buttons = 0
            self.sent = []

        def press_button(self, button):
            self.buttons |= button

        def release_button(self, button):
            self.buttons &= ~button

        def left_joystick_float(self, x_value_float, y_value_float):
            self.left = (x_value_float, y_value_float)

        def right_joystick_float(self, x_value_float, y_value_float):
            self.right = (x_value_float, y_value_float)

        def left_trigger_float(self, value_float):
            self.lt = value_float

        def right_trigger_float(self, value_float):
            self.rt = value_float

        def update(self):
            self.sent.append((self.buttons, self.left, self.right, self.lt, self.rt))

    module.XUSB_BUTTON = XUSB_BUTTON
    module.VX360Gamepad = VX360Gamepad
    return module


class VigemPadTests(unittest.TestCase):
    def test_state_is_sent_as_one_xinput_report(self):
        with mock.patch.dict(sys.modules, {"vgamepad": fake_vgamepad()}):
            pad = VigemPad()
            gamepad = pad._pad
            pad.update(GUITAR_STATE)
            pad.update(PadState())
        self.assertEqual(gamepad.sent[0], (0x1000 | 0x0100 | 0x0002 | 0x0020, (0.0, 0.0), (0.5, -1.0), 1.0, 0.0))
        self.assertEqual(gamepad.sent[1], (0, (0.0, 0.0), (0.0, 0.0), 0.0, 0.0))

    def test_missing_driver_gives_a_helpful_error(self):
        with mock.patch.dict(sys.modules, {"vgamepad": fake_vgamepad(fail=True)}):
            with self.assertRaises(SetupError) as raised:
                VigemPad()
        self.assertIn("ViGEmBus", str(raised.exception))


try:
    import evdev
except ImportError:
    evdev = None


@unittest.skipIf(evdev is None, "evdev is only installed on Linux")
class UinputPadTests(unittest.TestCase):
    def test_events_follow_linux_conventions(self):
        created = []

        class FakeUInput:
            def __init__(self, capabilities, **kwargs):
                self.capabilities = capabilities
                self.kwargs = kwargs
                self.events = {}
                self.syncs = 0
                created.append(self)

            def write(self, kind, code, value):
                self.events[(kind, code)] = value

            def syn(self):
                self.syncs += 1

            def close(self):
                pass

        e = evdev.ecodes
        with mock.patch.object(evdev, "UInput", FakeUInput):
            pad = UinputPad()
            pad.update(GUITAR_STATE)
        ui = created[0]
        self.assertEqual((ui.kwargs["vendor"], ui.kwargs["product"]), (0x045E, 0x028E))
        self.assertEqual(ui.events[(e.EV_KEY, e.BTN_A)], 1)
        self.assertEqual(ui.events[(e.EV_KEY, e.BTN_B)], 0)
        self.assertEqual(ui.events[(e.EV_KEY, e.BTN_TL)], 1)
        self.assertEqual(ui.events[(e.EV_KEY, e.BTN_SELECT)], 1)
        self.assertEqual(ui.events[(e.EV_ABS, e.ABS_HAT0Y)], 1)  # D-pad down is +1 on Linux
        self.assertEqual(ui.events[(e.EV_ABS, e.ABS_RX)], 16384)
        self.assertEqual(ui.events[(e.EV_ABS, e.ABS_RY)], 32767)  # XInput -1 (down) is +max on Linux
        self.assertEqual(ui.events[(e.EV_ABS, e.ABS_Z)], 255)
        self.assertEqual(ui.syncs, 1)

    def test_missing_uinput_gives_a_helpful_error(self):
        def refuse(*args, **kwargs):
            raise evdev.UInputError('"/dev/uinput" does not exist')

        with mock.patch.object(evdev, "UInput", refuse):
            with self.assertRaises(SetupError) as raised:
                UinputPad()
        self.assertIn("README", str(raised.exception))


if __name__ == "__main__":
    unittest.main()

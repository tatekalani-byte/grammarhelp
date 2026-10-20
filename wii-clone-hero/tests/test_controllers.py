import unittest

from tests.fake_wiimote import ACCEL_CALIBRATION, accel_bytes, guitar_ext, pro_report
from wiibridge import controllers as c


class GuitarDecodeTests(unittest.TestCase):
    def test_nothing_pressed(self):
        inputs = c.decode_guitar(guitar_ext())
        self.assertEqual(inputs.buttons, frozenset())
        self.assertEqual(inputs.axes["stick_x"], 0.0)
        self.assertEqual(inputs.axes["whammy_raw"], 0x10)

    def test_each_fret_and_strum(self):
        for fret in ("green", "red", "yellow", "blue", "orange"):
            self.assertEqual(c.decode_guitar(guitar_ext(frets=[fret])).buttons, {fret})
        self.assertEqual(c.decode_guitar(guitar_ext(strum="up")).buttons, {"strum_up"})
        self.assertEqual(c.decode_guitar(guitar_ext(strum="down")).buttons, {"strum_down"})
        self.assertEqual(c.decode_guitar(guitar_ext(plus=True, minus=True)).buttons, {"plus", "minus"})

    def test_chord(self):
        inputs = c.decode_guitar(guitar_ext(frets=["green", "yellow", "orange"], strum="down"))
        self.assertEqual(inputs.buttons, {"green", "yellow", "orange", "strum_down"})

    def test_stick(self):
        inputs = c.decode_guitar(guitar_ext(stick=(58, 6)))
        self.assertEqual(inputs.axes["stick_x"], 1.0)
        self.assertEqual(inputs.axes["stick_y"], -1.0)

    def test_gh3_flag(self):
        self.assertEqual(c.decode_guitar(guitar_ext(gh3=True)).axes["gh3"], 1)
        self.assertEqual(c.decode_guitar(guitar_ext()).axes["gh3"], 0)

    def test_accelerometer_with_calibration(self):
        calibration = c.parse_accel_calibration(ACCEL_CALIBRATION)
        self.assertEqual(calibration.zero, (512, 512, 512))
        self.assertEqual(calibration.one_g, (616, 616, 616))
        inputs = c.decode_guitar(guitar_ext(), b"\x00\x00", accel_bytes(1.0, 0.0, -1.0), calibration)
        gx, gy, gz = inputs.accel
        self.assertAlmostEqual(gx, 1.0, places=1)
        self.assertAlmostEqual(gy, 0.0, places=1)
        self.assertAlmostEqual(gz, -1.0, places=1)

    def test_bad_calibration_falls_back(self):
        self.assertEqual(c.parse_accel_calibration(bytes(10)), c.DEFAULT_ACCEL_CALIBRATION)

    def test_wiimote_buttons_come_through_on_a_guitar(self):
        inputs = c.decode_guitar(guitar_ext(), bytes([0x00, 0x82]), b"\x80\x80\x80")
        self.assertEqual(inputs.buttons, {"wm_one", "wm_home"})

    def test_touch_strip_table(self):
        self.assertEqual(c.touch_strip_frets(0x04), {"green"})
        self.assertEqual(c.touch_strip_frets(0x14), {"yellow", "blue"})
        self.assertEqual(c.touch_strip_frets(0x1F), {"orange"})
        self.assertEqual(c.touch_strip_frets(0x0F), frozenset())


class ProDecodeTests(unittest.TestCase):
    def test_buttons(self):
        ext = pro_report(buttons=["a", "zr", "lstick", "up", "minus"])[1:]
        self.assertEqual(c.decode_pro(ext).buttons, {"a", "zr", "lstick", "up", "minus"})

    def test_sticks(self):
        ext = pro_report(lx=0x800 + 0x400, ly=0x800 - 0x200, rx=0x800 + 0x20, ry=0xFFF)[1:]
        axes = c.decode_pro(ext).axes
        self.assertEqual(axes["lx"], 1.0)
        self.assertEqual(axes["ly"], -0.5)
        self.assertEqual(axes["rx"], 0.0)  # inside the dead zone
        self.assertEqual(axes["ry"], 1.0)


class WiimoteDecodeTests(unittest.TestCase):
    def test_core_buttons(self):
        self.assertEqual(c.decode_wiimote(bytes([0x18, 0x09])).buttons, {"wm_up", "wm_plus", "wm_two", "wm_a"})

    def test_accel_bits_are_not_buttons(self):
        self.assertEqual(c.decode_wiimote(bytes([0x60, 0x60])).buttons, frozenset())


if __name__ == "__main__":
    unittest.main()

import math
import unittest

from tests.fake_wiimote import guitar_ext, pro_report
from wiibridge import controllers as c
from wiibridge.mapping import GuitarMapper, Options, ProMapper, WiimoteMapper, mapper_for
from wiibridge.protocol import ExtensionType


def guitar(frets=(), gravity=(1.0, 0.0, 0.0), core=(), **ext):
    inputs = c.decode_guitar(guitar_ext(frets=frets, **ext))
    return c.Inputs(buttons=inputs.buttons | set(core), axes=inputs.axes, accel=gravity)


def tilted(degrees):
    """Gravity for a guitar whose neck is raised by this many degrees."""
    r = math.radians(degrees)
    return (math.cos(r), math.sin(r), 0.0)


class GuitarMappingTests(unittest.TestCase):
    def test_frets_follow_the_xbox_guitar_layout(self):
        state = GuitarMapper().map(guitar(frets=["green", "red", "yellow", "blue", "orange"]))
        self.assertEqual(state.buttons, {"A", "B", "Y", "X", "LB"})

    def test_strum_start_and_star_power_button(self):
        mapper = GuitarMapper()
        self.assertEqual(mapper.map(guitar(strum="up")).buttons, {"UP"})
        self.assertEqual(mapper.map(guitar(strum="down", plus=True)).buttons, {"DOWN", "START"})
        self.assertEqual(mapper.map(guitar(minus=True)).buttons, {"BACK"})

    def test_whammy_learns_its_range(self):
        mapper = GuitarMapper()
        self.assertEqual(mapper.map(guitar(whammy=0x10)).rx, -1.0)  # at rest
        self.assertEqual(mapper.map(guitar(whammy=0x14)).rx, 0.0)  # halfway of the default span
        self.assertEqual(mapper.map(guitar(whammy=0x1A)).rx, 1.0)  # new maximum
        self.assertEqual(mapper.map(guitar(whammy=0x15)).rx, 0.0)  # halfway of the learned range
        self.assertEqual(mapper.map(guitar(whammy=0x10)).rx, -1.0)

    def test_held_normally_is_not_tilted(self):
        mapper = GuitarMapper()
        for _ in range(20):
            state = mapper.map(guitar(gravity=tilted(10)))
        self.assertNotIn("BACK", state.buttons)
        self.assertLess(state.ry, -0.7)

    def test_neck_up_triggers_star_power(self):
        mapper = GuitarMapper()
        for _ in range(20):
            state = mapper.map(guitar(gravity=tilted(60)))
        self.assertIn("BACK", state.buttons)
        self.assertGreater(state.ry, 0.2)

    def test_tilt_ignores_which_way_the_remote_faces(self):
        mapper = GuitarMapper()
        for _ in range(20):
            state = mapper.map(guitar(gravity=(-0.5, -0.87, 0.0)))
        self.assertIn("BACK", state.buttons)

    def test_a_single_jolt_does_not_trigger_star_power(self):
        mapper = GuitarMapper()
        for _ in range(10):
            mapper.map(guitar(gravity=tilted(0)))
        state = mapper.map(guitar(gravity=tilted(80)))
        self.assertNotIn("BACK", state.buttons)

    def test_hysteresis_keeps_star_power_steady_near_the_threshold(self):
        mapper = GuitarMapper()
        for _ in range(20):
            mapper.map(guitar(gravity=tilted(50)))
        for _ in range(20):
            state = mapper.map(guitar(gravity=tilted(35)))  # just under the 40.5 degree threshold
        self.assertIn("BACK", state.buttons)
        for _ in range(20):
            state = mapper.map(guitar(gravity=tilted(20)))
        self.assertNotIn("BACK", state.buttons)

    def test_lying_flat_is_not_tilted(self):
        mapper = GuitarMapper()
        for _ in range(20):
            state = mapper.map(guitar(gravity=(0.05, 0.1, 1.0)))
        self.assertNotIn("BACK", state.buttons)

    def test_tilt_can_be_turned_off(self):
        mapper = GuitarMapper(Options(tilt=False))
        for _ in range(20):
            state = mapper.map(guitar(gravity=tilted(80)))
        self.assertNotIn("BACK", state.buttons)

    def test_recalibrate_with_one_and_two(self):
        messages = []
        mapper = GuitarMapper(log=messages.append)
        # This player holds the neck 30 degrees up as their normal pose...
        mapper.map(guitar(gravity=tilted(30), core=["wm_one"]))
        # ...and only manages 70 degrees when tilting.
        mapper.map(guitar(gravity=tilted(70)))
        mapper.map(guitar(gravity=tilted(70), core=["wm_two"]))
        self.assertAlmostEqual(math.degrees(mapper.tilt_neutral), 30, places=0)
        self.assertAlmostEqual(math.degrees(mapper.tilt_full), 70, places=0)
        self.assertEqual(len(messages), 2)
        for _ in range(20):
            state = mapper.map(guitar(gravity=tilted(30)))
        self.assertNotIn("BACK", state.buttons)
        for _ in range(20):
            state = mapper.map(guitar(gravity=tilted(55)))
        self.assertIn("BACK", state.buttons)

    def test_touch_strip_is_off_by_default(self):
        self.assertEqual(GuitarMapper().map(guitar(touch=0x04)).buttons, frozenset())

    def test_touch_strip_presses_frets_when_enabled(self):
        mapper = GuitarMapper(Options(touch_strip=True))
        self.assertEqual(mapper.map(guitar(touch=0x14)).buttons, {"Y", "X"})
        self.assertEqual(mapper.map(guitar(touch=0x0F)).buttons, frozenset())

    def test_touch_strip_is_ignored_on_gh3_guitars(self):
        mapper = GuitarMapper(Options(touch_strip=True))
        self.assertEqual(mapper.map(guitar(touch=0x04, gh3=True)).buttons, frozenset())


class OtherMappingTests(unittest.TestCase):
    def test_pro_controller(self):
        inputs = c.decode_pro(pro_report(buttons=["a", "zl", "zr", "home", "left"], lx=0xC00)[1:])
        state = ProMapper().map(inputs)
        self.assertEqual(state.buttons, {"A", "GUIDE", "LEFT"})
        self.assertEqual((state.lt, state.rt), (1.0, 1.0))
        self.assertEqual(state.lx, 1.0)

    def test_sideways_wiimote(self):
        state = WiimoteMapper().map(c.decode_wiimote(bytes([0x08, 0x01])))
        self.assertEqual(state.buttons, {"LEFT", "A"})

    def test_mapper_for(self):
        self.assertIsInstance(mapper_for(ExtensionType.GUITAR), GuitarMapper)
        self.assertIsInstance(mapper_for(ExtensionType.PRO_CONTROLLER), ProMapper)
        self.assertIsInstance(mapper_for(ExtensionType.NUNCHUK), WiimoteMapper)
        self.assertIsInstance(mapper_for(ExtensionType.NONE), WiimoteMapper)


if __name__ == "__main__":
    unittest.main()

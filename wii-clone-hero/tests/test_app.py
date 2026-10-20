import io
import unittest
from contextlib import redirect_stdout

from tests.fake_wiimote import GUITAR_ID, FakeWiimote, guitar_ext, guitar_report
from wiibridge.app import Bridge, Session, describe_inputs
from wiibridge.controllers import decode_guitar
from wiibridge.mapping import GuitarMapper, Options
from wiibridge.protocol import ExtensionType


class RecordingPad:
    def __init__(self):
        self.states = []
        self.closed = False

    def update(self, state):
        self.states.append(state)

    def close(self):
        self.closed = True


class BridgeTests(unittest.TestCase):
    def make_bridge(self, fakes, monitor=False):
        self.pads = []

        def make_pad():
            pad = RecordingPad()
            self.pads.append(pad)
            return pad

        return Bridge(Options(), monitor, make_pad, open_transport=lambda path: fakes[path])

    def test_guitar_session_drives_a_virtual_pad(self):
        fake = FakeWiimote(GUITAR_ID, hang_up_when_drained=True)
        fake.after_mode = [
            guitar_report(guitar_ext(frets=["green"])),
            guitar_report(guitar_ext(frets=["green"])),  # unchanged: no extra update
            guitar_report(guitar_ext(frets=["green"], strum="down")),
            guitar_report(guitar_ext()),
        ]
        bridge = self.make_bridge({"path": fake})
        Session(bridge, "path", 1).run()

        pad = self.pads[0]
        self.assertEqual([s.buttons for s in pad.states], [{"A"}, {"A", "DOWN"}, frozenset()])
        self.assertTrue(pad.closed)
        self.assertTrue(fake.closed)
        self.assertEqual(bridge.sessions, {})

    def test_monitor_mode_prints_instead_of_creating_a_pad(self):
        fake = FakeWiimote(GUITAR_ID, hang_up_when_drained=True)
        fake.after_mode = [guitar_report(guitar_ext(frets=["red"]))]
        bridge = self.make_bridge({"path": fake}, monitor=True)
        out = io.StringIO()
        with redirect_stdout(out):
            Session(bridge, "path", 1).run()
        self.assertEqual(self.pads, [])
        self.assertIn("red", out.getvalue())
        self.assertIn("Xbox: B", out.getvalue())

    def test_switched_off_controller_is_retried_later(self):
        fake = FakeWiimote(responsive=False)
        bridge = self.make_bridge({"path": fake})
        session = Session(bridge, "path", 1)
        session.run()
        self.assertEqual(self.pads, [])
        self.assertIn("path", bridge.retry_after)

    def test_scan_assigns_players_in_order(self):
        started = []
        bridge = self.make_bridge({})
        original_start = Session.start
        Session.start = lambda self: started.append(self)
        try:
            bridge.scan(lambda: [("a", "Wii"), ("b", "Wii")])
            bridge.scan(lambda: [("a", "Wii"), ("b", "Wii")])  # already running: ignored
        finally:
            Session.start = original_start
        self.assertEqual([(s.path, s.player) for s in started], [("a", 1), ("b", 2)])


class MonitorLineTests(unittest.TestCase):
    def test_guitar_line(self):
        inputs = decode_guitar(guitar_ext(frets=["green"], whammy=0x10))
        line = describe_inputs(ExtensionType.GUITAR, inputs, GuitarMapper().map(inputs))
        self.assertIn("green", line)
        self.assertIn("Xbox: A", line)
        self.assertIn("whammy   0%", line)


if __name__ == "__main__":
    unittest.main()

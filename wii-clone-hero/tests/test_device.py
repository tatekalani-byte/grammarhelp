import sys
import types
import unittest
from unittest import mock

from tests.fake_wiimote import (
    GUITAR_ID, NUNCHUK_ID, PRO_ID, FakeWiimote, guitar_ext, guitar_report, pro_report,
)
from wiibridge import protocol as p
from wiibridge.device import Disconnected, HidTransport, NotResponding, TransportError, WiiDevice


def connect(fake, player=1):
    device = WiiDevice(fake, player=player, clock=fake.clock)
    device.connect()
    return device


def next_inputs(device, tries=10):
    for _ in range(tries):
        inputs = device.poll(0.01)
        if inputs is not None:
            return inputs
    return None


class HandshakeTests(unittest.TestCase):
    def test_bare_wiimote(self):
        fake = FakeWiimote()
        device = connect(fake, player=2)
        self.assertIs(device.kind, p.ExtensionType.NONE)
        self.assertEqual(fake.mode, p.MODE_BUTTONS)
        self.assertEqual(fake.leds, 0x2)
        self.assertEqual(fake.ext_init, [])

    def test_guitar_is_initialised_and_identified(self):
        fake = FakeWiimote(GUITAR_ID)
        device = connect(fake)
        self.assertIs(device.kind, p.ExtensionType.GUITAR)
        self.assertEqual(fake.ext_init, [(0xA400F0, 0x55), (0xA400FB, 0x00)])
        self.assertEqual(fake.mode, p.MODE_BUTTONS_ACCEL_EXT16)
        self.assertEqual(device._calibration.zero, (512, 512, 512))

    def test_pro_controller(self):
        fake = FakeWiimote(PRO_ID)
        device = connect(fake)
        self.assertIs(device.kind, p.ExtensionType.PRO_CONTROLLER)
        self.assertEqual(fake.mode, p.MODE_EXT21)

    def test_unsupported_extension_falls_back_to_the_remote(self):
        fake = FakeWiimote(NUNCHUK_ID)
        device = connect(fake)
        self.assertIs(device.kind, p.ExtensionType.NUNCHUK)
        self.assertEqual(fake.mode, p.MODE_BUTTONS)

    def test_switched_off_controller(self):
        fake = FakeWiimote(responsive=False)
        with self.assertRaises(NotResponding):
            connect(fake)

    def test_rumbles_briefly_on_connect(self):
        fake = FakeWiimote()
        device = connect(fake)
        self.assertTrue(fake.rumble)
        fake.clock.now += 1
        device.poll(0.01)
        self.assertFalse(fake.rumble)
        self.assertEqual(fake.leds, 0x1)


class RunningTests(unittest.TestCase):
    def test_guitar_reports_are_decoded(self):
        fake = FakeWiimote(GUITAR_ID)
        device = connect(fake)
        fake.send(guitar_report(guitar_ext(frets=["green", "blue"], strum="down")))
        inputs = next_inputs(device)
        self.assertEqual(inputs.buttons, {"green", "blue", "strum_down"})
        self.assertIsNotNone(inputs.accel)

    def test_pro_reports_are_decoded(self):
        fake = FakeWiimote(PRO_ID)
        device = connect(fake)
        fake.send(pro_report(buttons=["b"]))
        self.assertEqual(next_inputs(device).buttons, {"b"})

    def test_status_report_restores_the_reporting_mode(self):
        fake = FakeWiimote(GUITAR_ID)
        device = connect(fake)
        fake.mode = p.MODE_BUTTONS  # what a real remote does after a status report
        fake.send(fake.status_report())
        device.poll(0.01)
        self.assertEqual(fake.mode, p.MODE_BUTTONS_ACCEL_EXT16)

    def test_plugging_in_a_guitar_later(self):
        fake = FakeWiimote()
        device = connect(fake)
        fake.plug(GUITAR_ID)
        device.poll(0.01)
        self.assertIs(device.kind, p.ExtensionType.GUITAR)
        self.assertEqual(fake.mode, p.MODE_BUTTONS_ACCEL_EXT16)

    def test_unplugging_the_guitar(self):
        fake = FakeWiimote(GUITAR_ID)
        device = connect(fake)
        fake.plug(None)
        device.poll(0.01)
        self.assertIs(device.kind, p.ExtensionType.NONE)
        self.assertEqual(fake.mode, p.MODE_BUTTONS)

    def test_silence_pings_then_gives_up(self):
        fake = FakeWiimote()
        device = connect(fake)
        fake.responsive = False
        with self.assertRaises(Disconnected):
            for _ in range(100):
                device.poll(0.1)
        self.assertIn(p.status_request(), fake.written[-5:])

    def test_quiet_but_alive_controller_stays_connected(self):
        fake = FakeWiimote()
        device = connect(fake)
        for _ in range(100):  # 10 seconds with only status replies to the pings
            device.poll(0.1)

    def test_close_turns_leds_off(self):
        fake = FakeWiimote()
        device = connect(fake)
        device.close()
        self.assertEqual(fake.leds, 0)
        self.assertTrue(fake.closed)



class FakeHidDevice:
    def __init__(self, open_error=None, write_result=22, read_result=(), read_error=None):
        self.open_error = open_error
        self.write_result = write_result
        self.read_result = list(read_result)
        self.read_error = read_error
        self.read_calls = []

    def open_path(self, path):
        if self.open_error:
            raise self.open_error

    def write(self, data):
        return self.write_result

    def read(self, max_length, timeout_ms):
        self.read_calls.append(timeout_ms)
        if self.read_error:
            raise self.read_error
        return self.read_result

    def close(self):
        pass


class HidTransportTests(unittest.TestCase):
    def transport(self, **kwargs):
        device = FakeHidDevice(**kwargs)
        backend = types.ModuleType("wiibridge.hidbackend")
        backend.hid = types.SimpleNamespace(device=lambda: device)
        with mock.patch.dict(sys.modules, {"wiibridge.hidbackend": backend}):
            return HidTransport(b"/dev/hidraw0"), device

    def test_reads_reports_as_bytes(self):
        transport, _ = self.transport(read_result=[0x20, 0, 0, 2, 0, 0, 200])
        self.assertEqual(transport.read(10), bytes([0x20, 0, 0, 2, 0, 0, 200]))

    def test_timeout_reads_as_none(self):
        transport, _ = self.transport(read_result=[])
        self.assertIsNone(transport.read(10))

    def test_zero_timeout_never_blocks_forever(self):
        transport, device = self.transport()
        transport.read(0)
        self.assertEqual(device.read_calls, [1])

    def test_errors_become_transport_errors(self):
        with self.assertRaises(TransportError):
            self.transport(open_error=OSError("open failed"))
        transport, _ = self.transport(write_result=-1)
        with self.assertRaises(TransportError):
            transport.write(b"\x15\x00")
        transport, _ = self.transport(read_error=OSError("read error"))
        with self.assertRaises(TransportError):
            transport.read(10)


if __name__ == "__main__":
    unittest.main()

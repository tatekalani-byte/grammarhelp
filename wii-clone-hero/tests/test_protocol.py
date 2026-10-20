import unittest

from wiibridge import protocol as p


class BuilderTests(unittest.TestCase):
    def test_leds_light_one_per_player(self):
        self.assertEqual(p.set_leds(1), bytes([0x11, 0x10]))
        self.assertEqual(p.set_leds(4), bytes([0x11, 0x80]))
        self.assertEqual(p.set_leds(0), bytes([0x11, 0x00]))

    def test_rumble_bit_rides_on_every_report(self):
        self.assertEqual(p.set_leds(2, rumble=True), bytes([0x11, 0x21]))
        self.assertEqual(p.status_request(rumble=True), bytes([0x15, 0x01]))
        self.assertEqual(p.set_report_mode(0x35, continuous=True, rumble=True), bytes([0x12, 0x05, 0x35]))

    def test_write_memory_pads_payload_to_16_bytes(self):
        report = p.write_memory(0xA400F0, b"\x55")
        self.assertEqual(report[:7], bytes([0x16, 0x04, 0xA4, 0x00, 0xF0, 0x01, 0x55]))
        self.assertEqual(len(report), 22)

    def test_read_memory(self):
        self.assertEqual(p.read_memory(0x0016, 10, space=p.MEMORY_EEPROM),
                         bytes([0x17, 0x00, 0x00, 0x00, 0x16, 0x00, 0x0A]))


class ParserTests(unittest.TestCase):
    def test_status(self):
        status = p.parse_status(bytes([0x20, 0, 0, 0x12, 0, 0, 0x64]))
        self.assertTrue(status.extension_connected)
        self.assertFalse(status.battery_low)
        self.assertEqual(status.battery_percent, 50)

    def test_read_reply(self):
        reply = p.parse_read_reply(bytes([0x21, 0, 0, 0x50, 0x00, 0xFA]) + bytes.fromhex("0000a4200103") + bytes(10))
        self.assertEqual(reply.error, 0)
        self.assertEqual(reply.address_low, 0x00FA)
        self.assertEqual(reply.data, bytes.fromhex("0000a4200103"))

    def test_extension_ids(self):
        self.assertIs(p.identify_extension(bytes.fromhex("0000a4200103")), p.ExtensionType.GUITAR)
        self.assertIs(p.identify_extension(bytes.fromhex("0100a4200103")), p.ExtensionType.DRUMS)
        self.assertIs(p.identify_extension(bytes.fromhex("0000a4200120")), p.ExtensionType.PRO_CONTROLLER)
        self.assertIs(p.identify_extension(bytes.fromhex("ffffffffffff")), p.ExtensionType.UNKNOWN)

    def test_split_data_report(self):
        report = bytes([0x35, 0xAA, 0xBB, 1, 2, 3]) + bytes(range(16))
        buttons, accel, ext = p.split_data_report(report)
        self.assertEqual(buttons, b"\xAA\xBB")
        self.assertEqual(accel, b"\x01\x02\x03")
        self.assertEqual(ext, bytes(range(16)))

        buttons, accel, ext = p.split_data_report(bytes([0x3D]) + bytes(21))
        self.assertIsNone(buttons)
        self.assertIsNone(accel)
        self.assertEqual(len(ext), 21)

    def test_short_report_yields_none(self):
        buttons, accel, ext = p.split_data_report(bytes([0x35, 0, 0, 0, 0, 0, 1, 2]))
        self.assertIsNone(ext)


if __name__ == "__main__":
    unittest.main()

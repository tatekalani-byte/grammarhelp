"""A pretend Wii Remote that answers the HID protocol the way real hardware does."""

from collections import deque

from wiibridge.device import TransportError

GUITAR_ID = bytes.fromhex("0000a4200103")
PRO_ID = bytes.fromhex("0000a4200120")
NUNCHUK_ID = bytes.fromhex("0000a4200000")

# Zero point 0x80 (512) and 1 g at 0x9A (616) on every axis.
ACCEL_CALIBRATION = bytes([0x80, 0x80, 0x80, 0x00, 0x9A, 0x9A, 0x9A, 0x00, 0x40, 0x00])


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class FakeWiimote:
    """Implements write(), read() and close() like HidTransport.

    read() advances the fake clock by its timeout when nothing is queued, so
    timeouts happen instantly in tests.
    """

    def __init__(self, extension_id=None, clock=None, responsive=True, hang_up_when_drained=False):
        self.extension_id = extension_id
        self.clock = clock or FakeClock()
        self.responsive = responsive
        # Raise TransportError (as if switched off) once the handshake is done
        # and every queued report has been read.
        self.hang_up_when_drained = hang_up_when_drained
        self.queue = deque()
        self.written = []
        self.mode = None
        self.leds = None
        self.rumble = False
        self.ext_init = []
        self.closed = False
        self.eeprom = {0x0016: ACCEL_CALIBRATION}
        # Reports to send once the PC picks a reporting mode, like a player
        # pressing buttons after the controller connects.
        self.after_mode = []

    # transport interface

    def write(self, data):
        data = bytes(data)
        self.written.append(data)
        if not self.responsive:
            return
        report = data[0]
        self.rumble = bool(data[1] & 0x01)
        if report == 0x11:
            self.leds = data[1] >> 4
        elif report == 0x12:
            self.mode = data[2]
            self.queue.extend(self.after_mode)
            self.after_mode = []
        elif report == 0x15:
            self.queue.append(self.status_report())
        elif report == 0x16:
            address = int.from_bytes(data[2:5], "big")
            self.ext_init.append((address, data[6]))
            error = 0 if self.extension_id is not None else 7
            self.queue.append(bytes([0x22, 0, 0, 0x16, error]))
        elif report == 0x17:
            space = data[1] & 0x0C
            address = int.from_bytes(data[2:5], "big")
            size = int.from_bytes(data[5:7], "big")
            if space == 0x00:
                payload = self.eeprom.get(address)
            elif address == 0xA400FA and self.extension_id is not None:
                payload = self.extension_id
            else:
                payload = None
            if payload is None:
                self.queue.append(bytes([0x21, 0, 0, 0xF8]) + address.to_bytes(3, "big")[1:] + bytes(16))
            else:
                payload = payload[:size]
                se = ((len(payload) - 1) << 4)
                self.queue.append(bytes([0x21, 0, 0, se]) + address.to_bytes(3, "big")[1:]
                                  + payload + bytes(16 - len(payload)))

    def read(self, timeout_ms):
        if self.queue:
            return self.queue.popleft()
        if self.hang_up_when_drained and self.mode is not None:
            raise TransportError("device switched off")
        self.clock.now += timeout_ms / 1000
        return None

    def close(self):
        self.closed = True

    # test helpers

    def status_report(self):
        flags = 0x02 if self.extension_id is not None else 0x00
        return bytes([0x20, 0, 0, flags, 0, 0, 0xC8])

    def plug(self, extension_id):
        """Plug in or (with None) pull out an extension; the remote sends a status report."""
        self.extension_id = extension_id
        self.ext_init.clear()
        self.queue.append(self.status_report())

    def send(self, report):
        self.queue.append(bytes(report))


def guitar_ext(frets=(), strum=None, plus=False, minus=False, whammy=0x10, touch=0x0F,
               stick=(32, 32), gh3=False):
    """Build the 6 extension bytes a guitar sends."""
    b4 = 0xFF
    b5 = 0xFF
    bits = {"green": 0x10, "red": 0x40, "yellow": 0x08, "blue": 0x20, "orange": 0x80}
    for fret in frets:
        b5 &= ~bits[fret]
    if strum == "up":
        b5 &= ~0x01
    elif strum == "down":
        b4 &= ~0x40
    if plus:
        b4 &= ~0x04
    if minus:
        b4 &= ~0x10
    sx = stick[0] | (0x80 if gh3 else 0)
    return bytes([sx & 0xFF, stick[1], touch, whammy, b4 & 0xFF, b5 & 0xFF])


def accel_bytes(gx, gy, gz):
    """8-bit accelerometer bytes for a gravity vector, matching ACCEL_CALIBRATION."""
    return bytes(max(0, min(255, round(0x80 + g * (0x9A - 0x80)))) for g in (gx, gy, gz))


def guitar_report(ext, gravity=(1.0, 0.0, 0.0), core=b"\x00\x00"):
    return bytes([0x35]) + core + accel_bytes(*gravity) + ext + bytes(10)


def pro_report(buttons=(), lx=0x800, ly=0x800, rx=0x800, ry=0x800):
    bits = {
        "right": (8, 0x80), "down": (8, 0x40), "l": (8, 0x20), "minus": (8, 0x10),
        "home": (8, 0x08), "plus": (8, 0x04), "r": (8, 0x02),
        "zl": (9, 0x80), "b": (9, 0x40), "y": (9, 0x20), "a": (9, 0x10), "x": (9, 0x08),
        "zr": (9, 0x04), "left": (9, 0x02), "up": (9, 0x01),
        "lstick": (10, 0x02), "rstick": (10, 0x01),
    }
    ext = bytearray(21)
    for i, value in enumerate((lx, rx, ly, ry)):
        ext[2 * i] = value & 0xFF
        ext[2 * i + 1] = value >> 8
    ext[8] = 0xFF
    ext[9] = 0xFF
    ext[10] = 0xFF
    for name in buttons:
        byte, mask = bits[name]
        ext[byte] &= ~mask
    return bytes([0x3D]) + bytes(ext)

"""Command line entry point and the loop that watches for controllers."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
import time

from .device import Disconnected, HidTransport, NotResponding, TransportError, WiiDevice, describe
from .mapping import Options, PadState, mapper_for
from .protocol import ExtensionType

log = logging.getLogger("wiibridge")

SCAN_INTERVAL = 2.0
RETRY_AFTER_FAILURE = 5.0
MAX_PLAYERS = 7


class Session(threading.Thread):
    """Runs one controller: handshake, then forward its inputs until it disconnects."""

    def __init__(self, bridge, path, player):
        super().__init__(daemon=True, name=f"player-{player}")
        self.bridge = bridge
        self.path = path
        self.player = player
        self.connected = False
        self.stop_event = threading.Event()

    def run(self):
        try:
            self._run()
        except Exception:
            log.exception("Player %d: unexpected error", self.player)
        finally:
            self.bridge.session_ended(self)

    def _run(self):
        try:
            transport = self.bridge.open_transport(self.path)
        except TransportError as exc:
            self.bridge.open_failed(self.path, exc)
            return
        device = WiiDevice(transport, self.player)
        try:
            device.connect()
        except (NotResponding, TransportError) as exc:
            # Typically a controller that is paired but switched off.
            log.debug("%r did not answer: %s", self.path, exc)
            device.close()
            return

        self.connected = True
        battery = ""
        if device.status and device.kind is not ExtensionType.PRO_CONTROLLER:
            battery = f", battery {device.status.battery_percent}%"
        log.info("Player %d connected: %s%s", self.player, describe(device.kind), battery)
        if device.kind is ExtensionType.GUITAR:
            log.info("Player %d: push the whammy bar all the way down once to calibrate it.", self.player)

        pad = None
        try:
            if not self.bridge.monitor:
                pad = self.bridge.make_pad()
            self._forward(device, pad)
        except (Disconnected, TransportError):
            log.info("Player %d disconnected.", self.player)
        finally:
            if pad is not None:
                pad.close()
            device.close()

    def _forward(self, device, pad):
        kind = None
        mapper = None
        last_state = None
        last_line = None
        while not self.stop_event.is_set():
            inputs = device.poll(0.1)
            if device.kind is not kind:
                kind = device.kind
                mapper = mapper_for(kind, self.bridge.options,
                                    log=lambda message: log.info("Player %d: %s", self.player, message))
                last_state = None
            if inputs is None:
                continue
            state = mapper.map(inputs)
            if pad is not None:
                if state != last_state:
                    pad.update(state)
                    last_state = state
            else:
                line = describe_inputs(kind, inputs, state)
                if line != last_line:
                    print(f"[P{self.player}] {line}", flush=True)
                    last_line = line

    def stop(self):
        self.stop_event.set()


def describe_inputs(kind, inputs, state: PadState) -> str:
    """One line for monitor mode: what was pressed and what Clone Hero will see."""
    pressed = ", ".join(sorted(inputs.buttons)) or "-"
    sent = ", ".join(sorted(state.buttons)) or "-"
    line = f"{pressed:<40} -> Xbox: {sent}"
    if kind is ExtensionType.GUITAR:
        whammy = (state.rx + 1) / 2
        tilt = (state.ry + 1) / 2
        line += f" | whammy {round(whammy * 10) * 10:3d}% tilt {round(tilt * 10) * 10:3d}%"
    sticks = [(n, v) for n, v in (("LX", state.lx), ("LY", state.ly)) if v]
    if kind is ExtensionType.PRO_CONTROLLER:
        sticks += [(n, v) for n, v in (("RX", state.rx), ("RY", state.ry)) if v]
    if sticks:
        line += " | " + " ".join(f"{n} {v:+.1f}" for n, v in sticks)
    return line


class Bridge:
    def __init__(self, options: Options, monitor: bool, make_pad=None, open_transport=HidTransport):
        self.options = options
        self.monitor = monitor
        self.make_pad = make_pad
        self.open_transport = open_transport
        self.sessions = {}
        self.retry_after = {}
        self.open_warnings = set()
        self.lock = threading.Lock()

    def session_ended(self, session):
        with self.lock:
            self.sessions.pop(session.path, None)
            delay = 0 if session.connected else RETRY_AFTER_FAILURE
            self.retry_after[session.path] = time.monotonic() + delay

    def open_failed(self, path, exc):
        if path in self.open_warnings:
            return
        self.open_warnings.add(path)
        hint = ""
        if sys.platform.startswith("linux"):
            hint = " Check the hidraw permissions (see the Linux section of README.md)."
        log.warning("Found a controller but could not open it: %s.%s", exc, hint)

    def _free_player(self):
        used = {s.player for s in self.sessions.values()}
        return next(n for n in range(1, MAX_PLAYERS + 1) if n not in used)

    def scan(self, enumerate_controllers):
        now = time.monotonic()
        for path, _name in enumerate_controllers():
            with self.lock:
                if path in self.sessions or self.retry_after.get(path, 0) > now:
                    continue
                if len(self.sessions) >= MAX_PLAYERS:
                    return
                session = Session(self, path, self._free_player())
                self.sessions[path] = session
            session.start()

    def run(self):
        from .hidbackend import enumerate_wii_controllers

        try:
            while True:
                self.scan(enumerate_wii_controllers)
                time.sleep(SCAN_INTERVAL)
        finally:
            with self.lock:
                sessions = list(self.sessions.values())
            for session in sessions:
                session.stop()
            for session in sessions:
                session.join(timeout=2)


def warn_about_linux_driver():
    driver = "/sys/bus/hid/drivers/wiimote"
    if not os.path.isdir(driver):
        return
    log.warning(
        "The Linux 'hid-wiimote' driver is loaded and will fight with this program over the\n"
        "controllers. Unload it with:   sudo modprobe -r hid_wiimote\n"
        "(see README.md for how to keep it from loading again).")


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="wiibridge",
        description="Use Wii guitars, Wii Remotes and Wii U Pro Controllers as Xbox 360 "
                    "controllers in Clone Hero.")
    parser.add_argument("command", nargs="?", default="run",
                        choices=["run", "monitor", "pair", "forget"],
                        help="run: start the bridge (default). monitor: print button presses "
                             "without creating virtual controllers. pair: pair controllers with "
                             "Windows. forget: unpair all Wii controllers from Windows.")
    parser.add_argument("--tilt-threshold", type=float, default=Options.tilt_threshold,
                        metavar="0-1", help="how far the neck must tilt up for star power, from 0 "
                        "(held normally) to 1 (straight up). Default %(default)s.")
    parser.add_argument("--no-tilt", action="store_true", help="turn off tilt for star power")
    parser.add_argument("--touch-strip", action="store_true",
                        help="let the touch strip on World Tour-era guitars press frets")
    parser.add_argument("--seconds", type=float, default=60, help="how long 'pair' scans (default 60)")
    parser.add_argument("--debug", action="store_true", help="print protocol details")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO,
                        format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")

    if args.command in ("pair", "forget"):
        if sys.platform != "win32":
            print("Pairing from this program is only for Windows. On Linux use bluetoothctl;"
                  " see README.md.")
            return 1
        from . import pairing_windows

        try:
            if args.command == "pair":
                pairing_windows.pair(args.seconds)
            else:
                pairing_windows.forget()
        except KeyboardInterrupt:
            print("Stopped.")
        return 0

    if not 0 < args.tilt_threshold < 1:
        parser.error("--tilt-threshold must be between 0 and 1")
    options = Options(tilt=not args.no_tilt, tilt_threshold=args.tilt_threshold,
                      touch_strip=args.touch_strip)
    monitor = args.command == "monitor"

    make_pad = None
    if not monitor:
        from .vpad import SetupError, create_pad

        try:
            create_pad().close()  # fail now, not when the first controller connects
        except SetupError as exc:
            print(exc)
            return 1
        make_pad = create_pad

    if sys.platform.startswith("linux"):
        warn_about_linux_driver()

    print("Wii -> Clone Hero bridge running. Press Ctrl+C to quit.")
    if monitor:
        print("Monitor mode: showing button presses only, no virtual controllers.")
    print("Waiting for controllers. Press a button on each paired controller to connect it.")
    print("(Not paired yet? Quit and run 'pair' first.)")
    try:
        Bridge(options, monitor, make_pad).run()
    except KeyboardInterrupt:
        print("\nBye.")
    return 0

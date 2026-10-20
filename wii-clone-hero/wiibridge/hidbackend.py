"""Import the right hidapi module for this platform.

The `hidapi` package ships two modules on Linux: `hid` (libusb, USB only) and
`hidraw` (kernel hidraw, which also covers Bluetooth). Wii controllers are
Bluetooth devices, so Linux needs `hidraw`. Windows and macOS only have `hid`.
"""

import sys

try:
    if sys.platform.startswith("linux"):
        import hidraw as hid
    else:
        import hid
except ImportError as exc:
    raise SystemExit(
        "The 'hidapi' Python package is missing. Install it with:\n"
        "    python -m pip install hidapi"
    ) from exc

if not hasattr(hid, "device"):
    raise SystemExit(
        "A different package called 'hid' is installed and hides 'hidapi'. Fix it with:\n"
        "    python -m pip uninstall hid\n"
        "    python -m pip install --force-reinstall hidapi"
    )


def enumerate_wii_controllers():
    """Return [(path, product_name)] for every Wii Remote / Pro Controller the OS sees."""
    from .protocol import NINTENDO_VID, WIIMOTE_PIDS

    found = []
    for pid in WIIMOTE_PIDS:
        for info in hid.enumerate(NINTENDO_VID, pid):
            found.append((info["path"], info.get("product_string") or "Nintendo controller"))
    return found

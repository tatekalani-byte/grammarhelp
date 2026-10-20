"""Pair Wii Remotes, Wii guitars and Wii U Pro Controllers with Windows.

Windows' own "Add a device" dialog often fails with Nintendo controllers
because they want an unusual PIN: the PC's Bluetooth address as six raw bytes
(when you press the red SYNC button) or the controller's own address (when
you press 1+2). This module sends that PIN through the Win32 Bluetooth API,
then switches on the HID service, which is the same thing Dolphin and
WiitarThing do.

Pairing with SYNC is permanent: afterwards the controller reconnects when you
press a button.
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

NINTENDO_NAME_PREFIX = "Nintendo RVL-CNT-01"
BLUETOOTH_MAX_NAME_SIZE = 248
BLUETOOTH_SERVICE_ENABLE = 0x01

FRIENDLY_NAMES = {
    "Nintendo RVL-CNT-01": "Wii Remote",
    "Nintendo RVL-CNT-01-TR": "Wii Remote Plus",
    "Nintendo RVL-CNT-01-UC": "Wii U Pro Controller",
}


class BLUETOOTH_ADDRESS(ctypes.Union):
    _fields_ = [("ullLong", ctypes.c_ulonglong), ("rgBytes", ctypes.c_ubyte * 6)]


class SYSTEMTIME(ctypes.Structure):
    _fields_ = [(name, wintypes.WORD) for name in (
        "wYear", "wMonth", "wDayOfWeek", "wDay", "wHour", "wMinute", "wSecond", "wMilliseconds")]


class BLUETOOTH_DEVICE_INFO(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("Address", BLUETOOTH_ADDRESS),
        ("ulClassofDevice", wintypes.ULONG),
        ("fConnected", wintypes.BOOL),
        ("fRemembered", wintypes.BOOL),
        ("fAuthenticated", wintypes.BOOL),
        ("stLastSeen", SYSTEMTIME),
        ("stLastUsed", SYSTEMTIME),
        ("szName", wintypes.WCHAR * BLUETOOTH_MAX_NAME_SIZE),
    ]


class BLUETOOTH_RADIO_INFO(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("address", BLUETOOTH_ADDRESS),
        ("szName", wintypes.WCHAR * BLUETOOTH_MAX_NAME_SIZE),
        ("ulClassofDevice", wintypes.ULONG),
        ("lmpSubversion", wintypes.USHORT),
        ("manufacturer", wintypes.USHORT),
    ]


class BLUETOOTH_DEVICE_SEARCH_PARAMS(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("fReturnAuthenticated", wintypes.BOOL),
        ("fReturnRemembered", wintypes.BOOL),
        ("fReturnUnknown", wintypes.BOOL),
        ("fReturnConnected", wintypes.BOOL),
        ("fIssueInquiry", wintypes.BOOL),
        ("cTimeoutMultiplier", ctypes.c_ubyte),
        ("hRadio", wintypes.HANDLE),
    ]


class BLUETOOTH_FIND_RADIO_PARAMS(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD)]


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


# {00001124-0000-1000-8000-00805F9B34FB}
HID_SERVICE_CLASS = GUID(0x00001124, 0x0000, 0x1000,
                         (ctypes.c_ubyte * 8)(0x80, 0x00, 0x00, 0x80, 0x5F, 0x9B, 0x34, 0xFB))


def _load_api():
    try:
        bt = ctypes.WinDLL("bthprops.cpl")
    except OSError:
        bt = ctypes.WinDLL("BluetoothApis.dll")
    P = ctypes.POINTER
    H = wintypes.HANDLE
    signatures = {
        "BluetoothFindFirstRadio": (H, [P(BLUETOOTH_FIND_RADIO_PARAMS), P(H)]),
        "BluetoothFindNextRadio": (wintypes.BOOL, [H, P(H)]),
        "BluetoothFindRadioClose": (wintypes.BOOL, [H]),
        "BluetoothGetRadioInfo": (wintypes.DWORD, [H, P(BLUETOOTH_RADIO_INFO)]),
        "BluetoothFindFirstDevice": (H, [P(BLUETOOTH_DEVICE_SEARCH_PARAMS), P(BLUETOOTH_DEVICE_INFO)]),
        "BluetoothFindNextDevice": (wintypes.BOOL, [H, P(BLUETOOTH_DEVICE_INFO)]),
        "BluetoothFindDeviceClose": (wintypes.BOOL, [H]),
        "BluetoothAuthenticateDevice": (
            wintypes.DWORD, [wintypes.HWND, H, P(BLUETOOTH_DEVICE_INFO), P(wintypes.WCHAR), wintypes.ULONG]),
        "BluetoothEnumerateInstalledServices": (
            wintypes.DWORD, [H, P(BLUETOOTH_DEVICE_INFO), P(wintypes.DWORD), P(GUID)]),
        "BluetoothSetServiceState": (
            wintypes.DWORD, [H, P(BLUETOOTH_DEVICE_INFO), P(GUID), wintypes.DWORD]),
        "BluetoothRemoveDevice": (wintypes.DWORD, [P(BLUETOOTH_ADDRESS)]),
    }
    for name, (restype, argtypes) in signatures.items():
        function = getattr(bt, name)
        function.restype = restype
        function.argtypes = argtypes
    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.CloseHandle.argtypes = [H]
    kernel32.CloseHandle.restype = wintypes.BOOL
    return bt, kernel32


def format_address(address: BLUETOOTH_ADDRESS) -> str:
    return ":".join(f"{b:02X}" for b in reversed(bytes(address.rgBytes)))


def pin_from_address(address: BLUETOOTH_ADDRESS):
    """The Wii PIN is the six address bytes, least significant first, as UTF-16 code units."""
    pin = (wintypes.WCHAR * 6)()
    for i, byte in enumerate(bytes(address.rgBytes)):
        pin[i] = chr(byte)
    return pin


def _radios(bt, kernel32):
    params = BLUETOOTH_FIND_RADIO_PARAMS(ctypes.sizeof(BLUETOOTH_FIND_RADIO_PARAMS))
    radio = wintypes.HANDLE()
    find = bt.BluetoothFindFirstRadio(ctypes.byref(params), ctypes.byref(radio))
    if not find:
        return
    try:
        while True:
            info = BLUETOOTH_RADIO_INFO()
            info.dwSize = ctypes.sizeof(BLUETOOTH_RADIO_INFO)
            try:
                if bt.BluetoothGetRadioInfo(radio, ctypes.byref(info)) == 0:
                    yield radio, info
            finally:
                kernel32.CloseHandle(radio)
            radio = wintypes.HANDLE()
            if not bt.BluetoothFindNextRadio(find, ctypes.byref(radio)):
                break
    finally:
        bt.BluetoothFindRadioClose(find)


def _devices(bt, radio, inquiry: bool):
    params = BLUETOOTH_DEVICE_SEARCH_PARAMS()
    params.dwSize = ctypes.sizeof(BLUETOOTH_DEVICE_SEARCH_PARAMS)
    params.fReturnAuthenticated = True
    params.fReturnRemembered = True
    params.fReturnUnknown = True
    params.fReturnConnected = True
    params.fIssueInquiry = inquiry
    params.cTimeoutMultiplier = 2  # x 1.28 s
    params.hRadio = radio
    info = BLUETOOTH_DEVICE_INFO()
    info.dwSize = ctypes.sizeof(BLUETOOTH_DEVICE_INFO)
    find = bt.BluetoothFindFirstDevice(ctypes.byref(params), ctypes.byref(info))
    if not find:
        return []
    found = []
    try:
        while True:
            found.append(BLUETOOTH_DEVICE_INFO.from_buffer_copy(info))
            info = BLUETOOTH_DEVICE_INFO()
            info.dwSize = ctypes.sizeof(BLUETOOTH_DEVICE_INFO)
            if not bt.BluetoothFindNextDevice(find, ctypes.byref(info)):
                break
    finally:
        bt.BluetoothFindDeviceClose(find)
    return found


def _is_nintendo(device: BLUETOOTH_DEVICE_INFO) -> bool:
    return device.szName.startswith(NINTENDO_NAME_PREFIX)


def _friendly(device: BLUETOOTH_DEVICE_INFO) -> str:
    name = FRIENDLY_NAMES.get(device.szName, device.szName)
    return f"{name} ({format_address(device.Address)})"


ERROR_ACCESS_DENIED = 5


def _explain(error: int) -> str:
    if error == ERROR_ACCESS_DENIED:
        return " (access denied: right-click wiibridge.bat and choose 'Run as administrator')"
    return ""


def _pair(bt, radio, radio_info, device, log) -> bool:
    # PIN for the red SYNC button first, then for 1+2.
    for pin_source, how in ((radio_info.address, "SYNC button"), (device.Address, "1+2")):
        error = bt.BluetoothAuthenticateDevice(None, radio, ctypes.byref(device),
                                               pin_from_address(pin_source), 6)
        if error == 0:
            log(f"  authenticated using the {how} PIN")
            break
    else:
        log(f"  could not authenticate (error {error}){_explain(error)}; "
            "press SYNC again and keep it blinking")
        return False

    # Windows only remembers the pairing after it has listed the services.
    count = wintypes.DWORD(16)
    services = (GUID * 16)()
    bt.BluetoothEnumerateInstalledServices(radio, ctypes.byref(device), ctypes.byref(count), services)

    error = bt.BluetoothSetServiceState(radio, ctypes.byref(device), ctypes.byref(HID_SERVICE_CLASS),
                                        BLUETOOTH_SERVICE_ENABLE)
    if error != 0:
        log(f"  paired, but enabling the controller driver failed (error {error}){_explain(error)}")
        return False
    return True


def pair(seconds: float = 60, log=print) -> int:
    """Scan for Nintendo controllers in sync mode and pair them. Returns how many were paired."""
    bt, kernel32 = _load_api()
    if not any(True for _ in _radios(bt, kernel32)):
        log("No Bluetooth adapter found. Is Bluetooth switched on?")
        return 0

    log("Press the red SYNC button on each controller now (Wii Remote: under the battery")
    log("cover; Wii U Pro Controller: on the back). For a guitar, sync the Wii Remote that")
    log("sits inside it. Keep pressing SYNC whenever the lights stop blinking.")
    log(f"Scanning for {int(seconds)} seconds. Press Ctrl+C to stop early.")
    paired = 0
    hinted = set()
    handled = set()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        for radio, radio_info in _radios(bt, kernel32):
            for device in _devices(bt, radio, inquiry=True):
                address = device.Address.ullLong
                if not _is_nintendo(device) or address in handled:
                    continue
                if device.fConnected:
                    handled.add(address)
                    log(f"{_friendly(device)} is already connected.")
                    continue
                if device.fRemembered:
                    if address not in hinted:
                        hinted.add(address)
                        log(f"{_friendly(device)} is already paired but not connected. Press a "
                            "button on it to reconnect. If it won't, run 'forget' and pair again.")
                    continue
                log(f"Found {_friendly(device)}, pairing...")
                if _pair(bt, radio, radio_info, device, log):
                    handled.add(address)
                    paired += 1
                    log(f"Paired {_friendly(device)}.")
    log(f"Done. Paired {paired} controller(s).")
    return paired


def forget(log=print) -> int:
    """Remove every remembered Nintendo controller from Windows' Bluetooth list."""
    bt, kernel32 = _load_api()
    removed = 0
    for radio, _ in _radios(bt, kernel32):
        for device in _devices(bt, radio, inquiry=False):
            if _is_nintendo(device) and (device.fRemembered or device.fConnected):
                error = bt.BluetoothRemoveDevice(ctypes.byref(device.Address))
                if error == 0:
                    removed += 1
                    log(f"Removed {_friendly(device)}")
                else:
                    log(f"Could not remove {_friendly(device)} (error {error}){_explain(error)}")
    log(f"Removed {removed} controller(s).")
    return removed

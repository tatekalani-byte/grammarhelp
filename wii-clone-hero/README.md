# Wii → Clone Hero bridge

Connects Wii Guitar Hero guitars, Wii Remotes and Wii U Pro Controllers to a PC
over Bluetooth and turns each one into a virtual **Xbox 360 controller** that
Clone Hero (or any other game) can use.

| Controller | What Clone Hero sees |
|---|---|
| **Guitar Hero guitar** (the Wii kind with a Wii Remote inside: GH3, World Tour, GH5, Warriors of Rock, Band Hero) | Frets, strum bar, whammy, **tilt for star power**, +/- buttons, laid out like an Xbox 360 guitar |
| **Wii U Pro Controller** | A normal gamepad: sticks, all buttons, ZL/ZR as triggers |
| **Wii Remote / Wii Remote Plus** on its own | A gamepad held sideways (D-pad on the left, 1 and 2 on the right) |

Up to 7 controllers at once. Each one rumbles and lights its player LED when it
connects. Windows and Linux are supported.

**Not supported:** the Wii U **GamePad** (the one with the screen doesn't use
Bluetooth), **Guitar Hero Live** guitars (those use a USB dongle, not
Bluetooth), and Guitar Hero drums / DJ Hero turntables plugged into a Wii
Remote (the Wii Remote's own buttons still work).

---

## Windows setup

You need a PC with Bluetooth (built in, or a USB Bluetooth adapter) and
Python 3.10 to 3.14. One of the parts it uses has no
ready-made package for Python 3.15 yet; if that's your default, `wiibridge.bat`
installs Python 3.14 next to it on the first run.

1. **Install Python** from <https://www.python.org/downloads/>. The download
   is the *Python install manager*, which opens a terminal window and asks a
   few questions. Type the letter and press Enter:
   - *Install CPython now?* **y** (this is the one that matters)
   - *Add commands directory to your PATH now?* **y**
   - *Update setting now?* (long paths) **n** is fine
   - *Open Settings now… App execution aliases?* **y**, then switch on
     *Python (default)* and *Python install manager*

   When it says *Configuration checks completed*, close it. (If you used
   the older `.exe` installer instead, tick **"Add python.exe to PATH"**.)
2. **Double-click `wiibridge.bat`.** The first time, it installs what it needs.
   This includes the **ViGEmBus** driver, which creates the virtual Xbox
   controllers: when its installer pops up, accept the licence and click
   *Install*. If Windows asks you to reboot, reboot and double-click
   `wiibridge.bat` again.
3. **Pair each controller (one time only).** Choose **1. Pair controllers**,
   then press the red **SYNC** button:
   - Wii Remote: under the battery cover.
   - Guitar: on the Wii Remote that sits inside the guitar. Take the Wii
     Remote's battery cover off if needed.
   - Wii U Pro Controller: the small button on the back, next to the
     charging port.

   The lights blink while it waits. Keep pressing SYNC whenever they stop
   blinking until the program says **Paired**. Pair as many as you like, then
   wait for the scan to finish or press Ctrl+C.

   If pairing fails with "access denied", right-click `wiibridge.bat`,
   choose **Run as administrator**, and try again.
4. **Start the bridge.** Double-click `wiibridge.bat` and choose
   **2. Start the bridge**. Press any button on each controller to connect it.
   You should see `Player 1 connected: Guitar Hero guitar` and feel a short
   rumble. **Leave this window open while you play.**
5. **Push the whammy bar all the way down once** after each guitar connects.
   The program learns the whammy's range from that.

Next time, just do steps 4 and 5. Paired controllers reconnect when you press
a button.

Want to check that everything works before opening Clone Hero? Choose
**3. Test controllers**. It prints every button press and what it turns into.

### Already tried pairing through Windows Settings?

Windows' own *Add a device* dialog often half-pairs Wii controllers so they
show as "Paired" but never connect. Choose **4. Forget all paired Wii
controllers**, then pair again with option 1.

---

## Setting up Clone Hero

1. Start the bridge and connect your guitar **before** opening Clone Hero.
2. In Clone Hero, open the controller settings, choose the new **Xbox 360
   controller**, set its type to **Guitar**, and bind each action by pressing
   the matching fret or button on the guitar when asked:

| Clone Hero action | Press on the guitar | Sent as |
|---|---|---|
| Green / Red / Yellow / Blue / Orange | that fret | A / B / Y / X / LB |
| Strum up / Strum down | strum bar | D-pad up / down |
| Whammy | push the whammy bar | right stick X |
| Star power | **tilt the neck up**, or press **–** | Back button (and right stick Y for tilt) |
| Start / pause | **+** | Start |

The layout matches a real Xbox 360 Guitar Hero guitar, so guides for those
guitars apply too.

### Tilt (star power)

Tilting the neck past about 40° upward triggers star power. If it triggers too
easily or not at all:

- **Recalibrate while playing:** hold the guitar the way you normally play and
  press **1** on the Wii Remote inside the guitar; then point the neck as far
  up as you'd tilt for star power and press **2**. Star power then triggers
  about halfway between those two.
- **Or change the angle** for every guitar:
  `wiibridge.bat run --tilt-threshold 0.6` (0 is level, 1 is straight up;
  the default is 0.45).
- **Or turn tilt off** with `wiibridge.bat run --no-tilt` and use the –
  button.

### Touch strip

World Tour-era guitars have a touch strip on the neck. It's off by default
because Guitar Hero 3 guitars report garbage there. To let it press frets:
`wiibridge.bat run --touch-strip`.

---

## Downloading the songs

`songs/setlist.json` lists the 421 songs from the Spotify playlist
"This is what I sound like" that have a guitar chart on
[Chorus Encore](https://www.enchor.us), checked on October 21, 2026.

Double-click **`download-songs.bat`** to download them all in one go. It saves
each chart as one `.sng` file in `Documents\Clone Hero\Songs\This is what I sound like`
(it asks for the Songs folder if yours is somewhere else), skips songs that are
already there, and can be stopped with Ctrl+C and run again later to carry on.
Expect a few gigabytes in total. When it finishes, rescan your songs in Clone
Hero's settings.

---

## Linux setup

Linux works too, using the kernel's Bluetooth stack.

```sh
cd wii-clone-hero
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt   # evdev builds from source: needs gcc and python3-dev

# Allow access without sudo (one time)
sudo cp linux/70-wii-clone-hero.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger

# Stop the kernel's own Wii driver from grabbing the controllers (one time)
sudo cp linux/blacklist-hid-wiimote.conf /etc/modprobe.d/
sudo modprobe -r hid_wiimote
```

Pair each controller with `bluetoothctl` (BlueZ handles the Wii PIN itself):

```sh
bluetoothctl
  scan on          # now press SYNC on the controller
  pair XX:XX:XX:XX:XX:XX
  trust XX:XX:XX:XX:XX:XX
  connect XX:XX:XX:XX:XX:XX
```

Then run the bridge: `.venv/bin/python -m wiibridge` (or
`.venv/bin/python -m wiibridge monitor` to test).

---

## Troubleshooting

| Problem | Fix |
|---|---|
| "ViGEmBus is probably not installed" | Install it from <https://github.com/nefarius/ViGEmBus/releases>, reboot. |
| Controller pairs but never says "connected" | Press a button on it. If nothing happens: option 4 (Forget), then pair again with SYNC. |
| Strum or frets stop working mid-song, inputs lag | Bluetooth congestion. Move closer to the PC or the Bluetooth adapter, use fewer Bluetooth devices at once, and avoid a USB 3 port right next to a Bluetooth dongle. |
| Clone Hero doesn't see the controller | Start the bridge and connect the guitar *before* starting Clone Hero. |
| Two programs fighting over the controller | Close Dolphin, WiitarThing, DS4Windows or similar tools while using this. |
| Third-party / knock-off Wii Remotes | Some don't follow the protocol properly. Genuine Nintendo remotes work best. |

Run `wiibridge.bat run --debug` for detailed logs.

---

## How it works

- `wiibridge/protocol.py`: the Wii Remote's Bluetooth HID reports.
- `wiibridge/device.py`: handshake (status, extension detection, report mode)
  and the read loop, including hot-plugging a guitar into a Wii Remote.
- `wiibridge/controllers.py`: decodes guitar, Pro Controller and Wii Remote
  data.
- `wiibridge/mapping.py`: Xbox 360 layout, whammy calibration and tilt.
- `wiibridge/vpad.py`: virtual controllers (ViGEmBus on Windows, uinput on
  Linux).
- `wiibridge/pairing_windows.py`: Windows pairing with the Wii PIN, like
  Dolphin and WiitarThing do it.

Tests run against a simulated Wii Remote that answers the protocol like real
hardware: `python -m unittest discover -s tests -t .`

The protocol details come from [WiiBrew](https://wiibrew.org/wiki/Wiimote),
the Linux `hid-wiimote` driver and
[WiitarThing](https://github.com/shockdude/WiitarThing). WiitarThing is the
long-standing Windows tool for Wii guitars in Clone Hero; if this program
gives you trouble on your hardware, it's a good fallback.

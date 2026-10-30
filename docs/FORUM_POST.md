# Speed Editor over Bluetooth on Linux — the complete fix

**TL;DR:** DaVinci Resolve on Linux *does* work with the Speed Editor over
Bluetooth, but it takes **three** independent fixes: (1) a udev rule,
(2) the BlueZ GET_REPORT fix (upstream, expected in 5.88) and
(3) a 3-byte patch in the Resolve binary, whose Bluetooth checks were
written against the *buggy* BlueZ behavior. A small optional daemon covers
the panel's 600-second authentication. Everything is on GitHub:
`<repo link>`.

---

## Environment

- DaVinci Resolve Studio 19.1.x
- Arch Linux, kernel 7.2.x, BlueZ 5.87 (patched)
- Speed Editor over Bluetooth LE; Resolve inside a distrobox container

## Symptom

The panel pairs and shows battery, but inside Resolve nothing happens: LEDs
never light, buttons and jog do nothing. Over USB the same panel works.
(Depending on which fix you apply first, you may instead see Resolve stall —
see root cause 3.)

## Root cause 1 — permissions

Over Bluetooth the Speed Editor is HID-over-GATT. BlueZ exposes it via
`uhid`, and the kernel shows it as `hidraw`:

```
$ cat /sys/class/hidraw/hidraw3/device/uevent
HID_ID=0005:00001EDB:0000DA0E     # bus 0005 = Bluetooth
```

The device lives at `/sys/devices/virtual/misc/uhid/0005:1EDB:DA0E.*/...` and
has **no `idVendor`/`idProduct`** attributes, so Blackmagic's udev rules
(`ATTRS{idVendor}=="1edb"`) never match. The node stays `0600 root:root` and
Resolve can't open it — silently.

**Fix** — `/etc/udev/rules.d/99-blackmagic-hidraw.rules`:

```
# USB
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="1edb", ATTRS{idProduct}=="da0e", MODE="0660", GROUP="input", TAG+="uaccess"
# Bluetooth (HID-over-GATT via uhid; no idVendor). Match the kernel device name:
SUBSYSTEM=="hidraw", KERNELS=="*:1EDB:DA0E.*", MODE="0660", GROUP="input", TAG+="uaccess"
# Same family, untested:
SUBSYSTEM=="hidraw", KERNELS=="*:1EDB:DA11.*", MODE="0660", GROUP="input", TAG+="uaccess"
SUBSYSTEM=="hidraw", KERNELS=="*:1EDB:BEF0.*", MODE="0660", GROUP="input", TAG+="uaccess"
```

```
sudo udevadm control --reload-rules && sudo udevadm trigger --subsystem-match=hidraw
```

## Root cause 2 — authentication expires every 600 s

The panel reports input only after the mutual authentication on feature
report `0x06` (documented in
[smunaut/blackmagic-misc](https://github.com/smunaut/blackmagic-misc)). The
handshake returns a timeout — `0x0258` = **600 s** — after which the panel
goes quiet again. Resolve renews it over USB; over Bluetooth on Linux it
relies on the same feature-report reads, which brings us to…

## Root cause 3 — the BlueZ GET_REPORT truncation (the "lag")

`bt_uhid_get_report_reply` (`src/shared/uhid.c`) computed the reply size
without the Report ID byte, so the **last byte of every numbered report read
via hidraw is dropped**:

```
air (btmon) : 00 06 f3 cd 35 fc da d3 37
hidraw      : 06 00 06 f3 cd 35 fc da d3 00   <- last byte lost
```

The auth challenge Resolve reads is corrupted, its response is always
rejected, and it retries every ~1.1 s forever — stalling the UI thread on
the failing ioctls, which is the "lag" on fast jog-wheel use.

It is fixed upstream: commit
[`dc2eb1394f`](https://github.com/bluez/bluez/commit/dc2eb1394f)
*"shared/uhid: Fix size of Get Report reply with a Report ID"* (24 Sep 2026),
expected in BlueZ 5.88. One-line backport for 5.87 (see repo).

```diff
 	if (number) {
 		rsp->data[len++] = number;
-		rsp->size += MIN(size, sizeof(rsp->data) - 1);
+		rsp->size = 1 + MIN(size, sizeof(rsp->data) - 1);
 	} else
 		rsp->size = MIN(size, sizeof(ev.u.input.data));
```

## Root cause 4 — Resolve rejects the fixed BlueZ (please fix this, BMD)

With the BlueZ fix in place the panel went **completely dead** in Resolve —
no LEDs, no input — and the log showed, every ~105 ms during device scan:

```
SyManager | ERROR | BlueZ daemon version too old, reports malformed data.
SyManager | ERROR | Failed to add device.
```

The panel code in Resolve reads its device-info/auth feature reports with
`HIDIOCGFEATURE` and compares the **ioctl return value** against the size of
the report *data without the Report ID*:

| report read          | correct return (fixed BlueZ) | value Resolve requires |
|----------------------|------------------------------|------------------------|
| 0x01 (7 data bytes)  | 8                            | 7                      |
| 0x08 (32 data bytes) | 33                           | 32                     |
| 0x06 (9 data bytes)  | 10                           | 9                      |

On the Bluetooth transport, any value other than the required one is
treated as malformed data from a "too old" BlueZ — i.e. the check was
written against the buggy (truncated) BlueZ and now rejects the correct one.
This is a Blackmagic-side bug: over USB the same ioctl returns the data
size, so the check passes there, but over uhid/BlueZ the reply correctly
includes the Report ID.

**Workaround** — three bytes in `/opt/resolve/bin/resolve` (offsets for
19.1.x; the repo's `resolve-patch.sh` verifies before patching and must be
re-applied after every Resolve update):

```
0x4002C71: 0x07 -> 0x08
0x4003C05: 0x20 -> 0x21
0x40041F6: 0x09 -> 0x0A
```

**The proper fix** is in Resolve: accept the correct return values on the
Bluetooth transport (or validate the payload instead of the ioctl size).
With that, only the udev rule and BlueZ 5.88 remain.

## The optional auth daemon

Until everything above is in place (or as a fallback if the panel ever goes
quiet), `ble_auth.py` performs the `0x06` handshake and re-authenticates
every ~500 s. Because BlueZ blocks D-Bus **writes** to the HID Report
characteristic (`NotAuthorized`) but allows **reads**, it writes through
`/dev/hidraw` (`HIDIOCSFEATURE`, intact) and reads responses over GATT
(intact). Run it as a systemd user service (see repo).

## Verification

```
./check.sh                         # node, bus, permissions
./bluez-probe.py                   # GET_FEATURE returns 8 = BlueZ fixed
./read_hid.py --no-auth            # live input dump
```

## Notes

- The panel remembers **one paired host at a time**. To move it between
  machines: forget it on the old host, hold `CUT + SMTH CUT` for 3 s on the
  panel (all LEDs flicker), then pair normally.
- In a container (distrobox/podman), `/dev` is shared by default; new nodes
  propagate.
- If Blackmagic changes the auth algorithm in a future firmware, the daemon's
  tables need updating (public constants from `blackmagic-misc`/`bmdse`).
- With both USB and Bluetooth connected, USB usually wins.
- Windows/macOS are unaffected by causes 1/3/4 (no BlueZ, no udev).

#!/usr/bin/env python3
"""bt_connect.py -- directly connect a paired phone by MAC. No scanning.

For an already-paired ("bonded") device, connecting is a direct request to
BlueZ over D-Bus. Discovery/scanning is only ever needed to find an UNKNOWN
device the first time; a known MAC never needs it.

Strategy, in order:
  1. Ask BlueZ if the device is already connected -> done.
  2. Call Device1.Connect (connects all supported profiles).
  3. If that fails with br-connection-profile-unavailable, fall back to
     Device1.ConnectProfile for the Handsfree UUID specifically, which often
     succeeds when the blanket Connect does not (common on Tecno/HiOS after a
     reboot, where the phone must present HFP explicitly).

Usage:
    /usr/bin/python3 bt_connect.py                 # uses default MAC below
    /usr/bin/python3 bt_connect.py AA:BB:CC:DD:EE:FF
    PHONE_MAC=AA:BB:.. /usr/bin/python3 bt_connect.py

Requires python3-dbus (sudo apt install python3-dbus). Falls back to the
bluetoothctl CLI automatically if dbus is unavailable.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

PHONE_MAC = os.environ.get("PHONE_MAC", "3C:CA:61:B4:9B:54")
HFP_UUID = "0000111f-0000-1000-8000-00805f9b34fb"
ADAPTER = os.environ.get("BT_ADAPTER", "hci0")
RETRIES = int(os.environ.get("BT_CONNECT_RETRIES", "3"))


def dev_path(mac: str) -> str:
    """BlueZ object path for a device MAC."""
    return f"/org/bluez/{ADAPTER}/dev_" + mac.replace(":", "_")


# --------------------------------------------------------------------------
# D-Bus implementation (preferred)
# --------------------------------------------------------------------------
def connect_dbus(mac: str) -> bool:
    try:
        import dbus
    except ImportError:
        return False  # signal caller to use CLI fallback

    bus = dbus.SystemBus()
    path = dev_path(mac)
    try:
        dev = dbus.Interface(
            bus.get_object("org.bluez", path), "org.bluez.Device1"
        )
        props = dbus.Interface(
            bus.get_object("org.bluez", path),
            "org.freedesktop.DBus.Properties",
        )
    except dbus.DBusException as e:
        print(f"Device not known to BlueZ ({e}). Is it paired?")
        return False

    # 1. already connected?
    try:
        if bool(props.Get("org.bluez.Device1", "Connected")):
            print(f"{mac} already connected.")
            return True
    except dbus.DBusException:
        pass

    # 2. blanket Connect, with retries
    for attempt in range(1, RETRIES + 1):
        try:
            print(f"Connecting {mac} (attempt {attempt}/{RETRIES})...")
            dev.Connect()
            print("Connection successful.")
            return True
        except dbus.DBusException as e:
            msg = str(e)
            print(f"  Connect failed: {msg.splitlines()[-1]}")
            # 3. targeted HFP fallback for profile-unavailable
            if "profile-unavailable" in msg or "NotAvailable" in msg:
                try:
                    print("  Trying Handsfree profile directly...")
                    dev.ConnectProfile(HFP_UUID)
                    print("Connection successful (HFP profile).")
                    return True
                except dbus.DBusException as e2:
                    print(f"  HFP profile connect failed: "
                          f"{str(e2).splitlines()[-1]}")
            time.sleep(2)

    return False


# --------------------------------------------------------------------------
# bluetoothctl CLI fallback (no dbus module needed)
# --------------------------------------------------------------------------
def connect_cli(mac: str) -> bool:
    for attempt in range(1, RETRIES + 1):
        print(f"Connecting {mac} via bluetoothctl (attempt {attempt}/{RETRIES})...")
        r = subprocess.run(
            ["bluetoothctl", "connect", mac],
            capture_output=True, text=True,
        )
        out = r.stdout + r.stderr
        if "Connection successful" in out or "already connected" in out.lower():
            print("Connection successful.")
            return True
        last = out.strip().splitlines()[-1] if out.strip() else "(no output)"
        print(f"  Failed: {last}")
        time.sleep(2)
    return False


def ensure_connected(mac: str = PHONE_MAC) -> bool:
    """Connect the phone by MAC. Returns True on success."""
    ok = connect_dbus(mac)
    if ok:
        return True
    # dbus missing or failed -> CLI fallback
    return connect_cli(mac)


def main() -> int:
    mac = sys.argv[1] if len(sys.argv) > 1 else PHONE_MAC
    if ensure_connected(mac):
        # brief confirmation of the profile we care about
        info = subprocess.run(
            ["bluetoothctl", "info", mac], capture_output=True, text=True
        ).stdout
        if "Handsfree Audio Gateway" in info:
            print("Handsfree Audio Gateway present -- ready to dial.")
        else:
            print("Connected, but Handsfree profile not listed yet.")
        return 0
    print(f"\nCould not connect {mac}.")
    print("If this keeps failing with 'profile-unavailable', open Bluetooth")
    print("settings ON THE PHONE and tap the laptop to connect from that side.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

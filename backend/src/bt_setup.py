#!/usr/bin/env python3
"""bt_setup.py -- idempotent Bluetooth/HFP readiness check + fix for btdial.py.

Import and call ensure_ready() at the top of btdial.py's main(), or run
standalone to check/fix before running the dialer:

    python3 bt_setup.py 3C:CA:61:B4:9B:54 --channel 4
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import time

BLUETOOTHCTL = "bluetoothctl"


def run(cmd, timeout=10, input_text=None):
    """Run a command, return (returncode, combined stdout+stderr)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            input=input_text,
        )
        return result.returncode, (result.stdout or "") + (result.stderr or "")
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return -1, str(e)


def bluetoothctl_batch(commands, wait_per_cmd=1.5):
    """Feed a list of commands into one interactive bluetoothctl session."""
    script = "\n".join(commands) + "\n"
    timeout = 5 + wait_per_cmd * len(commands)
    return run([BLUETOOTHCTL], timeout=timeout, input_text=script)


# ---------------------------------------------------------------- checks --

def is_root():
    return os.geteuid() == 0


def python_has_raw_socket_caps():
    """True if the running python3 binary (resolving symlinks) has cap_net_raw/admin."""
    # Resolve symlink (e.g. .venv/bin/python3 -> real binary) because getcap fails on symlinks
    py_path = os.path.realpath(sys.executable)
    rc, out = run(["getcap", py_path])
    return "cap_net_raw" in out and "cap_net_admin" in out


def bluetooth_service_active():
    rc, out = run(["systemctl", "is-active", "bluetooth"])
    return out.strip() == "active"


def ofono_active():
    rc, out = run(["systemctl", "is-active", "ofono"])
    return out.strip() == "active"


def adapter_powered():
    rc, out = run([BLUETOOTHCTL, "show"])
    return "Powered: yes" in out


def device_info(mac):
    rc, out = run([BLUETOOTHCTL, "info", mac])
    return out


def device_paired(mac):
    return "Paired: yes" in device_info(mac)


def device_trusted(mac):
    return "Trusted: yes" in device_info(mac)


def device_connected(mac):
    return "Connected: yes" in device_info(mac)


def hfp_channel(mac):
    """Best-effort parse of `sdptool records` for the Handsfree/HFP AG
    RFCOMM channel. Returns None if it can't be determined."""
    if not shutil.which("sdptool"):
        return None
    rc, out = run(["sdptool", "records", mac], timeout=15)
    if rc != 0:
        return None
    for block in out.split("Service Name:"):
        if re.search(r"hands[\s-]*free", block, re.I):
            m = re.search(r"RFCOMM.*?Channel:\s*(\d+)", block, re.S)
            if m:
                return int(m.group(1))
    return None


# ---------------------------------------------------------------- fixes --

def start_bluetooth_service():
    print("[bt_setup] starting bluetooth.service ...")
    rc, _ = run(["sudo", "systemctl", "start", "bluetooth"])
    return rc == 0


def power_on_adapter():
    print("[bt_setup] powering on adapter ...")
    bluetoothctl_batch(["power on"])


def disable_ofono():
    """Stop/mask oFono to prevent RFCOMM channel competition."""
    print("[bt_setup] stopping/masking ofono ...")
    run(["sudo", "systemctl", "stop", "ofono"])
    rc, _ = run(["sudo", "systemctl", "mask", "ofono"])
    return rc == 0


def scan_for_device(mac, duration=8):
    print(f"[bt_setup] scanning for {mac} ({duration}s) ...")
    rc, out = bluetoothctl_batch(["scan on", "scan off"], wait_per_cmd=duration)
    return mac.lower() in out.lower()


def pair_and_trust(mac):
    print(f"[bt_setup] pairing + trusting {mac} ...")
    print("           >>> confirm any passkey prompt on the phone now <<<")
    rc, out = bluetoothctl_batch([f"pair {mac}", f"trust {mac}"], wait_per_cmd=6)
    return device_paired(mac), device_trusted(mac), out


def connect_device(mac):
    print(f"[bt_setup] establishing Bluetooth ACL connection to {mac} ...")
    bluetoothctl_batch([f"connect {mac}"], wait_per_cmd=3)
    return device_connected(mac)


# --------------------------------------------------------------- main API --

def ensure_ready(mac, expected_channel=None, auto_pair=True):
    """
    Idempotent check-then-fix. Returns True if the Bluetooth link is ready
    for btdial.py to open its RFCOMM + SCO sockets.
    """
    ok = True

    if not bluetooth_service_active():
        if not start_bluetooth_service():
            print("[bt_setup] FAILED to start bluetooth.service")
            return False
        time.sleep(1)

    if not adapter_powered():
        power_on_adapter()
        time.sleep(1)
        if not adapter_powered():
            print("[bt_setup] FAILED to power on the adapter")
            return False

    if ofono_active():
        if not disable_ofono():
            print("[bt_setup] WARNING: couldn't stop ofono -- it may steal the RFCOMM channel")

    if not device_paired(mac):
        if not auto_pair:
            print(f"[bt_setup] {mac} is not paired and auto_pair=False -- pair it manually")
            return False
        scan_for_device(mac)
        paired, trusted, out = pair_and_trust(mac)
        if not paired:
            print("[bt_setup] FAILED to pair. Output from bluetoothctl:")
            print(out)
            print("[bt_setup] Pair manually with `bluetoothctl` and re-run.")
            return False
    elif not device_trusted(mac):
        run([BLUETOOTHCTL, "trust", mac])

    # Establish base ACL bluetooth connection if currently disconnected
    if not device_connected(mac):
        connect_device(mac)
        time.sleep(1)

    # Capability check (resolved realpath)
    if not (is_root() or python_has_raw_socket_caps()):
        py_path = os.path.realpath(sys.executable)
        print("[bt_setup] WARNING: not running as root and python3 has no raw-socket capabilities.")
        print(f"           fix: sudo setcap 'cap_net_raw,cap_net_admin+eip' {py_path}")
        print("           or replace symlink with binary and run setcap.")
        ok = False

    if expected_channel is not None:
        found = hfp_channel(mac)
        if found is not None and found != expected_channel:
            print(f"[bt_setup] NOTE: phone advertises HFP on channel {found}, "
                  f"not {expected_channel} -- update CHANNEL in btdial.py")

    if ok:
        print("[bt_setup] Bluetooth link ready.")
    return ok


def cli():
    ap = argparse.ArgumentParser(description="Check/fix Bluetooth HFP readiness for btdial.py")
    ap.add_argument("mac", help="phone's Bluetooth MAC address")
    ap.add_argument("--channel", type=int, default=None, help="expected RFCOMM channel")
    ap.add_argument("--no-pair", action="store_true", help="don't attempt auto-pairing")
    args = ap.parse_args()

    ready = ensure_ready(args.mac, expected_channel=args.channel, auto_pair=not args.no_pair)
    print("READY" if ready else "NOT READY")
    sys.exit(0 if ready else 1)


if __name__ == "__main__":
    cli()

#!/usr/bin/env bash
#
# btcall-preflight.sh
# Prepares the Bluetooth HFP stack before running the calling script.
# Run this each time before btdial.py (e.g. after a reboot or when the
# audio channel gets grabbed by PipeWire).
#
#   ./btcall-preflight.sh                 # prep only
#   ./btcall-preflight.sh --run           # prep, then launch btdial.py
#   PHONE_MAC=AA:BB:.. ./btcall-preflight.sh   # override the phone MAC
#
set -uo pipefail

# --- settings (override via environment) ------------------------------------
PHONE_MAC="${PHONE_MAC:-3C:CA:61:B4:9B:54}"
HFP_CHANNEL="${HFP_CHANNEL:-4}"
SCRIPT="${SCRIPT:-btdial.py}"
PY="${PY:-/usr/bin/python3}"     # system python: venv python lacks AF_BLUETOOTH

green() { printf '\033[0;32m%s\033[0m\n' "$1"; }
yellow() { printf '\033[0;33m%s\033[0m\n' "$1"; }
red()    { printf '\033[0;31m%s\033[0m\n' "$1"; }

# --- 1. verify the interpreter has Bluetooth support ------------------------
if ! "$PY" -c "import socket; socket.AF_BLUETOOTH" 2>/dev/null; then
    red "ERROR: $PY has no AF_BLUETOOTH support."
    red "Use the system interpreter (/usr/bin/python3), not a venv."
    exit 1
fi
green "[1/5] Python OK ($PY has AF_BLUETOOTH)"

# --- 2. release the HFP channel from PipeWire/ofono -------------------------
# These hold RFCOMM channel 4 and cause [Errno 16] Device or resource busy.
sudo systemctl stop ofono 2>/dev/null || true
sudo pkill -f ofonod 2>/dev/null || true
systemctl --user restart wireplumber 2>/dev/null || true
green "[2/5] Released HFP channel (stopped ofono, restarted wireplumber)"

# --- 3. cycle the phone connection so profiles renegotiate ------------------
yellow "[3/5] Reconnecting $PHONE_MAC ..."
bluetoothctl disconnect "$PHONE_MAC" >/dev/null 2>&1 || true
sleep 3
bluetoothctl connect "$PHONE_MAC" >/dev/null 2>&1 || true
sleep 3

# --- 4. confirm the phone is connected with the Handsfree profile -----------
info="$(bluetoothctl info "$PHONE_MAC" 2>/dev/null)"
if ! grep -q "Connected: yes" <<<"$info"; then
    red "[4/5] Phone NOT connected. Turn on Bluetooth on both devices."
    red "      If it still fails, the pairing may be lost -- re-pair in bluetoothctl."
    exit 1
fi
if ! grep -q "Handsfree Audio Gateway" <<<"$info"; then
    yellow "[4/5] Connected, but Handsfree profile not listed -- dialing may fail."
else
    green "[4/5] Phone connected with Handsfree Audio Gateway"
fi

# --- 5. confirm RFCOMM channel 4 is actually free ---------------------------
# Quick probe: try to open and immediately close the control channel.
probe="$("$PY" - "$PHONE_MAC" "$HFP_CHANNEL" <<'PYEOF'
import socket, sys
mac, ch = sys.argv[1], int(sys.argv[2])
s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
s.settimeout(5)
try:
    s.connect((mac, ch))
    s.close()
    print("FREE")
except OSError as e:
    print(f"BUSY {e}")
PYEOF
)"
if [[ "$probe" == FREE ]]; then
    green "[5/5] RFCOMM channel $HFP_CHANNEL is free -- ready to dial"
else
    red "[5/5] RFCOMM channel $HFP_CHANNEL still busy: ${probe#BUSY }"
    red "      Something still holds it. Try: sudo pkill -f ofonod ; systemctl --user restart wireplumber"
    exit 1
fi

echo
green "Preflight complete."

# --- optional: launch the calling script ------------------------------------
if [[ "${1:-}" == "--run" ]]; then
    if [[ ! -f "$SCRIPT" ]]; then
        red "Cannot run: $SCRIPT not found in $(pwd)"
        exit 1
    fi
    if [[ ! -f message.wav ]]; then
        yellow "message.wav not found -- the calling script needs it. Record with:"
        yellow "  arecord -f S16_LE -r 8000 -c 1 -d 10 message.wav"
        exit 1
    fi
    echo
    green "Launching $SCRIPT ..."
    exec "$PY" "$SCRIPT"
else
    echo "Now run:  $PY $SCRIPT"
    echo "Or next time:  ./btcall-preflight.sh --run"
fi
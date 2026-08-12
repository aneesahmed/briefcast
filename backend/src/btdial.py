#!/usr/bin/env python3
"""btdial.py v3 -- dial via HFP, stream recorded audio into the call via SCO."""
import socket
import wave
import time
import threading

PHONE_MAC = "3C:CA:61:B4:9B:54"
CHANNEL   = 4
# NUMBER    = "+923118215923" # hamdan
NUMBER    = "+923219277084"
AUDIO_IN  = "message.wav"         # 8kHz 16-bit mono
AUDIO_OUT = "reply.raw"           # their voice, recorded from the call

SCO_PKT = 48        # bytes per SCO packet
PKT_INTERVAL = SCO_PKT / 16000.0  # 8000Hz * 2 bytes = 16000 B/s -> 3ms per packet

def send(s, cmd):
    s.send((cmd + "\r").encode())
    buf = ""
    while True:
        try:
            buf += s.recv(1024).decode(errors="ignore")
        except socket.timeout:
            break
        if "OK" in buf or "ERROR" in buf:
            break
    print(f">> {cmd}\n<< {buf.strip()}\n")
    return buf

def stream_audio(sco):
    """Send WAV into the call; save incoming audio simultaneously."""
    wf = wave.open(AUDIO_IN, "rb")
    assert wf.getframerate() == 8000 and wf.getnchannels() == 1, \
        "message.wav must be 8kHz mono 16-bit"
    data = wf.readframes(wf.getnframes())
    wf.close()

    outfile = open(AUDIO_OUT, "wb")
    stop = threading.Event()

    def receiver():
        sco.settimeout(1)
        while not stop.is_set():
            try:
                pkt = sco.recv(SCO_PKT * 4)
                if pkt:
                    outfile.write(pkt)
            except socket.timeout:
                continue
            except OSError:
                break

    rx = threading.Thread(target=receiver, daemon=True)
    rx.start()

    print(f"🔊 Streaming {len(data)} bytes into the call...")
    t0 = time.time()
    sent = 0
    for i in range(0, len(data), SCO_PKT):
        chunk = data[i:i+SCO_PKT]
        if len(chunk) < SCO_PKT:
            chunk += b"\x00" * (SCO_PKT - len(chunk))   # pad last packet
        try:
            sco.send(chunk)
        except OSError as e:
            print(f"SCO send failed mid-stream: {e}")
            break
        sent += 1
        # pace to real time -- SCO has no buffering mercy
        target = t0 + sent * PKT_INTERVAL
        delay = target - time.time()
        if delay > 0:
            time.sleep(delay)

    print("✅ Audio sent. Recording reply for 5 more seconds...")
    time.sleep(5)
    stop.set()
    outfile.close()

def main():
    # --- control channel (what already works) ---
    ctrl = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM,
                         socket.BTPROTO_RFCOMM)
    ctrl.settimeout(5)
    print("Connecting HFP control channel...")
    ctrl.connect((PHONE_MAC, CHANNEL))
    print("Connected!\n")

    send(ctrl, "AT+BRSF=20")
    send(ctrl, "AT+CIND=?")
    send(ctrl, "AT+CIND?")
    send(ctrl, "AT+CMER=3,0,0,1")

    print(f"Dialing {NUMBER}...")
    if "ERROR" in send(ctrl, f"ATD{NUMBER};"):
        print("❌ Dial rejected"); return

    print("📞 Ringing... waiting for answer\n")
    answered = False
    ctrl.settimeout(1)
    while not answered:
        try:
            data = ctrl.recv(1024).decode(errors="ignore")
        except socket.timeout:
            continue
        for line in data.splitlines():
            line = line.strip()
            if line:
                print(f"<< {line}")
            if "+CIEV: 1,1" in line:
                answered = True
            if "+CIEV: 1,0" in line and answered:
                print("📴 Ended before we spoke."); return

    print("✅ ANSWERED — opening SCO audio link...")
    time.sleep(0.5)

    # --- the experimental part: HF-initiated SCO audio connection ---
    try:
        sco = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET,
                            socket.BTPROTO_SCO)
        sco.connect(PHONE_MAC.encode())
        print("🎉 SCO AUDIO LINK ESTABLISHED — laptop audio is IN the call!")
        stream_audio(sco)
        sco.close()
    except OSError as e:
        print(f"❌ SCO connect failed: {e}")
        print("   (chipset/phone won't allow HF-initiated audio -- see notes)")

    # keep call state visible until hangup
    print("\nCall still live -- Ctrl+C to exit")
    try:
        while True:
            try:
                data = ctrl.recv(1024).decode(errors="ignore").strip()
                if data:
                    print(f"<< {data}")
                if "+CIEV: 1,0" in data:
                    print("📴 Call ended."); break
            except socket.timeout:
                continue
    except KeyboardInterrupt:
        pass
    ctrl.close()

if __name__ == "__main__":
    main()
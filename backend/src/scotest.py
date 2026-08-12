#!/usr/bin/env python3
"""btdial.py v4 -- dial via HFP, stream recorded audio into the call via SCO (WORKING)."""
import socket
import wave
import time
import threading

PHONE_MAC = "3C:CA:61:B4:9B:54"
CHANNEL   = 4
NUMBER    = "+923118215923"
AUDIO_IN  = "message.wav"
AUDIO_OUT = "reply.raw"

SCO_PKT = 48
PKT_INTERVAL = SCO_PKT / 16000.0

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

    threading.Thread(target=receiver, daemon=True).start()

    print(f"🔊 Streaming {len(data)} bytes into the call...")
    t0 = time.time()
    sent = 0
    for i in range(0, len(data), SCO_PKT):
        chunk = data[i:i+SCO_PKT]
        if len(chunk) < SCO_PKT:
            chunk += b"\x00" * (SCO_PKT - len(chunk))
        try:
            sco.send(chunk)
        except OSError as e:
            print(f"SCO send failed: {e}")
            break
        sent += 1
        target = t0 + sent * PKT_INTERVAL
        delay = target - time.time()
        if delay > 0:
            time.sleep(delay)

    print("✅ Audio sent. Recording reply for 5 more seconds...")
    time.sleep(5)
    stop.set()
    outfile.close()

def main():
    ctrl = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
    ctrl.settimeout(5)
    ctrl.connect((PHONE_MAC, CHANNEL))
    print("Connected control channel\n")

    send(ctrl, "AT+BRSF=20")
    send(ctrl, "AT+CIND=?")
    send(ctrl, "AT+CIND?")
    send(ctrl, "AT+CMER=3,0,0,1")

    print(f"Dialing {NUMBER}...")
    if "ERROR" in send(ctrl, f"ATD{NUMBER};"):
        print("❌ Dial rejected"); return

    print("📞 Waiting for answer...\n")
    ctrl.settimeout(1)
    answered = False
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

    print("\n✅ ANSWERED — opening SCO...")
    time.sleep(0.3)

    try:
        sco = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_SCO)
        sco.settimeout(5)
        sco.connect(PHONE_MAC.encode())   # <-- the fix: bytes, not tuple
        print("🎉 SCO CONNECTED — streaming audio into live call")
        stream_audio(sco)
        sco.close()
    except OSError as e:
        print(f"❌ SCO failed: {e}")

    print("\nHanging up...")
    send(ctrl, "AT+CHUP")
    ctrl.close()

if __name__ == "__main__":
    main()
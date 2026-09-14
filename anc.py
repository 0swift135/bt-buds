#!/usr/bin/env python3
"""Set/toggle ANC on Redmi Buds 6 Lite via Xiaomi RFCOMM channel 29.
Usage: anc.py on|off|toggle  ->  prints 0/1 (new state), exit 0 on ACK.
State (last set value + seq) kept in ~/.local/state/bt-buds/anc.json.
"""
import json
import os
import socket
import sys

MAC = "78:99:87:AD:44:BA"
CH = 29
STATE_PATH = os.path.expanduser("~/.local/state/bt-buds/anc.json")


def load_state():
    try:
        with open(STATE_PATH) as f:
            d = json.load(f)
            return int(d.get("anc", 0))
    except Exception:
        return 0


def save_state(anc):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump({"anc": anc}, f)


def drain(s, wait=1.2):
    out = b""
    s.settimeout(wait)
    try:
        while True:
            d = s.recv(4096)
            if not d:
                break
            out += d
    except socket.timeout:
        pass
    return out


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("on", "off", "toggle"):
        print("usage: anc.py on|off|toggle", file=sys.stderr)
        return 2
    cur = load_state()
    target = {"on": 1, "off": 0, "toggle": 0 if cur else 1}[sys.argv[1]]
    seq = 0x08  # fresh session starts low, like the phone app

    s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
    s.settimeout(5)
    try:
        s.connect((MAC, CH))
    except Exception as e:
        print("connect fail: %s" % e, file=sys.stderr)
        return 1
    try:
        s.send(bytes.fromhex("1bfedcbac402000506ffffffff"))
        drain(s, 0.8)
        s.send(bytes.fromhex("01fedcbac4f3000507000b000c"))
        drain(s, 0.8)
        s.send(bytes.fromhex("19fedcbac4080004%02x0204%02x" % (seq, target)))
        reply = drain(s, 2.0)
        # protocol handshake: follow-up ack with seq+0x17 (as the phone app does)
        s.send(bytes.fromhex("15fedcba04f4000200%02x" % ((seq + 0x17) & 0xFF)))
        reply += drain(s, 1.5)
    except Exception as e:
        print("io fail: %s" % e, file=sys.stderr)
        return 1
    finally:
        s.close()
    if not reply:
        print("no ack", file=sys.stderr)
        return 1
    save_state(target)
    print(target)
    return 0


if __name__ == "__main__":
    sys.exit(main())

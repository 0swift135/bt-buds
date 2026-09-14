#!/usr/bin/env python3
"""bt-buds EQ via ffmpeg: apps -> eq_in (null sink) -> ffmpeg DSP -> buds.

Usage: eq.py set <normal|more_bass|boost_vocals|more_highs> | eq.py get
Prints 'ok <preset>' or 'err <reason>'.
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import time

STATE_DIR = os.path.expanduser("~/.local/state/bt-buds")
CUR_FILE = os.path.join(STATE_DIR, "eq.json")
PID_FILE = os.path.join(STATE_DIR, "eq-ffmpeg.pid")
EQ_SINK = "eq_in"

FILTERS = {
    "normal": "anull",
    "more_bass": "bass=g=7:f=150,treble=g=1:f=8000",
    "boost_vocals": "bass=g=-2:f=150,equalizer=f=1500:t=q:w=1:g=5,equalizer=f=4000:t=q:w=1:g=3,treble=g=1:f=10000",
    "more_highs": "bass=g=-2:f=150,equalizer=f=1500:t=q:w=1:g=1,treble=g=6:f=6000",
}
PRESETS = list(FILTERS.keys())


def run(*args, timeout=15):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def buds_sink():
    try:
        out = run("pactl", "list", "sinks", "short").stdout
    except subprocess.TimeoutExpired:
        return None
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1].startswith("bluez_output."):
            return parts[1]
    return None


def ensure_eq_sink():
    try:
        out = run("pactl", "list", "sinks", "short").stdout
    except subprocess.TimeoutExpired:
        return False
    if EQ_SINK in out:
        return True
    try:
        r = run("pactl", "load-module", "module-null-sink",
                "sink_name=" + EQ_SINK,
                "sink_properties=device.description=BudsEQ")
        return r.returncode == 0
    except subprocess.TimeoutExpired:
        return False


def own_ffmpeg_pids():
    found = []
    me = os.getpid()
    for pid in os.listdir("/proc"):
        if not pid.isdigit() or int(pid) == me:
            continue
        try:
            with open("/proc/%s/cmdline" % pid, "rb") as f:
                cmd = f.read().replace(b"\0", b" ").decode()
        except (OSError, ValueError):
            continue
        if "ffmpeq-buds" in cmd and "eq.py" not in cmd:
            found.append(int(pid))
    return found


def stop_chain():
    for pid in own_ffmpeg_pids():
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    try:
        with open(PID_FILE) as f:
            old = int(f.read().strip())
        os.kill(old, signal.SIGTERM)
    except (OSError, ValueError):
        pass
    time.sleep(0.5)
    for pid in own_ffmpeg_pids():
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    try:
        os.unlink(PID_FILE)
    except OSError:
        pass


def start_chain(afilter, target):
    log = os.path.join(STATE_DIR, "eq-ffmpeg.log")
    proc = subprocess.Popen(
        ["ffmpeg", "-hide_banner", "-loglevel", "error",
         "-f", "pulse", "-i", EQ_SINK + ".monitor",
         "-af", afilter,
         "-f", "pulse", "-device", target, "ffmpeq-buds"],
        stdout=open(log, "ab"), stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, start_new_session=True)
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(PID_FILE, "w") as f:
        f.write(str(proc.pid))
    time.sleep(3)
    if proc.poll() is not None:
        return False
    return proc.pid in own_ffmpeg_pids() or proc.poll() is None


def list_inputs():
    """Parse `pactl list sink-inputs` -> [(id, sink, app, media)]."""
    try:
        out = run("pactl", "list", "sink-inputs").stdout
    except subprocess.TimeoutExpired:
        return []
    items, cur = [], {}
    for line in out.splitlines():
        if line.startswith("Sink Input #"):
            if cur:
                items.append(cur)
            cur = {"id": line.split("#")[1].strip(), "sink": "", "app": "", "media": ""}
        elif cur is not None:
            s = line.strip()
            if s.startswith("Sink:"):
                cur["sink"] = s.split(":", 1)[1].strip()
            elif s.startswith("application.name"):
                cur["app"] = s.split("=", 1)[1].strip().strip('"')
            elif s.startswith("media.name"):
                cur["media"] = s.split("=", 1)[1].strip().strip('"')
    if cur:
        items.append(cur)
    return [(i["id"], i["sink"], i["app"], i["media"]) for i in items]


def pin_ffmpeg_output(target):
    for _ in range(3):
        moved = False
        for iid, sink, app, media in list_inputs():
            if media == "ffmpeq-buds" and sink != target:
                try:
                    run("pactl", "move-sink-input", iid, target)
                    moved = True
                except subprocess.TimeoutExpired:
                    pass
        if not moved:
            return
        time.sleep(1)


def route_to_eq():
    try:
        if run("pactl", "get-default-sink").stdout.strip() != EQ_SINK:
            run("pactl", "set-default-sink", EQ_SINK)
        for iid, sink, app, media in list_inputs():
            if media == "ffmpeq-buds" or app.startswith("Lavf"):
                continue
            if sink != EQ_SINK:
                run("pactl", "move-sink-input", iid, EQ_SINK)
    except subprocess.TimeoutExpired:
        pass


def save_cur(name):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(CUR_FILE, "w") as f:
        json.dump({"eq": name}, f)


def main(argv):
    if len(argv) == 1 and argv[0] == "get":
        try:
            with open(CUR_FILE) as f:
                name = json.load(f).get("eq", "normal")
        except (OSError, ValueError):
            name = "normal"
        print("ok %s" % name)
        return 0
    if len(argv) != 2 or argv[0] != "set" or argv[1] not in PRESETS:
        print("err usage: eq.py set <%s> | get" % "|".join(PRESETS))
        return 2
    name = argv[1]
    if shutil.which("ffmpeg") is None or shutil.which("pactl") is None:
        print("err no-deps")
        return 3
    target = buds_sink()
    if target is None:
        print("err no-buds")
        return 4
    if not ensure_eq_sink():
        print("err eq-sink")
        return 5
    stop_chain()
    if not start_chain(FILTERS[name], target):
        print("err ffmpeg-start")
        return 6
    pin_ffmpeg_output(target)
    route_to_eq()
    save_cur(name)
    print("ok %s" % name)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

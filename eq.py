#!/usr/bin/env python3
"""bt-buds EQ via EasyEffects output presets.

Usage: eq.py set <normal|more_bass|boost_vocals|more_highs> | eq.py get
Prints 'ok <preset>' or 'err <reason>'.
"""
import json
import os
import shutil
import subprocess
import sys
import time

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.expanduser("~/.local/state/bt-buds")
EE_OUT = os.path.expanduser("~/.config/easyeffects/output")
CUR_FILE = os.path.join(STATE_DIR, "eq.json")
PRESETS = ["normal", "more_bass", "boost_vocals", "more_highs"]


def run(*args, timeout=20):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def ensure_daemon():
    if run("pgrep", "-f", "easyeffects").returncode == 0:
        return True
    if shutil.which("easyeffects") is None:
        return False
    subprocess.Popen(["easyeffects", "--gapplication-service"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(10):
        time.sleep(1)
        if run("pgrep", "-f", "easyeffects").returncode == 0:
            return True
    return False


def ensure_preset(name):
    os.makedirs(EE_OUT, exist_ok=True)
    src = os.path.join(PLUGIN_DIR, "easyeffects", "btbuds-%s.json" % name)
    dst = os.path.join(EE_OUT, "btbuds-%s.json" % name)
    if os.path.exists(src):
        shutil.copyfile(src, dst)
    return dst if os.path.exists(dst) else None


def save_cur(name):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(CUR_FILE, "w") as f:
        json.dump({"eq": name}, f)


def main(argv):
    if len(argv) == 2 and argv[0] == "get":
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
    if shutil.which("easyeffects") is None:
        print("err no-easyeffects")
        return 3
    if not ensure_daemon():
        print("err daemon")
        return 4
    if ensure_preset(name) is None:
        print("err preset-file")
        return 5
    r = run("easyeffects", "-l", "btbuds-%s" % name)
    if r.returncode != 0:
        print("err load")
        return 6
    save_cur(name)
    print("ok %s" % name)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""Apply ONE optimization variant to gyro-l.service, restart once, bench, leave up.

usage: gyro_opt_run.py VARIANT -- FLAG FLAG ...
Derives flags from the CURRENT live process/unit ExecStart so no production flag
is lost; forces --ctx-size 128000 --parallel 1; drops any existing --spec-type.
"""
import json
import os
import re
import shlex
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
UNIT = "/home/joe/.config/systemd/user/gyro-l.service"
BIN = "/home/joe/src/llama-gyro/build/bin/llama-server"


def sh(cmd, t=90):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=t)


def health():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8081/health", timeout=5) as r:
            return r.status == 200
    except Exception:                                   # noqa: BLE001
        return False


def busy():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8081/server_info", timeout=5) as r:
            d = json.loads(r.read().decode())
    except Exception:                                   # noqa: BLE001
        return False
    return any(s.get("state") not in (None, "idle") or s.get("is_generating") for s in d.get("slots", []))


def live_args():
    """Args of the currently serving process (authoritative), else unit ExecStart."""
    out = sh("tr '\\0' ' ' < /proc/$(pgrep -f 'llama-server.*port 8081' | head -1)/cmdline").stdout.strip()
    if out:
        return shlex.split(out)
    body = open(UNIT, encoding="utf-8").read()
    ex = [l for l in body.splitlines() if l.strip().startswith("ExecStart")][0]
    return shlex.split(ex.split("=", 1)[1])[1:]


def setopt(args, name, value):
    if name in args:
        args[args.index(name) + 1] = value
    else:
        args += [name, value]
    return args


def drop(args, *names):
    out, i = [], 0
    while i < len(args):
        if args[i] in names:
            i += 1
            if i < len(args) and not args[i].startswith("-"):
                i += 1
            continue
        out.append(args[i])
        i += 1
    return out


def main():
    variant = sys.argv[1]
    extra = sys.argv[3:] if sys.argv[2:3] == ["--"] else sys.argv[2:]
    args = live_args()
    args = setopt(setopt(args, "--ctx-size", "128000"), "--parallel", "1")
    args = drop(args, "--spec-type")
    args += extra
    body = open(UNIT, encoding="utf-8").read()
    ex = [l for l in body.splitlines() if l.strip().startswith("ExecStart")][0]
    new = "ExecStart=" + BIN + " " + " ".join(shlex.quote(a) for a in args)
    open(UNIT, "w", encoding="utf-8").write(body.replace(ex, new))
    print(f"[{variant}] variant flags: {' '.join(extra) or '(none = baseline)'}", flush=True)
    print(f"[{variant}] effective: {re.findall(r'--(?:ctx-size|parallel|spec-type|cache-type-[kv]|ngram-on-disk|flash-attn|tensor-split|split-mode) \\S+', ' '.join(args))}",
          flush=True)
    sh("systemctl --user daemon-reload gyro-l.service")

    for _ in range(12):
        if not busy():
            break
        print("[opt] inference active, waiting…", flush=True)
        time.sleep(5)
    print(f"[{variant}] busy before stop: {busy()}", flush=True)

    pid = sh("pgrep -f 'llama-server.*port 8081' | head -1").stdout.strip()
    if pid:
        sh(f"kill {pid}")
        for _ in range(25):
            if not health():
                break
            time.sleep(2)
    sh("systemctl --user reset-failed gyro-l.service")
    sh("systemctl --user start gyro-l.service")
    t0 = time.time()
    while time.time() - t0 < 240:
        if health():
            break
        time.sleep(3)
    ok = health()
    print(f"[{variant}] service healthy={ok} after {time.time()-t0:.0f}s", flush=True)
    if not ok:
        print(sh("journalctl --user -u gyro-l.service -n 30 --no-pager").stdout[-1800:])
        sys.exit(2)
    r = subprocess.run([sys.executable, os.path.join(HERE, "gyro_opt_bench.py"), variant,
                        os.path.join(HERE, f"bench_{variant}.json")], cwd=HERE, timeout=480)
    print(f"[{variant}] bench exit={r.returncode}", flush=True)
    sys.exit(r.returncode)


main()

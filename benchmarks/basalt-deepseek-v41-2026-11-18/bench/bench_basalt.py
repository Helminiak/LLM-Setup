#!/usr/bin/env python3
"""Frozen-fixture benchmark for basalt-deepseek-v41 through Llama Swap only.

Usage: python3 -I bench_basalt.py LABEL OUTFILE
All inference goes to http://127.0.0.1:8080 (Llama Swap). Nothing here talks to the engine directly.
"""
import json, sys, time, urllib.request, subprocess, datetime, re

GATEWAY = "http://127.0.0.1:8080/v1/chat/completions"
MODEL = "basalt-deepseek-v41"
TEMP = 0


def _json_ok(t):
    m = re.search(r"\{.*\}", t, re.S)
    if not m:
        return False
    try:
        d = json.loads(m.group(0))
    except Exception:
        return False
    return {"name", "ports", "enabled"} <= set(d)


FIXTURES = [
    {
        "id": "coding",
        "prompt": "Write a Python function merge_intervals(intervals) that merges overlapping closed intervals and returns them sorted. Output only code.",
        "max_tokens": 200,
        "check": lambda t: "def merge_intervals" in t,
    },
    {
        "id": "structured",
        "prompt": 'Return JSON only, no prose: {"name": string, "ports": [int], "enabled": bool} for an nginx summary with ports 80 and 443, enabled true, name "nginx".',
        "max_tokens": 96,
        "check": _json_ok,
    },
    {
        "id": "reasoning",
        "prompt": "A train leaves a station at 9:00 going 60 km/h. Another leaves the same station at 10:00 going 90 km/h in the same direction. At what clock time does the second catch the first? Give the time and one line of justification.",
        "max_tokens": 160,
        "check": lambda t: ("12:00" in t) or ("noon" in t.lower()),
    },
]


def vmstat(keys=("pswpin", "pswpout")):
    out = {}
    for line in open("/proc/vmstat"):
        k, v = line.split()
        if k in keys:
            out[k] = int(v)
    return out


def psi():
    return open("/proc/pressure/memory").read().strip().splitlines()[0]


def gpu():
    r = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.used,utilization.gpu",
                        "--format=csv,noheader,nounits"], capture_output=True, text=True)
    return r.stdout.strip().replace("\n", " | ")


def ram_avail_mib():
    for line in open("/proc/meminfo"):
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) // 1024


def call(prompt, max_tokens):
    body = json.dumps({"model": MODEL, "messages": [{"role": "user", "content": prompt}],
                       "max_tokens": max_tokens, "temperature": TEMP, "stream": False}).encode()
    req = urllib.request.Request(GATEWAY, data=body, headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=900) as resp:
        raw = json.loads(resp.read())
    return raw, time.time() - t0


def main():
    label, outfile = sys.argv[1], sys.argv[2]
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    vm0 = vmstat()
    results = {"label": label, "started_utc": started, "gpu_before": gpu(),
               "ram_avail_before_mib": ram_avail_mib(), "psi_before": psi(), "runs": []}
    for f in FIXTURES:  # warmup, excluded from timing
        call(f["prompt"], 8)
    for rep in range(3):
        for f in FIXTURES:
            raw, wall = call(f["prompt"], f["max_tokens"])
            text = raw["choices"][0]["message"].get("content") or ""
            tm = raw.get("timings", {})
            results["runs"].append({
                "rep": rep, "fixture": f["id"], "wall_s": round(wall, 2),
                "prompt_tokens": raw["usage"]["prompt_tokens"],
                "completion_tokens": raw["usage"]["completion_tokens"],
                "prefill_tps": tm.get("prompt_per_second"),
                "decode_tps": tm.get("predicted_per_second"),
                "draft_n": tm.get("draft_n"), "draft_accepted_n": tm.get("draft_accepted_n"),
                "correct": bool(f["check"](text)),
                "output_head": text[:160],
            })
    vm1 = vmstat()
    results.update({"gpu_after": gpu(), "ram_avail_after_mib": ram_avail_mib(), "psi_after": psi(),
                    "pswpin_delta": vm1["pswpin"] - vm0["pswpin"], "pswpout_delta": vm1["pswpout"] - vm0["pswpout"],
                    "finished_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()})
    with open(outfile, "w") as fh:
        json.dump(results, fh, indent=2)
    dec = [r["decode_tps"] for r in results["runs"] if r["decode_tps"]]
    ok = sum(r["correct"] for r in results["runs"])
    print(f"{label}: runs={len(results['runs'])} correct={ok}/{len(results['runs'])} "
          f"decode_tps_mean={sum(dec)/len(dec):.2f} swap_in={results['pswpin_delta']} swap_out={results['pswpout_delta']}")


if __name__ == "__main__":
    main()

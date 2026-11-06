#!/usr/bin/env python3
"""Window-level GPU + slot telemetry summary for the dual-5090 smoke test."""
import csv, json, os, statistics as st, sys
from collections import Counter

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
G = list(csv.DictReader(open(f"{BASE}/results/gpu_campaign.csv")))
S = list(csv.DictReader(open(f"{BASE}/results/slot_campaign.csv")))
F = lambda v: float(v) if v not in (None, "", "[N/A]", "N/A") else None


def num(rows, key):
    out = []
    for r in rows:
        v = F(r.get(key, ""))
        if v is not None:
            out.append(v)
    return out


def win(rows, t0, t1):
    return [r for r in rows if t0 <= float(r["elapsed_s"]) <= t1]


def summarize(label, t0, t1):
    g = win(G, t0, t1)
    per = {}
    for gid in sorted(set(r["gpu_id"] for r in g)):
        sub = [r for r in g if r["gpu_id"] == gid]
        pw = num(sub, "power_w")
        ut = num(sub, "util_gpu_pct")
        um = num(sub, "util_mem_pct")
        tc = num(sub, "temp_c")
        sm = num(sub, "sm_clock_mhz")
        mc = num(sub, "mem_clock_mhz")
        mu = num(sub, "mem_used_mib")
        n = len(sub)
        dt = (float(sub[-1]["elapsed_s"]) - float(sub[0]["elapsed_s"])) / max(1, n - 1)
        thr = Counter(r["throttle_reasons"].strip() for r in sub)
        per[gid] = dict(
            samples=n, dt_s=round(dt, 3), pstates=sorted(set(r["pstate"].strip() for r in sub)),
            util_gpu_mean=round(st.mean(ut), 1), util_gpu_max=max(ut),
            util_mem_mean=round(st.mean(um), 1), util_mem_max=max(um),
            power_mean_w=round(st.mean(pw), 1), power_peak_w=round(max(pw), 1),
            power_min_w=round(min(pw), 1), power_p95_w=round(sorted(pw)[int(0.95 * (len(pw) - 1))], 1),
            energy_wh=round(sum(pw) * dt / 3600.0, 2),
            temp_mean_c=round(st.mean(tc), 1), temp_max_c=max(tc),
            sm_clock_mean=round(st.mean(sm)), sm_clock_min=min(sm), sm_clock_max=max(sm),
            mem_clock_mean=round(st.mean(mc)), mem_clock_max=max(mc),
            vram_used_peak_mib=int(max(mu)), vram_total_mib=int(F(sub[0]["mem_total_mib"]) or 0),
            vram_free_min_gib=round(((F(sub[0]["mem_total_mib"]) or 0) - max(mu)) / 1024.0, 2),
            throttle=dict(thr), power_limit_w=round(max(num(sub, "power_limit_w")), 0),
        )
    combined_mean = round(sum(v["power_mean_w"] for v in per.values()), 1)
    combined_peak = round(sum(v["power_peak_w"] for v in per.values()), 1)
    combined_wh = round(sum(v["energy_wh"] for v in per.values()), 2)
    s = win(S, t0, t1)
    busy = Counter(int(r["busy_slots"]) for r in s if r["busy_slots"] != "ERR")
    n_ok = sum(busy.values()) or 1
    return dict(
        label=label, wall_s=round(t1 - t0, 1), gpu_samples=len(g),
        per_gpu=per, combined_power_mean_w=combined_mean, combined_power_peak_w=combined_peak,
        combined_energy_wh=combined_wh,
        slot_busy_fraction={str(k): round(v / n_ok, 3) for k, v in sorted(busy.items())},
        samples_both_slots_busy=busy.get(2, 0),
    )


if __name__ == "__main__":
    print("This script summarizes a newly collected window when supplied by the calling harness.")
    raise SystemExit("For archived data, use the published aggregate JSON files.")

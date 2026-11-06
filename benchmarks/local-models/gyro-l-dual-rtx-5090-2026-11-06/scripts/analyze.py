#!/usr/bin/env python3
"""Analyse dual-RTX-5090 smoke-test telemetry + load records.

Reports measured values only:
  * per-GPU mean/peak power, utilisation, temperature, clocks, free VRAM
  * distinct throttle-reason bitmasks observed (0x0 == none)
  * energy in Wh, integrated from the 1 Hz power samples (trapezoid-free:
    each sample held for the gap to the next sample of the same GPU)
  * load-window-aligned stats when a load JSON is supplied
  * sustained-throughput trend from the server-reported per-request timings

Amperage is NOT reported: this driver exposes no voltage or current sensor
(verified: `nvidia-smi --help-query-gpu` has no volt/amper/electr field), and
power alone cannot give current without a verified rail voltage.
"""
import argparse
import json
import statistics


def fnum(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def nums(rows, key):
    """Numeric column values with non-numeric entries ([N/A], [Not Supported])."""
    return [v for v in (fnum(r.get(key)) for r in rows) if v is not None]


def read_csv(path):
    with open(path) as fh:
        header = fh.readline().strip().split(",")
        rows = []
        for line in fh:
            if not line.strip():
                continue
            parts = line.rstrip("\n").split(",")
            if len(parts) != len(header):
                continue
            rows.append(dict(zip(header, parts)))
    return rows


def gpu_stats(rows, ids, t0=None, t1=None):
    out = {}
    for gid in ids:
        g = [r for r in rows if r["gpu_id"] == str(gid)]
        if t0 is not None:
            g = [r for r in g if t0 <= float(r["mono"]) <= t1]
        if not g:
            out[gid] = {"samples": 0}
            continue
        pw = nums(g, "power_w")
        ut = nums(g, "util_gpu_pct")
        mu = nums(g, "util_mem_pct")
        tp = nums(g, "temp_c")
        sm = nums(g, "sm_clock_mhz")
        mc = nums(g, "mem_clock_mhz")
        used = nums(g, "mem_used_mib")
        total = nums(g, "mem_total_mib")
        thr = sorted({r["throttle_reasons"] for r in g})
        # integrate energy: hold each sample until the next sample of this GPU
        mono = [float(r["mono"]) for r in g]
        pairs = [(float(r["mono"]), fnum(r["power_w"])) for r in g]
        energy = 0.0
        for i in range(len(pairs) - 1):
            dt = pairs[i + 1][0] - pairs[i][0]
            p = pairs[i][1]
            if 0.05 <= dt <= 3.0 and p is not None:
                energy += p * dt
        hours = (mono[-1] - mono[0]) / 3600.0
        out[gid] = {
            "samples": len(g),
            "window_s": round(mono[-1] - mono[0], 2),
            "power_w_mean": round(statistics.mean(pw), 1) if pw else None,
            "power_w_peak": round(max(pw), 1) if pw else None,
            "power_w_min": round(min(pw), 1) if pw else None,
            "energy_wh": round(energy / 3600.0, 2),
            "energy_wh_from_mean": round(statistics.mean(pw) * hours, 2) if pw else None,
            "util_gpu_pct_mean": round(statistics.mean(ut), 1) if ut else None,
            "util_gpu_pct_peak": round(max(ut), 1) if ut else None,
            "util_gpu_pct_nonzero_frac": round(
                sum(1 for u in ut if u > 0) / len(ut), 3) if ut else None,
            "util_mem_pct_mean": round(statistics.mean(mu), 1) if mu else None,
            "util_mem_pct_peak": round(max(mu), 1) if mu else None,
            "temp_c_mean": round(statistics.mean(tp), 1) if tp else None,
            "temp_c_peak": round(max(tp), 1) if tp else None,
            "sm_clock_mean_mhz": round(statistics.mean(sm), 0) if sm else None,
            "sm_clock_min_mhz": round(min(sm), 0) if sm else None,
            "sm_clock_max_mhz": round(max(sm), 0) if sm else None,
            "mem_clock_mean_mhz": round(statistics.mean(mc), 0) if mc else None,
            "mem_used_peak_mib": round(max(used), 0) if used else None,
            "mem_free_min_mib": (round(min(total) - max(used), 0)
                                 if used and total else None),
            "mem_free_min_gib": (round((min(total) - max(used)) / 1024.0, 2)
                                 if used and total else None),
            "throttle_reasons_seen": thr,
            "power_limit_w": fnum(g[0]["power_limit_w"]),
            "pstate_seen": sorted({r["pstate"] for r in g}),
        }
    return out


def load_window(load):
    """Return (t0,t1) in sampler-mono space is unknown; use epoch instead."""
    reqs = [r for r in load["requests"] if "lane_end" not in r]
    if not reqs:
        return None, None
    return min(r["start_epoch"] for r in reqs), max(r.get("end_epoch", 0) for r in reqs)


def window_rows_by_epoch(path, t0, t1):
    rows = read_csv(path)
    out = {}
    for gid in {r["gpu_id"] for r in rows}:
        g = [r for r in rows if r["gpu_id"] == gid]
        g = [r for r in g if t0 <= float(r["epoch"]) <= t1]
        out[int(gid)] = g
    return out


def sustained_trend(load, buckets=5):
    """Per-request server decode tok/s, bucketed over the run's time order."""
    reqs = [r for r in load["requests"]
            if "error" not in r and r.get("timings")]
    by_lane = {}
    for r in reqs:
        by_lane.setdefault(r["lane"], []).append(r)
    trend = {}
    for lane, rr in by_lane.items():
        rr.sort(key=lambda r: r["start_epoch"])
        n = len(rr)
        if n < buckets:
            trend[lane] = {"requests": n, "note": "too few requests to bucket"}
            continue
        size = n // buckets
        chunks = [rr[i * size:(i + 1) * size] for i in range(buckets)]
        vals = []
        for c in chunks:
            tok = sum(r["usage"].get("completion_tokens", 0) for r in c)
            ms = sum(r["timings"].get("predicted_ms") or 0 for r in c)
            vals.append(round(tok * 1000.0 / ms, 2) if ms else None)
        first, last = vals[0], vals[-1]
        trend[lane] = {
            "requests": n,
            "decode_tok_s_by_quintile": vals,
            "first_vs_last_delta_pct":
                round((last - first) * 100.0 / first, 1)
                if first and last else None,
        }
    return trend


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--load", default=None)
    ap.add_argument("--label", default="")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    report = {"label": args.label, "csv": args.csv}
    if args.load:
        with open(args.load) as fh:
            load = json.load(fh)
        report["load_summary"] = load["summary"]
        t0, t1 = load_window(load)
        if t0 is not None:
            rows_by_gpu = window_rows_by_epoch(args.csv, t0, t1)
            allrows = [dict(r, gpu_id=str(gid))
                       for gid, rs in rows_by_gpu.items() for r in rs]
            report["gpu_in_load_window"] = {
                str(k): v for k, v in
                gpu_stats(allrows, sorted(rows_by_gpu.keys())).items()}
        report["sustained_trend"] = sustained_trend(load)
    else:
        report["gpu_whole_file"] = gpu_stats(read_csv(args.csv), [0, 1])

    txt = json.dumps(report, indent=1)
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(txt + "\n")
    print(txt)


if __name__ == "__main__":
    main()

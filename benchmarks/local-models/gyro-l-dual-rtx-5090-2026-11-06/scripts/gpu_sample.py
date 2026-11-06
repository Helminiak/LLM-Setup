#!/usr/bin/env python3
"""1 Hz GPU telemetry sampler for the dual-RTX-5090 Gyro-L smoke test.

Writes one CSV row per GPU per second. Writes an abort marker file and exits 3
if any GPU crosses --max-temp (unsafe thermal condition).

No GPU settings are touched: read-only nvidia-smi queries only.
"""
import argparse
import os
import subprocess
import sys
import time

QUERY = ("index,timestamp,pstate,utilization.gpu,utilization.memory,"
         "temperature.gpu,memory.used,memory.total,power.draw,power.limit,"
         "clocks.current.sm,clocks.current.memory,clocks_event_reasons.active,"
         "fan.speed")
HEADER = ("elapsed_s,gpu_id,pstate,util_gpu_pct,util_mem_pct,"
          "temp_c,mem_used_mib,mem_total_mib,power_w,power_limit_w,"
          "sm_clock_mhz,mem_clock_mhz,throttle_reasons,fan_pct")


def sample():
    out = subprocess.run(
        ["nvidia-smi", f"--query-gpu={QUERY}", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=20,
    )
    if out.returncode != 0:
        raise RuntimeError(f"nvidia-smi rc={out.returncode}: {out.stderr.strip()}")
    return [row.strip() for row in out.stdout.strip().splitlines() if row.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--hz", type=float, default=1.0)
    ap.add_argument("--max-temp", type=float, default=85.0)
    ap.add_argument("--abort-file", default=None,
                    help="touch this file when aborting on temperature")
    ap.add_argument("--stop-file", default=None,
                    help="stop sampling when this file appears")
    args = ap.parse_args()

    period = 1.0 / args.hz
    t_start = time.monotonic()
    max_seen = {0: 0.0, 1: 0.0}
    n = 0
    with open(args.out, "w", buffering=1) as fh:
        fh.write(HEADER + "\n")
        while True:
            if args.stop_file and os.path.exists(args.stop_file):
                break
            try:
                rows = sample()
            except Exception as exc:                      # noqa: BLE001
                sys.stderr.write(f"sampler: {type(exc).__name__}: {exc}\n")
                time.sleep(period)
                continue
            mono = time.monotonic() - t_start
            hot = None
            for row in rows:
                fh.write(f"{mono:.3f},{row}\n")
                cols = row.split(",")
                try:
                    gid = int(cols[0]); temp = float(cols[4])
                except (ValueError, IndexError):
                    continue
                if temp > max_seen.get(gid, 0.0):
                    max_seen[gid] = temp
                if temp >= args.max_temp:
                    hot = (gid, temp)
            n += 1
            if hot:
                if args.abort_file:
                    with open(args.abort_file, "w") as af:
                        af.write(f"thermal gid={hot[0]} temp={hot[1]}\n")
                sys.stderr.write(f"SAMPLER ABORT: gpu{hot[0]} at {hot[1]} C\n")
                sys.exit(3)
            elapsed = time.monotonic() - t_start
            sleep_for = period - (elapsed % period)
            if sleep_for > 0:
                time.sleep(sleep_for)
    print(f"sampler done: {n} iterations, peak temps {max_seen}")


if __name__ == "__main__":
    main()

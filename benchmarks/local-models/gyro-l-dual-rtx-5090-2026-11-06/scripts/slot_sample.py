#!/usr/bin/env python3
"""1 Hz llama.cpp slot-occupancy probe for the Gyro-L server.

Uses only fields the server actually returns from GET /slots:
  id, id_task, is_processing, n_ctx, n_prompt_tokens,
  n_prompt_tokens_cache, n_prompt_tokens_processed, next_token, params

Derived per slot:
  busy      = is_processing
  prefilling= is_processing and n_prompt_tokens_processed <  n_prompt_tokens
  decoding  = is_processing and n_prompt_tokens_processed >= n_prompt_tokens
  cache_tok = n_prompt_tokens_cache   (prefix-cache hit; 0 => genuine prefill)

Purpose: make "both inference slots occupied" and "prefill vs decode on the
wire" measured claims instead of assumptions.
"""
import argparse
import json
import os
import time
import urllib.request

HDR = ("elapsed_s,gap_ms,busy_slots,prefilling_slots,decoding_slots,"
       "prompt_tokens_total,processed_tokens_total,cache_tokens_total,"
       "slot_busy_mask")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8081")
    ap.add_argument("--out", required=True)
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--stop-file", default=None)
    args = ap.parse_args()

    t0 = time.monotonic()
    last = t0 * 1000.0
    with open(args.out, "w", buffering=1) as fh:
        fh.write(HDR + "\n")
        while True:
            if args.stop_file and os.path.exists(args.stop_file):
                break
            now_ms = time.monotonic() * 1000.0
            gap = now_ms - last
            last = now_ms
            try:
                with urllib.request.urlopen(args.url + "/slots", timeout=10) as r:
                    slots = json.load(r)
            except Exception as exc:  # noqa: BLE001
                name = type(exc).__name__
                fh.write(f"{time.monotonic()-t0:.3f},{gap:.0f},ERR,{name},,,,,,\n")
                time.sleep(args.interval)
                continue
            busy = prefill = decode = 0

            ptok = ptok_proc = cache = 0
            for s in slots:
                ip = bool(s.get("is_processing"))
                npr = int(s.get("n_prompt_tokens") or 0)
                npc = int(s.get("n_prompt_tokens_processed") or 0)
                npcache = int(s.get("n_prompt_tokens_cache") or 0)
                if ip:
                    busy += 1
                    if npc < npr:
                        prefill += 1
                    else:
                        decode += 1
                ptok += npr
                ptok_proc += npc
                cache += npcache
            fh.write(f"{time.monotonic()-t0:.3f},{gap:.0f},"
                     f"{busy},{prefill},{decode},{ptok},{ptok_proc},{cache},"
                     "-\n")
            time.sleep(args.interval)


if __name__ == "__main__":
    main()

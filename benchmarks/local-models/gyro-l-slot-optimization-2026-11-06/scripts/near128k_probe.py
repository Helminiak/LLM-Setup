#!/usr/bin/env python3
"""Near-128K context probe against the LIVE gyro-l 128K/1-slot instance (no restart).

Fits a real-document prompt into the 120k-126k token window using the server's own
tokenizer, sends it once at temperature 0 with thinking disabled, and records whether
a ~122k-token prompt is accepted with a correct needle answer. Reuses the corpus and
fitting helpers from ctx128k_final.py (imported, not re-implemented). Python 3 stdlib.

Usage: python3 near128k_probe.py   > results/near_128k_final_1slot.json
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)  # archive copy: scripts/ sits next to this file
sys.path.insert(1, "/home/joe/.hermes/profiles/hermes-supervisor/cache/scratch")
from ctx128k_final import BASE, fit_prompt, post  # noqa: E402

INFER_TIMEOUT = 240.0


def vram() -> dict:
    out = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.used,memory.free",
                          "--format=csv,noheader,nounits"],
                         capture_output=True, text=True, check=True).stdout
    res = {}
    for line in out.strip().splitlines():
        i, used, free = [p.strip() for p in line.split(",")]
        res[i] = {"used": int(used), "free": int(free)}
    return res


def main() -> int:
    t0 = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    before = vram()
    prompt, n_tokens = fit_prompt()
    print(f"fitted prompt: tokens={n_tokens} chars={len(prompt)}", file=sys.stderr, flush=True)
    d, wall, err = post("/v1/chat/completions", {
        "model": "gyro-l",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 48, "temperature": 0.0,
        "chat_template_kwargs": {"enable_thinking": False}}, INFER_TIMEOUT)
    after = vram()
    choices = (d or {}).get("choices", [{}])
    content = choices[0].get("message", {}).get("content", "") if choices else ""
    usage = (d or {}).get("usage", {})
    timings = (d or {}).get("timings", {})
    ptok = usage.get("prompt_tokens")
    ctok = usage.get("completion_tokens")
    prefill_ms = timings.get("prompt_ms")
    result = {
        "started_at": t0,
        "base": BASE,
        "config": {"ctx_size": 128000, "parallel": 1, "cache_type_kv": "q8_0"},
        "prompt_tokens_fitted": n_tokens,
        "prompt_chars": len(prompt),
        "ok": err is None and bool(content.strip()),
        "err": err,
        "wall_s": round(wall, 2),
        "prompt_tokens_reported": ptok,
        "completion_tokens": ctok,
        "finish_reason": choices[0].get("finish_reason") if choices else None,
        "content": content.strip()[:120],
        "needle_correct": "7391" in content,
        "prefill_tps_from_timings": (round(ptok / (prefill_ms / 1000.0), 1)
                                     if prefill_ms and ptok else None),
        "prefill_tps_from_wall": (round(ptok / wall, 1) if ptok and wall else None),
        "timings": timings,
        "vram_before": before,
        "vram_after": after,
        "min_free_mib": min(v["free"] for v in list(before.values()) + list(after.values())),
    }
    print(json.dumps(result, indent=1))
    return 0 if result["ok"] and result["needle_correct"] else 1


if __name__ == "__main__":
    sys.exit(main())

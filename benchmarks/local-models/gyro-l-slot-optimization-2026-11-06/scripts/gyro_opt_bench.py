#!/usr/bin/env python3
"""Bench one Gyro-L server config: decode t/s, prefill t/s, spec acceptance,
end-to-end latency, peak VRAM, correctness fingerprints. temp=0 so outputs are
comparable across configs (identical text => correctness preserved).

usage: gyro_opt_bench.py LABEL [outfile]
"""
import json
import subprocess
import sys
import threading
import time
import urllib.request

BASE = "http://127.0.0.1:8081"
LABEL = sys.argv[1] if len(sys.argv) > 1 else "run"
OUT = sys.argv[2] if len(sys.argv) > 2 else None

# --- representative coding workload (deterministic, temp=0) ---
DEC_TASKS = [
    ("kth-largest",
     "Write a Python function kth_largest(nums, k) that returns the k-th largest "
     "element using a heap. No prose, code only.", 260),
    ("merge-intervals",
     "Write a Python function merge_intervals(iv) that merges overlapping "
     "intervals and returns them sorted. No prose, code only.", 320),
    ("lru-cache",
     "Implement a Python LRUCache class with get/put, O(1), using OrderedDict. "
     "No prose, code only.", 380),
]

NEEDLE = "NEEDLE: EMERGENCY_CODE=7391\n\n"


def gpu():
    out = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.used,memory.free",
                          "--format=csv,noheader,nounits"],
                         capture_output=True, text=True).stdout.strip()
    return {int(x[0]): (int(x[1]), int(x[2])) for x in (l.split(", ") for l in out.splitlines())}


class Sampler(threading.Thread):
    daemon = True

    def __init__(self):
        super().__init__()
        self.stop_it = threading.Event()
        self.peak = {}

    def run(self):
        while not self.stop_it.is_set():
            for i, (u, _f) in gpu().items():
                self.peak[i] = max(self.peak.get(i, 0), u)
            time.sleep(0.4)

    def snapshot(self):
        self.stop_it.set()
        self.join(timeout=3)
        return self.peak


def post(path, payload, timeout=180):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode()), time.perf_counter() - t0


def chat(content, max_tokens):
    d, wall = post("/v1/chat/completions", {
        "model": "gyro-l",
        "messages": [{"role": "user", "content": content}],
        "max_tokens": max_tokens, "temperature": 0.0,
        "chat_template_kwargs": {"enable_thinking": False}})
    t = d.get("timings", {})
    u = d.get("usage", {})
    ch = (d.get("choices") or [{}])[0]
    return {
        "wall_s": round(wall, 3),
        "prompt_tokens": u.get("prompt_tokens"),
        "completion_tokens": u.get("completion_tokens"),
        "prefill_tps": round(u["prompt_tokens"] * 1000 / t["prompt_ms"], 1) if t.get("prompt_ms") else None,
        "decode_tps": round(u["completion_tokens"] * 1000 / t["predicted_ms"], 1) if t.get("predicted_ms") else None,
        "spec": {k: t.get(k) for k in ("draft_n", "draft_n_accept", "draft_mean_accept_len",
                                       "dec_prompt_ms", "dec_decode_ms") if k in t},
        "finish": ch.get("finish_reason"),
        "text": ch.get("message", {}).get("content", ""),
    }


def main():
    R = {"label": LABEL, "server": {}, "tasks": {}, "aggregate": {}}
    try:
        p, _ = post("/props", {}, 10)
        si, _ = post("/server_info", {}, 10)
        R["server"] = {
            "total_slots": p.get("total_slots"), "n_ctx": p.get("n_ctx"),
            "n_ctx_slot": p.get("n_ctx_slot"),
            "model_ftype": p.get("model_ftype"), "model_path": si.get("model_path"),
            "spec_type": si.get("speculative", {}).get("type") if si.get("speculative") else None,
            "spec_draft": (si.get("speculative") or {}).get("draft", {}).get("model_path"),
            "use_mlock": p.get("use_mlock"), "use_mmap": p.get("use_mmap"),
            "flash_attn": p.get("flash_attn"), "n_gpu_layers": p.get("n_gpu_layers"),
            "n_threads": p.get("n_threads"), "n_batch": p.get("n_batch"),
            "n_ubatch": p.get("n_ubatch"), "n_ctx_train": p.get("n_ctx_train"),
        }
    except Exception as e:                                  # noqa: BLE001
        R["server_error"] = f"{type(e).__name__}: {e}"

    s = Sampler()
    s.start()

    # decode throughput + correctness fingerprint
    tot_dec, tot_wall, texts = [], 0.0, {}
    for name, prompt, mt in DEC_TASKS:
        r = chat(prompt, mt)
        texts[name] = r["text"]
        tot_wall += r["wall_s"]
        if r["completion_tokens"] and r["decode_tps"]:
            tot_dec.append((r["completion_tokens"], r["decode_tps"]))
        R["tasks"][name] = {k: v for k, v in r.items() if k != "text"}
        print(f"[{LABEL}] {name}: dec={r['decode_tps']} t/s tok={r['completion_tokens']} "
              f"wall={r['wall_s']}s spec={r['spec']}", flush=True)

    # prefill probe on a real coding file (~10-25K tokens)
    pre = None
    for path in ["/home/joe/repos/LLM-Setup/benchmarks/local-models/gyro-l-dual-rtx-5090-2026-11-06/reports/load_metrics.json"]:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                big = f.read()
        except OSError:
            continue
        body = NEEDLE + big * 40
        r = chat(body + "\nQuestion: what is the EMERGENCY_CODE? Reply with only the number.", 32)
        pre = r
        R["tasks"]["prefill-probe"] = {k: v for k, v in r.items() if k != "text"}
        print(f"[{LABEL}] prefill-probe: {r['prefill_tps']} t/s on {r['prompt_tokens']} tok "
              f"(answer={r['text'].strip()[:12]!r})", flush=True)
        break

    # optional long-context probe (LONG=1); skipped by default to save load/measure time
    import os
    if os.environ.get("LONG") == "1":
        try:
            with open("/home/joe/repos/LLM-Setup/AGENTS.md", encoding="utf-8", errors="replace") as f:
                seed = f.read()
        except OSError:
            seed = "code " * 4000
        rl = chat(NEEDLE + (seed * 200)[:600_000] +
                  "\nQuestion: what is the EMERGENCY_CODE stated at the beginning? "
                  "Reply with only the number.", 24)
        R["tasks"]["long-probe"] = {k: v for k, v in rl.items() if k != "text"}
        print(f"[{LABEL}] long-probe: {rl['prompt_tokens']} tok prefill={rl['prefill_tps']} t/s "
              f"wall={rl['wall_s']}s answer={rl['text'].strip()[:12]!r}", flush=True)
    else:
        rl = {"prompt_tokens": pre["prompt_tokens"] if pre else 0,
              "prefill_tps": None, "wall_s": pre["wall_s"] if pre else 0,
              "text": pre["text"] if pre else ""}
        R["tasks"]["long-probe"] = "skipped"

    R["peak_vram_used_mib"] = {str(k): v for k, v in s.snapshot().items()}
    R["aggregate"] = {
        "decode_tps_weighted": round(sum(c for c, _ in tot_dec) /
                                     sum(c / d for c, d in tot_dec), 1) if tot_dec else None,
        "sum_decode_tokens": sum(c for c, _ in tot_dec),
        "sum_decode_wall_s": round(tot_wall, 2),
        "prefill_tps_probe": pre["prefill_tps"] if pre else None,
        "long_ctx_tokens": rl["prompt_tokens"],
        "long_ctx_prefill_tps": rl["prefill_tps"],
        "long_ctx_wall_s": rl["wall_s"],
        "needle_ok": "7391" in (pre["text"] if pre else "") or "7391" in rl["text"],
        "correctness_sha": __import__("hashlib").sha256(
            json.dumps(texts, sort_keys=True).encode()).hexdigest()[:16],
    }
    print(f"[{LABEL}] AGG {json.dumps(R['aggregate'])}", flush=True)
    if OUT:
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(R, f, indent=1)


main()

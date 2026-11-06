#!/usr/bin/env python3
"""Continuous-inference load generator for the Gyro-L dual-RTX-5090 smoke test.

Each lane issues back-to-back streaming /v1/chat/completions requests until
--duration elapses. Token counts and prefill/decode timings are taken from the
server's own usage+timings payload (stream_options.include_usage) -- never from
a locally estimated token count.

Read-only with respect to server config: sampling and KV settings are left at
their server defaults; only max_tokens and the prompt are set per request.
"""
import argparse
import glob
import json
import os
import threading
import time
import urllib.request
import uuid

CHAT = "http://127.0.0.1:8081/v1/chat/completions"


def stream_once(prompt, max_tokens, timeout=1800.0):
    body = json.dumps({
        "model": "gyro-l",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
    }).encode()
    req = urllib.request.Request(
        CHAT, data=body, headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    ttft = None
    finish = None
    usage, timings = {}, {}
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw in resp:
            if not raw.startswith(b"data: "):
                continue
            payload = raw[6:].strip()
            if payload == b"[DONE]":
                break
            obj = json.loads(payload)
            for choice in obj.get("choices", []):
                delta = choice.get("delta") or {}
                if (delta.get("content") or delta.get("reasoning_content")) \
                        and ttft is None:
                    ttft = time.perf_counter() - t0
                if choice.get("finish_reason"):
                    finish = choice["finish_reason"]
            if obj.get("usage"):
                usage = obj["usage"]
            if obj.get("timings"):
                timings = obj["timings"]
    return {
        "wall_s": time.perf_counter() - t0,
        "ttft_s": ttft,
        "finish_reason": finish,
        "usage": usage,
        "timings": timings,
    }


def lane(name, prompts, duration, max_tokens, records, lock, stop):
    """Issue requests until `duration` seconds have elapsed for this lane."""
    deadline = time.perf_counter() + duration
    i = 0
    while time.perf_counter() < deadline and not stop.is_set():
        base = prompts[i % len(prompts)]
        # uid at the head defeats prefix-cache reuse -> honest cold-prefill rate
        prompt = f"[[req uid={uuid.uuid4().hex[:8]} seq={i}]]\n{base}"
        rec = {"lane": name, "seq": i, "start_epoch": time.time(),
               "prompt_bytes": len(prompt.encode())}
        t_req = time.perf_counter()
        try:
            rec.update(stream_once(prompt, max_tokens))
        except Exception as exc:                            # noqa: BLE001
            rec["error"] = f"{type(exc).__name__}: {exc}"
            rec["wall_s"] = time.perf_counter() - t_req
        rec["end_epoch"] = time.time()
        with lock:
            records.append(rec)
        if "error" in rec:
            stop.set()
        i += 1
    with lock:
        records.append({"lane": name, "lane_end": True,
                        "requests": i, "end_epoch": time.time(),
                        "start_epoch": deadline - duration})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt-dir", required=True)
    ap.add_argument("--lanes", type=int, default=1)
    ap.add_argument("--duration", type=float, default=60.0)
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", default="run")
    ap.add_argument("--abort-file", default=None,
                    help="stop issuing if this file appears (sampler safety)")
    args = ap.parse_args()

    prompts = sorted(glob.glob(os.path.join(args.prompt_dir, "prompt_*.txt")))
    if not prompts:
        raise SystemExit(f"no prompts in {args.prompt_dir}")
    texts = []
    for p in prompts:
        with open(p, encoding="utf-8") as fh:
            texts.append(fh.read())

    records, lock, stop = [], threading.Lock(), threading.Event()

    def watch_abort():
        while not stop.is_set():
            if args.abort_file and os.path.exists(args.abort_file):
                stop.set()
                return
            time.sleep(0.5)

    watcher = threading.Thread(target=watch_abort, daemon=True)
    watcher.start()

    threads = [threading.Thread(
        target=lane,
        args=(f"lane{i}", texts, args.duration, args.max_tokens,
              records, lock, stop))
        for i in range(args.lanes)]
    t0 = time.perf_counter()
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    wall = time.perf_counter() - t0
    stop.set()

    requests = [r for r in records if "lane_end" not in r]
    errors = [r for r in requests if "error" in r]
    ok = [r for r in requests if "error" not in r]
    completion = sum(r["usage"].get("completion_tokens", 0) for r in ok)
    prompt_tok = sum(r["usage"].get("prompt_tokens", 0) for r in ok)
    cached = sum((r["usage"].get("prompt_tokens_details") or {})
                 .get("cached_tokens", 0) for r in ok)
    prompt_ms = sum((r["timings"].get("prompt_ms") or 0.0) for r in ok)
    pred_ms = sum((r["timings"].get("predicted_ms") or 0.0) for r in ok)
    cache_n = sum((r["timings"].get("cache_n") or 0) for r in ok)

    summary = {
        "label": args.label,
        "lanes": args.lanes,
        "duration_set_s": args.duration,
        "wall_s": wall,
        "requests": len(requests),
        "errors": len(errors),
        "error_detail": [e.get("error") for e in errors][:5],
        "completion_tokens": completion,
        "prompt_tokens": prompt_tok,
        "cached_tokens": cached,
        "server_prompt_ms": prompt_ms,
        "server_decode_ms": pred_ms,
        "aggregate_out_tok_per_wall_s": (completion / wall) if wall else 0.0,
        "server_decode_tok_per_s": (completion * 1000.0 / pred_ms) if pred_ms else 0.0,
        "server_prefill_tok_per_s": ((prompt_tok - cached) * 1000.0 / prompt_ms)
        if prompt_ms else 0.0,
        "cache_lookups": cache_n,
        "mean_ttft_s": (sum(r["ttft_s"] for r in ok if r.get("ttft_s"))
                        / max(1, len([r for r in ok if r.get("ttft_s")]))),
        "per_lane": {},
    }
    for ln in sorted({r["lane"] for r in requests}):
        rl = [r for r in ok if r["lane"] == ln]
        lane_wall = max((r["end_epoch"] for r in rl), default=0) - \
            min((r["start_epoch"] for r in rl), default=0)
        ctok = sum(r["usage"].get("completion_tokens", 0) for r in rl)
        ptok = sum(r["usage"].get("prompt_tokens", 0) for r in rl)
        pcm = sum((r["timings"].get("prompt_ms") or 0.0) for r in rl)
        pmm = sum((r["timings"].get("predicted_ms") or 0.0) for r in rl)
        summary["per_lane"][ln] = {
            "requests": len(rl),
            "completion_tokens": ctok,
            "prompt_tokens": ptok,
            "lane_wall_s": lane_wall,
            "out_tok_per_wall_s": (ctok / lane_wall) if lane_wall > 0 else 0.0,
            "server_decode_tok_per_s": (ctok * 1000.0 / pmm) if pmm else 0.0,
            "server_prefill_tok_per_s": (ptok * 1000.0 / pcm) if pcm else 0.0,
            "mean_request_wall_s": (sum(r["wall_s"] for r in rl) / len(rl)) if rl else 0.0,
        }

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump({"summary": summary, "requests": records}, fh, indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()

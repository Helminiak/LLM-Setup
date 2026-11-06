#!/usr/bin/env python3
"""Functional correctness check for the Gyro-L slot-optimization benchmark.

Generates each representative coding answer at temperature 0, compiles only the
`content` field (this server returns chain-of-thought separately in
`reasoning_content`), exec()s it, and runs behavioural assertions. Writes a JSON
evidence file to stdout; exit 0 only if every assertion passes. Python 3 stdlib only.

Usage: python3 verify_outputs.py [base_url] [model]   > results/verify_final_1slot.json
"""
import json
import re
import sys
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8081"
MODEL = sys.argv[2] if len(sys.argv) > 2 else "gyro-l"

# (name, prompt, max_tokens, [(label, snippet defining `result`, expected)])
TASKS = [
    ("kth-largest",
     "Write a Python function kth_largest(nums, k) that returns the k-th largest "
     "element using a heap. No prose, code only.", 600,
     [("kth of 8", "result = kth_largest([3, 1, 4, 1, 5, 9, 2, 6], 3)", 5),
      ("kth of 1", "result = kth_largest([7], 1)", 7),
      ("k out of range", "result = kth_largest([1, 2], 5)", None)]),
    ("merge-intervals",
     "Write a Python function merge_intervals(iv) that merges overlapping "
     "intervals and returns them sorted. No prose, code only.", 600,
     [("disjoint+overlap", "result = merge_intervals([(1, 3), (2, 6), (8, 10), (15, 18)])",
       [(1, 6), (8, 10), (15, 18)]),
      ("touching", "result = merge_intervals([(1, 4), (4, 5)])", [(1, 5)]),
      ("unsorted input", "result = merge_intervals([(5, 6), (1, 2), (1, 3)])",
       [(1, 3), (5, 6)])]),
    ("lru-cache",
     "Implement a Python LRUCache class with get/put, O(1), using OrderedDict. "
     "No prose, code only.", 800,
     [("eviction order",
       "c = LRUCache(2)\nc.put(1, 1)\nc.put(2, 2)\na = c.get(1)\nc.put(3, 3)\n"
       "b = c.get(2)\nc.put(4, 4)\nd1 = c.get(1)\nd2 = c.get(3)\nd3 = c.get(4)\n"
       "result = (a, b, d1, d2, d3)", (1, -1, -1, 3, 4))]),
]


def gen(prompt: str, max_tokens: int) -> dict:
    body = json.dumps({"model": MODEL, "messages": [{"role": "user", "content": prompt}],
                       "max_tokens": max_tokens, "temperature": 0}).encode()
    req = urllib.request.Request(BASE + "/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.load(r)
    m = d["choices"][0]["message"]
    return {"code": m.get("content") or "",
            "reasoning_chars": len(m.get("reasoning_content") or ""),
            "completion_tokens": d.get("usage", {}).get("completion_tokens")}


def strip_fences(text: str) -> str:
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.S)
    return "\n\n".join(blocks) if blocks else text


def norm(value):
    """Tuples and lists compare equal — a generated answer may use either."""
    if isinstance(value, (list, tuple)):
        return [norm(v) for v in value]
    return value


def main() -> int:
    results, all_ok = {}, True
    for name, prompt, mtokens, checks in TASKS:
        entry = {"passed": 0, "failed": 0, "checks": []}
        try:
            gen_res = gen(prompt, mtokens)
            code = strip_fences(gen_res["code"])
            entry.update(gen_res, code_chars=len(code))
            entry.pop("code")  # keep evidence compact; code is reproducible from prompt
            ns: dict = {}
            exec(compile(code, f"<{name}>", "exec"), ns)
            for label, snippet, expected in checks:
                try:
                    local = dict(ns)
                    exec(compile(snippet, f"<{name}:{label}>", "exec"), local)
                    got = local.get("result")
                    ok = norm(got) == norm(expected)
                except Exception as exc:  # noqa: BLE001
                    got, ok = f"{type(exc).__name__}: {exc}", False
                entry["checks"].append({"label": label, "expected": expected,
                                        "got": repr(got), "ok": ok})
                entry["passed" if ok else "failed"] += 1
        except Exception as exc:  # noqa: BLE001
            entry["error"] = f"{type(exc).__name__}: {exc}"
            entry["failed"] += 1
        results[name] = entry
        all_ok = all_ok and entry["failed"] == 0
    print(json.dumps({"model": MODEL, "base": BASE, "temperature": 0,
                      "all_passed": all_ok, "tasks": results}, indent=1))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Configure gyro-l.service for 128K / 1 slot (Q8_0 K/V) and smoke-test it.

Applies the candidate config to the EXISTING unit (only --ctx-size/--parallel
change; all other ExecStart flags are inherited verbatim), restarts systemd,
then submits a near-128K-token prompt with minimal generation. On FAIL the unit
is restored to the previous 2x64K (--ctx-size 128000 --parallel 2).
"""
import json
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request

UNIT = "/home/joe/.config/systemd/user/gyro-l.service"
BASE = "http://127.0.0.1:8081"
INFER_TIMEOUT = 120.0
TARGET_TOKENS = 121_000
MIN_FREE_MIB = 2048


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def unit_src():
    with open(UNIT, encoding="utf-8") as f:
        return f.read()


def set_unit(ctx, parallel):
    s = re.sub(r"--ctx-size \d+", f"--ctx-size {ctx}", unit_src())
    s = re.sub(r"--parallel \d+", f"--parallel {parallel}", s)
    with open(UNIT, "w", encoding="utf-8") as f:
        f.write(s)
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    return re.findall(r"--ctx-size \d+|--parallel \d+", s)


def systemd(*a, timeout=300):
    return subprocess.run(["systemctl", "--user", *a], capture_output=True,
                          text=True, timeout=timeout)


def gpu():
    out = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.used,memory.free",
                          "--format=csv,noheader,nounits"],
                         capture_output=True, text=True).stdout.strip()
    return {int(x[0]): (int(x[1]), int(x[2]))
            for x in (l.split(", ") for l in out.splitlines())}


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


def get(path, timeout=8.0):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read().decode())


def post(path, payload, timeout):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode()), time.perf_counter() - t0, None
    except urllib.error.HTTPError as e:
        return None, time.perf_counter() - t0, f"HTTP {e.code}: {e.read().decode()[:200]}"
    except Exception as e:                                     # noqa: BLE001
        return None, time.perf_counter() - t0, f"{type(e).__name__}: {e}"


def wait_healthy(deadline=300.0):
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < deadline:
        try:
            if get("/health").get("status") == "ok":
                return True, time.perf_counter() - t0
        except Exception:                                      # noqa: BLE001
            pass
        time.sleep(2)
    return False, time.perf_counter() - t0


def build_prompt():
    body = []
    for dirpath, dirnames, filenames in os_walk("/home/joe/repos/LLM-Setup"):
        dirnames[:] = [d for d in dirnames
                       if d not in (".git", "__pycache__", "node_modules")]
        for fn in sorted(filenames):
            if not fn.endswith((".py", ".md", ".json", ".txt", ".yaml", ".toml")):
                continue
            p = f"{dirpath}/{fn}"
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    t = f.read()
                if len(t) < 900_000:
                    body.append(f"### {p}\n{t}\n")
            except OSError:
                continue
    corpus = "".join(body)
    tail = ("\nQuestion: what is the value of EMERGENCY_CODE stated in the NEEDLE "
            "line at the very beginning of this document? Answer with only the number.")
    return "NEEDLE: EMERGENCY_CODE=7391\n\nReference material follows.\n\n" + corpus + tail, corpus, tail


def os_walk(root):
    import os
    return os.walk(root)


def tokenize(text):
    d, _w, err = post("/tokenize", {"content": text}, 120)
    if err:
        raise RuntimeError(err)
    return len(d["tokens"])


def fit_prompt(target_lo=120_000, target_hi=126_000, want=123_000):
    """Pad OR trim the corpus so the prompt fits inside the 1-slot 128K window."""
    prompt, corpus, tail = build_prompt()
    n = tokenize(prompt)
    head = "NEEDLE: EMERGENCY_CODE=7391\n\nReference material follows.\n\n"
    for _ in range(10):
        if target_lo <= n <= target_hi:
            break
        cpt = len(prompt) / n                      # chars per token
        need_chars = int(want * cpt) - len(tail) - len(head)
        reps = need_chars // len(corpus) + 1
        prompt = head + (corpus * reps)[:need_chars] + tail
        n = tokenize(prompt)
        log(f"fitted -> tokens={n} chars={len(prompt)}")
    return prompt, n


def main():
    R = {}
    src = unit_src()
    R["unit_before"] = {"ctx": re.search(r"--ctx-size (\d+)", src).group(1),
                        "parallel": re.search(r"--parallel (\d+)", src).group(1),
                        "kv": re.findall(r"--cache-type-[kv] \w+", src)}
    R["baseline_vram"] = {str(k): {"used": v[0], "free": v[1]} for k, v in gpu().items()}

    s = Sampler()          # covers load + both tests
    s.start()

    # any orphan llama-server on 8081 (from the earlier aborted run) is stopped
    # together with the service, then the service owns the port again.
    orphans = subprocess.run(["pgrep", "-f", r"llama-server.*--port 8081"],
                             capture_output=True, text=True).stdout.split()
    mainpid = systemd("show", "gyro-l.service", "-p", "MainPID").stdout.strip().split("=")[-1]
    kill = [p for p in orphans if p != mainpid]
    for p in kill:
        subprocess.run(["kill", p], check=False)
    R["orphan_killed"] = kill
    time.sleep(3)

    R["unit_applied"] = set_unit(128000, 1)
    log(f"unit -> {R['unit_applied']}; restarting gyro-l.service")
    systemd("restart", "gyro-l.service")
    ok, t = wait_healthy()
    R["load_s"] = round(t, 1)
    R["service_active"] = systemd("is-active", "gyro-l.service").stdout.strip()
    R["service_enabled"] = systemd("is-enabled", "gyro-l.service").stdout.strip()
    log(f"healthy={ok} in {t:.0f}s active={R['service_active']}")

    j = subprocess.run(["journalctl", "--user", "-u", "gyro-l.service", "--no-pager",
                        "-q", "--since", "-3m"], capture_output=True, text=True).stdout
    init = re.findall(r"initializing, n_slots = (\d+), n_ctx_slot = (\d+)", j)
    R["server_init"] = dict(zip(("n_slots", "n_ctx_slot"), init[-1])) if init else None
    kvbuf = re.findall(r"KV buffer size =\s+(\d+)\s+MiB", j)
    R["kv_buffer_mib"] = kvbuf[-2:] if kvbuf else None
    R["vram_after_load"] = {str(k): {"used": v[0], "free": v[1]} for k, v in gpu().items()}
    R["props"] = {k: get("/props").get(k) for k in ("total_slots", "n_ctx", "n_ctx_slot",
                                                    "use_mmap", "n_gpu_layers")}
    log(f"init={R['server_init']} kvbuf={R['kv_buffer_mib']} "
        f"free={[v[1] for v in gpu().values()]} MiB")

    # --- ONE SHORT SMOKE TEST (small prompt, real generation) ---
    ds, ws, es = post("/v1/chat/completions", {
        "model": "gyro-l",
        "messages": [{"role": "user",
                      "content": "What is 17*23? Reply with only the number."}],
        "max_tokens": 32, "temperature": 0.0,
        "chat_template_kwargs": {"enable_thinking": False}}, 60)
    tms = (ds or {}).get("timings", {})
    chs = ((ds or {}).get("choices") or [{}])[0].get("message", {}).get("content", "")
    R["short_smoke"] = {"ok": es is None, "wall_s": round(ws, 2),
                        "content": chs[:80],
                        "prompt_tokens": (ds or {}).get("usage", {}).get("prompt_tokens"),
                        "completion_tokens": (ds or {}).get("usage", {}).get("completion_tokens"),
                        "decode_tps": round((ds or {}).get("usage", {}).get("completion_tokens", 0)
                                            * 1000 / tms["predicted_ms"], 1)
                        if tms.get("predicted_ms") else None,
                        "err": es}
    log(f"short smoke = {R['short_smoke']}")

    prompt, corpus, tail = build_prompt()
    n = tokenize(prompt)
    log(f"corpus tokens={n} chars={len(prompt)}")
    guard = 0
    while n < TARGET_TOKENS and guard < 8:
        guard += 1
        cpt = len(prompt) / n
        need = int((TARGET_TOKENS + 2000 - n) * cpt)
        reps = need // len(corpus) + 1
        prompt = prompt[:-len(tail)] + (corpus * reps)[:need] + tail
        n = tokenize(prompt)
        log(f"padded -> tokens={n} chars={len(prompt)}")
    R["prompt_tokens_planned"] = n

    s = Sampler()
    s.start()
    d, wall, err = post("/v1/chat/completions", {
        "model": "gyro-l",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 48, "temperature": 0.0,
        "chat_template_kwargs": {"enable_thinking": False}}, 150.0)
    R["peak_vram_used"] = {str(k): v for k, v in s.snapshot().items()}
    if err:
        R["inference"] = {"ok": False, "err": err, "wall_s": round(wall, 1)}
    else:
        u, tm = d.get("usage", {}), d.get("timings", {})
        ch = (d.get("choices") or [{}])[0]
        R["inference"] = {
            "ok": True, "wall_s": round(wall, 1),
            "prompt_tokens": u.get("prompt_tokens"),
            "completion_tokens": u.get("completion_tokens"),
            "finish_reason": ch.get("finish_reason"),
            "content": (ch.get("message") or {}).get("content", "")[:120],
            "prompt_ms": round(tm.get("prompt_ms", 0), 1),
            "predicted_ms": round(tm.get("predicted_ms", 0), 1),
            "prefill_tps": round(u.get("prompt_tokens", 0) * 1000 / tm["prompt_ms"], 1)
            if tm.get("prompt_ms") else None,
            "decode_tps": round(u.get("completion_tokens", 0) * 1000 / tm["predicted_ms"], 1)
            if tm.get("predicted_ms") else None}
    log(f"inference={R['inference']}")

    j2 = subprocess.run(["journalctl", "--user", "-u", "gyro-l.service", "--no-pager",
                         "-q", "--since", f"-{int(R['load_s'] + wall + 30)}s"],
                        capture_output=True, text=True).stdout
    R["cuda_oom_lines"] = [l.strip()[:170] for l in j2.splitlines()
                           if re.search(r"CUDA error|out of memory|OOM|cudaMalloc|"
                                        r"GGML CUDA|GGML Assert|available context|"
                                        r"slot launch_slot", l, re.I)][:6]
    R["service_active_after"] = systemd("is-active", "gyro-l.service").stdout.strip()

    inf = R["inference"]
    free_after_load = [v["free"] for v in R["vram_after_load"].values()]
    peak_free = [32607 - v for v in R["peak_vram_used"].values()]
    worst = min(free_after_load + peak_free) if (free_after_load or peak_free) else 0
    R["min_free_mib_during_test"] = worst
    R["pass_checks"] = {
        "service_active": R["service_active"] == "active",
        "http_ok": bool(inf.get("ok")),
        "inference_within_120s": bool(inf.get("ok")) and inf.get("wall_s", 999) < INFER_TIMEOUT,
        "context_ge_120k": (inf.get("prompt_tokens") or 0) >= 120_000,
        "needle_correct": "7391" in str(inf.get("content", "")),
        "no_cuda_oom": not R["cuda_oom_lines"],
        "min_free_ge_2gib": worst >= MIN_FREE_MIB,
        "still_active_after": R["service_active_after"] == "active",
    }
    decision = "PASS" if all(R["pass_checks"].values()) else "FAIL"
    R["decided"] = decision

    if decision == "FAIL":
        R["restored_unit"] = set_unit(128000, 2)
        log(f"FAIL -> restoring previous 2x64K {R['restored_unit']}")
        systemd("restart", "gyro-l.service")
        ok3, t3 = wait_healthy()
        R["restored_load_s"] = round(t3, 1)
        R["restored_active"] = systemd("is-active", "gyro-l.service").stdout.strip()
        jj = subprocess.run(["journalctl", "--user", "-u", "gyro-l.service", "--no-pager",
                             "-q", "--since", "-2m"], capture_output=True, text=True).stdout
        i2 = re.findall(r"initializing, n_slots = (\d+), n_ctx_slot = (\d+)", jj)
        R["restored_server_init"] = dict(zip(("n_slots", "n_ctx_slot"), i2[-1])) if i2 else None

    # final state + Hermes/worker connectivity probe
    R["final_unit"] = re.findall(r"--ctx-size \d+|--parallel \d+|--cache-type-[kv] \w+",
                                 unit_src())
    R["final_active"] = systemd("is-active", "gyro-l.service").stdout.strip()
    jf = subprocess.run(["journalctl", "--user", "-u", "gyro-l.service", "--no-pager",
                         "-q", "--since", "-2m"], capture_output=True, text=True).stdout
    i3 = re.findall(r"initializing, n_slots = (\d+), n_ctx_slot = (\d+)", jf)
    R["final_server_init"] = dict(zip(("n_slots", "n_ctx_slot"), i3[-1])) if i3 else None
    d2, w2, e2 = post("/v1/chat/completions",
                      {"model": "gyro-l", "messages": [{"role": "user",
                       "content": "Reply with exactly: CONNECTIVITY_OK"}],
                       "max_tokens": 16, "temperature": 0.0,
                       "chat_template_kwargs": {"enable_thinking": False}}, 60)
    R["connectivity_probe"] = {"ok": e2 is None,
                               "content": ((d2 or {}).get("choices") or [{}])[0]
                               .get("message", {}).get("content", "")[:60],
                               "wall_s": round(w2, 1), "err": e2}
    R["final_vram"] = {str(k): {"used": v[0], "free": v[1]} for k, v in gpu().items()}
    print("SUMMARY_JSON " + json.dumps(R), flush=True)


if __name__ == "__main__":
    main()

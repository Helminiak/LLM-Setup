#!/usr/bin/env bash
# DR100 / Hermes local Qwen loader and private GitHub evidence reporter.
# Public code: Helminiak/LLM-Setup
# Private reports: Helminiak/knowledge-base (never uploads transcripts/secrets).
# Requires: bash, python3, lms, nvidia-smi; gh for private upload.
set -euo pipefail
python3 - <<'PY'
import base64, datetime as dt, json, os, pathlib, shutil, subprocess, sys, time, urllib.request

MODEL = "qwen3.8-27b-coder390-efficientthink-opus5.5-gpt6astra-grok4.7-dsv4pro-k3-sft-rloo-ninfer@q6_k"
CONTEXT = 80000
PRIVATE_REPO = "Helminiak/knowledge-base"
STAMP = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
DEST = pathlib.Path.home() / ".local/state/lmstudio-load-reports" / (STAMP + ".json")
report = {
    "schema_version": 1, "timestamp_utc": STAMP,
    "purpose": "DR100 local Hermes worker recovery baseline",
    "request": {"model": MODEL, "quantization": "Q6_K", "context_length": CONTEXT,
                "gpu_offload": "max", "parallel_target": 1},
    "stages": {}, "observed": {}, "warnings": [],
    "result": "NOT_STARTED"
}
error = None

def run(argv, timeout=150, quiet=False):
    if not quiet:
        print("+", " ".join(argv[:2]), "(parameters omitted)" if len(argv)>2 else "", flush=True)
    cp = subprocess.run(argv, text=True, capture_output=True, timeout=timeout)
    if cp.returncode:
        raise RuntimeError("{} returned exit {}: {}".format(
            argv[0] + " " + argv[1], cp.returncode,
            (cp.stderr or cp.stdout).strip()[-350:]))
    return cp.stdout.strip()

def meminfo():
    try:
        lines = pathlib.Path("/proc/meminfo").read_text().splitlines()
        kv = {}
        for ln in lines:
            parts = ln.split()
            if len(parts) >= 2 and parts[0].endswith(":"):
                kv[parts[0][:-1]] = int(parts[1]) // 1024
        return {"total_mib": kv.get("MemTotal"), "available_mib": kv.get("MemAvailable"),
                "swap_free_mib": kv.get("SwapFree")}
    except Exception:
        return {"status": "unavailable"}

def loaded():
    data = json.loads(run(["lms", "ps", "--json"], timeout=30, quiet=True))
    if not isinstance(data, list):
        raise RuntimeError("lms ps --json returned non-list")
    return [x for x in data if x.get("type") == "llm"]

def gpu():
    if not shutil.which("nvidia-smi"):
        return {"status": "nvidia-smi unavailable"}
    cp = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu",
                         "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=20)
    if cp.returncode or not cp.stdout.strip():
        return {"status": "unavailable"}
    rows = []
    for line in cp.stdout.strip().splitlines():
        vals = [s.strip() for s in line.split(",")]
        if len(vals) == 5:
            rows.append(dict(zip(("name", "total_mib", "used_mib", "free_mib", "utilization_pct"),
                                 [vals[0]] + [int(v) if v.isdecimal() else None for v in vals[1:]])))
    return {"gpus": rows}

def api_call(path, payload=None, timeout=120):
    url = "http://127.0.0.1:1234" + path
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("LM_API_TOKEN") or os.environ.get("LM_STUDIO_API_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=(json.dumps(payload).encode() if payload is not None else None),
                                 headers=headers, method=("POST" if payload is not None else "GET"))
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)

def upload_private(raw):
    if not shutil.which("gh"):
        return (False, "gh CLI not installed")
    probe = subprocess.run(["gh", "api", "repos/" + PRIVATE_REPO, "--jq", ".private"],
                           capture_output=True, text=True, timeout=25)
    if probe.returncode or probe.stdout.strip() != "true":
        return (False, "Private GitHub repo inaccessible or not confirmed private; no upload")
    rel = "reports/lmstudio/" + STAMP + ".json"
    url_path = "repos/" + PRIVATE_REPO + "/contents/" + rel
    body = json.dumps({"message": "Add sanitized LM Studio loading report " + STAMP,
                       "content": base64.b64encode(raw).decode("ascii")})
    sent = subprocess.run(["gh", "api", "--method", "PUT", url_path, "--input", "-"],
                          input=body, capture_output=True, text=True, timeout=60)
    if sent.returncode:
        return (False, "GitHub upload failed (check gh auth and repository write permission)")
    fetched = subprocess.run(["gh", "api", url_path], capture_output=True, text=True, timeout=40)
    if fetched.returncode:
        return (False, "GitHub wrote the report but readback failed")
    try:
        remote = json.loads(fetched.stdout)
        if base64.b64decode(remote["content"]) != raw:
            return (False, "GitHub readback mismatch")
    except (ValueError, KeyError):
        return (False, "GitHub readback invalid")
    return (True, "https://github.com/" + PRIVATE_REPO + "/blob/main/" + rel)

try:
    if not shutil.which("lms"):
        raise RuntimeError("lms CLI not installed or not on PATH")
    print("DR100: Qwen Q6_K, 80K, maximum GPU layer offload", flush=True)
    before = loaded()
    if any(str(x.get("status", "")).lower() != "idle" or int(x.get("queued", 0)) > 0 for x in before):
        raise RuntimeError("A model is busy or state unknown; refusing to unload while inference may be active")
    report["stages"]["preflight"] = "PASS"
    print("Estimating 80K full-GPU load...", flush=True)
    estimate = run(["lms", "load", MODEL, "--context-length", str(CONTEXT),
                    "--gpu", "max", "--estimate-only"], timeout=120, quiet=True)
    report["stages"]["estimate"] = "PASS"
    print(estimate[:1200], flush=True)
    run(["lms", "server", "start"], timeout=40)
    report["stages"]["server"] = "PASS"
    if before:
        print("Unloading idle model instances...", flush=True)
        run(["lms", "unload", "--all"], timeout=60)
    print("Loading exact Q6_K checkpoint with 80K and --gpu max...", flush=True)
    start = time.monotonic()
    run(["lms", "load", MODEL, "--context-length", str(CONTEXT), "--gpu", "max"], timeout=600)
    report["observed"]["load_elapsed_seconds"] = round(time.monotonic() - start, 2)
    report["stages"]["model_load"] = "PASS"
    entries = loaded()
    matching = [x for x in entries if x.get("identifier") == MODEL or x.get("modelKey") == MODEL]
    if len(entries) != 1 or len(matching) != 1:
        raise RuntimeError("Expected exactly one loaded Q6_K model; found different instances")
    m = matching[0]
    observed = {
        "identifier": m.get("identifier"), "quantization": (m.get("quantization") or {}).get("name"),
        "context_length": m.get("contextLength"), "max_supported_context_length": m.get("maxContextLength"),
        "parallel": m.get("parallel"), "status": m.get("status"),
    }
    report["observed"]["loaded_model"] = observed
    if observed["context_length"] != CONTEXT or str(observed["quantization"]).upper() != "Q6_K":
        raise RuntimeError("Loaded model quantization or actual allocated context does not match request")
    if observed["parallel"] not in (None, 1):
        report["warnings"].append("parallel predictions is not 1; configure in LM Studio")
    report["stages"]["verification"] = "PASS"
    try:
        obj = api_call("/api/v1/models", timeout=15)
        for item in obj.get("models", []):
            if item.get("key") == MODEL or MODEL in item.get("variants", []):
                for inst in item.get("loaded_instances", []):
                    conf = inst.get("config", {})
                    if conf.get("context_length") == CONTEXT:
                        report["observed"]["api_load_config"] = {
                            k: conf.get(k) for k in ("context_length", "eval_batch_size",
                                                       "flash_attention", "offload_kv_cache_to_gpu", "parallel")
                            if k in conf}
                        if conf.get("flash_attention") is False:
                            report["warnings"].append("Flash Attention is OFF; set per-model defaults in LM Studio")
                        if conf.get("offload_kv_cache_to_gpu") is False:
                            report["warnings"].append("GPU KV-cache offload is OFF; set per-model defaults")
                        break
    except Exception:
        report["warnings"].append("Advanced load parameters could not be confirmed via LM Studio REST API")
    print("Running a short local inference smoke test...", flush=True)
    begin = time.monotonic()
    response = api_call("/v1/chat/completions",
                        {"model": MODEL, "messages": [{"role": "user", "content": "Reply with the word OK."}],
                         "temperature": 0, "max_tokens": 128, "stream": False}, timeout=180)
    report["observed"]["inference_elapsed_seconds"] = round(time.monotonic() - begin, 2)
    report["observed"]["inference_output_tokens"] = response.get("usage", {}).get("completion_tokens")
    if not response.get("choices"):
        raise RuntimeError("Inference response had no choices")
    report["stages"]["inference_smoke"] = "PASS"
    report["result"] = "PASS"
except Exception as exc:
    error = str(exc)[:350]
    report["result"] = "FAIL"
    report["error"] = error
    print("FAIL:", error, file=sys.stderr, flush=True)
finally:
    report["observed"]["gpu"] = gpu()
    report["observed"]["system_memory"] = meminfo()
    gpu_rows = report["observed"]["gpu"].get("gpus", [])
    if gpu_rows and gpu_rows[0].get("free_mib") is not None and gpu_rows[0]["free_mib"] < 1536:
        report["warnings"].append("Less than 1.5 GiB VRAM free after model load")
    report["warnings"].append("Full GPU offload was requested using --gpu max; exact layer placement not independently measured")
    DEST.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
    DEST.write_bytes(raw)
    os.chmod(DEST, 0o600)
    print("LOCAL REPORT:", DEST, flush=True)
    ok, upload_result = upload_private(raw)
    print("PRIVATE GITHUB:", "UPLOADED" if ok else "NOT UPLOADED", upload_result, flush=True)
    print("MODEL RESULT:", report["result"], flush=True)
    if report["warnings"]:
        print("WARNINGS:", "; ".join(report["warnings"]), flush=True)
    if not ok:
        print("Report is retained locally; install/authenticate gh for private upload.", flush=True)
sys.exit(0 if report["result"] == "PASS" and ok else 2)
PY

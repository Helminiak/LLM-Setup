#!/usr/bin/env bash
# DR100 local model recovery loader (v1.0.3): GitHub profile -> verified LM Studio -> private report -> Hermes.
# Credentials and prompts NEVER enter GitHub. --setup-only skips Hermes.
set -euo pipefail
python3 - "$@" <<'PY'
import base64, datetime, getpass, hashlib, json, os, pathlib, shutil, subprocess, sys, time, urllib.request, urllib.error

HOME=pathlib.Path.home()
STATE=HOME/".local/state/dr100-lmstudio"
STATE.mkdir(parents=True,exist_ok=True)
PROFILE_URL="https://raw.githubusercontent.com/Helminiak/LLM-Setup/main/profiles/rtx5090-dr100-qwen.json"
CACHE=STATE/"profile.json"
LEDGER=STATE/"benchmark-ledger-v103.json"
TOKEN=HOME/".config/dr100-lmstudio/api-token"
REPO="Helminiak/knowledge-base"
STAMP=datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
REPORT=STATE/"reports"/(STAMP+".json")
OPTIONS=set(sys.argv[1:])
if not OPTIONS.issubset({"--setup-only","--force-tests","--no-upload"}):
    sys.exit("Usage: bash dr100-hermes-start-v1.0.3.sh [--setup-only] [--force-tests] [--no-upload]")
data={"schema_version":1,"loader":"1.0.3","run_id":STAMP,"status":"NOT_RUN",
      "checks":{},"observed":{},"warnings":[]}
model=None
auth=None

def process(argv,timeout=180,required=True):
    p=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout)
    if required and p.returncode:
        raise RuntimeError("{} exited {}; {}".format(" ".join(argv[:2]),p.returncode,(p.stderr or "")[-180:]))
    return p

def gpu():
    p=process(["nvidia-smi","--query-gpu=name,driver_version,memory.total,memory.used,memory.free,utilization.gpu","--format=csv,noheader,nounits"],timeout=15,required=False)
    if p.returncode or not p.stdout.strip():return {"status":"unavailable"}
    v=[t.strip() for t in p.stdout.splitlines()[0].split(",")]
    return dict(zip(("name","driver","total_mib","used_mib","free_mib","util_pct"),[v[0],v[1]]+[int(t) for t in v[2:]]))

def loaded():
    v=json.loads(process(["lms","ps","--json"],timeout=30).stdout)
    return [x for x in v if x.get("type")=="llm"]

def api(path,payload=None,timeout=100):
    global auth
    if auth is None:
        auth=os.environ.get("LM_API_TOKEN") or os.environ.get("LM_STUDIO_API_TOKEN") or ""
        if not auth and TOKEN.exists():
            if TOKEN.is_symlink() or TOKEN.stat().st_mode&0o077:
                raise RuntimeError("LM Studio token file must not be symlink and must have mode 0600")
            auth=TOKEN.read_text().strip()
    def request():
        headers={"Content-Type":"application/json"}
        if auth:headers["Authorization"]="Bearer "+auth
        req=urllib.request.Request("http://127.0.0.1:1234"+path,headers=headers,
                data=json.dumps(payload).encode() if payload is not None else None,
                method="POST" if payload is not None else "GET")
        # Bypass inherited proxies for local 127.0.0.1 traffic.
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req,timeout=timeout) as res:return json.load(res)
    try:
        return request()
    except urllib.error.HTTPError as exc:
        if exc.code!=401:raise RuntimeError("Local LM Studio HTTP "+str(exc.code))
        if not os.isatty(0) and not pathlib.Path("/dev/tty").exists():
            raise RuntimeError("Local LM Studio HTTP 401; set LM_API_TOKEN with a valid local token")
        print("LM Studio API requires a token. Create one under Developer > Server Settings > Manage Tokens.")
        auth=getpass.getpass("LM Studio API token (hidden input): ").strip()
        if not auth or "\n" in auth or "\r" in auth:raise RuntimeError("Empty/invalid LM Studio API token")
        try:resp=request()
        except urllib.error.HTTPError as second:
            raise RuntimeError("Local LM Studio token rejected (HTTP {})".format(second.code))
        TOKEN.parent.mkdir(parents=True,exist_ok=True)
        fd=os.open(TOKEN,os.O_CREAT|os.O_WRONLY|os.O_TRUNC,0o600)
        with os.fdopen(fd,"w") as f:f.write(auth+"\n")
        os.chmod(TOKEN,0o600)
        return resp

def private_upload(blob):
    if "--no-upload" in OPTIONS:return "DISABLED"
    if not shutil.which("gh"):return "NO_GH_CLI"
    p=process(["gh","api","repos/"+REPO,"--jq",".private"],required=False,timeout=30)
    if p.returncode or p.stdout.strip()!="true":return "PRIVATE_REPOSITORY_NOT_CONFIRMED"
    route="reports/lmstudio/"+STAMP+".json"
    payload=json.dumps({"message":"DR100 sanitized loader result "+STAMP,
                        "content":base64.b64encode(blob).decode()})
    p=subprocess.run(["gh","api","--method","PUT","repos/"+REPO+"/contents/"+route,
                      "--input","-"],input=payload,text=True,capture_output=True,timeout=60)
    if p.returncode:return "UPLOAD_FAILED"
    p=process(["gh","api","repos/"+REPO+"/contents/"+route],required=False,timeout=35)
    if p.returncode:return "UPLOADED_READBACK_FAILED"
    try:
        obj=json.loads(p.stdout)
        if base64.b64decode(obj["content"])!=blob:return "UPLOADED_READBACK_MISMATCH"
    except (ValueError,KeyError):return "UPLOADED_READBACK_INVALID"
    return "https://github.com/"+REPO+"/blob/main/"+route

try:
    print("DR100 v1.0.3: loading versioned Q6_K / 80K / maximum GPU offload")
    try:
        p=urllib.request.Request(PROFILE_URL,headers={"User-Agent":"DR100-startup"})
        with urllib.request.urlopen(p,timeout=15) as r:profile=json.load(r)
        CACHE.write_text(json.dumps(profile,indent=2)+"\n")
        data["checks"]["profile_source"]="github"
    except Exception:
        if not CACHE.exists():raise RuntimeError("Profile unavailable and no cached profile")
        profile=json.loads(CACHE.read_text())
        data["checks"]["profile_source"]="cache"
    required={"model_key","context_length","required_quantization","gpu_offload_attempts"}
    if not required.issubset(profile):raise RuntimeError("Profile missing required fields")
    model=profile["model_key"]
    if not isinstance(model,str) or not model.endswith("@q6_k"):raise RuntimeError("Unexpected model identifier")
    if profile["required_quantization"]!="Q6_K" or profile["context_length"]!=80000:
        raise RuntimeError("Profile modified outside approved recovery baseline")
    if profile.get("api_url")!="http://127.0.0.1:1234" or profile.get("private_report_repo")!=REPO:
        raise RuntimeError("Profile endpoints mismatch")
    data["profile_sha256"]=hashlib.sha256(json.dumps(profile,sort_keys=True).encode()).hexdigest()
    process(["lms","server","start"],timeout=45)
    instances=loaded()
    for x in instances:
        if x.get("status","").lower()!="idle" or x.get("queued",0):
            raise RuntimeError("Loaded model is busy; refusing interruption")
    matching=[x for x in instances if x.get("identifier")==model or x.get("modelKey")==model]
    if len(instances)!=1 or not matching or matching[0].get("contextLength")!=80000:
        print("Requesting --gpu max with context 80000")
        process(["lms","load",model,"--context-length","80000","--gpu","max","--estimate-only"],timeout=120)
        if instances:
            process(["lms","unload","--all"],timeout=75)
        process(["lms","load",model,"--context-length","80000","--gpu","max"],timeout=600)
        matching=[x for x in loaded() if x.get("identifier")==model or x.get("modelKey")==model]
    if len(matching)!=1:raise RuntimeError("Model verification failed")
    entry=matching[0]
    data["observed"]["model"]={
        "id":entry.get("identifier"),"quant":(entry.get("quantization") or {}).get("name"),
        "contextLength":entry.get("contextLength"),
        "maxContextLength":entry.get("maxContextLength"),"parallel":entry.get("parallel"),
    }
    data["observed"]["gpu"]=gpu()
    if entry.get("contextLength")!=80000 or data["observed"]["model"]["quant"]!="Q6_K":
        raise RuntimeError("Actual context or quantization mismatch")
    if entry.get("parallel")!=1:
        raise RuntimeError("LM Studio has {} parallel slots. Set Q6_K model advanced default 'Max Concurrent Predictions' to 1 and reload; no Hermes dispatch.".format(entry.get("parallel")))
    if data["observed"]["gpu"].get("free_mib",0)<1024:
        raise RuntimeError("Less than 1024 MiB GPU headroom")
    data["checks"]["load"]="PASS"
    # Confirm authenticated API before performance measurements.
    res=api("/v1/models",timeout=20)
    if not res.get("data"):raise RuntimeError("Authenticated /v1/models empty")
    data["checks"]["authenticated_api"]="PASS"
    try:
        details=api("/api/v1/models",timeout=20)
        for item in details.get("models",[]):
            if item.get("key")==model:
                for inst in item.get("loaded_instances",[]):
                    conf=inst.get("config",{})
                    if conf:
                        data["observed"]["advanced"]={k:conf[k] for k in ("flash_attention","offload_kv_cache_to_gpu","eval_batch_size","parallel") if k in conf}
    except Exception:
        data["warnings"].append("Advanced load settings not exposed: verify in LM Studio GUI")
    # Hash the actual model/config/backend/driver; reuse results only for identical setup.
    identity={"profile":data["profile_sha256"],"model":data["observed"]["model"],
              "advanced":data["observed"].get("advanced"),
              "gpu_driver":data["observed"]["gpu"].get("driver"),
              "lms_version":process(["lms","--version"],required=False,timeout=10).stdout.strip(),
              "test_suite":"DR100-LOCAL-API-1.0"}
    fp=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    data["fingerprint"]=fp
    old={}
    if LEDGER.exists():
        old=json.loads(LEDGER.read_text())
        if not isinstance(old,dict):raise RuntimeError("Invalid benchmark ledger; refusing to overwrite")
    if fp in old and old[fp].get("pass") and "--force-tests" not in OPTIONS:
        data["checks"]["benchmark"]="CACHED_PASS"
        data["benchmarks"]=old[fp]["tests"]
        print("Reusing benchmark PASS for identical configuration")
    else:
        tests={}
        for name,prompt,limit in [
            ("smoke","Return precisely READY.",128),
            ("wp002","DR100 evidence publishing has immutable completed records plus latest.json and latest-completed.json pointers. State three deterministic tests for crash recovery, idempotence and cancellation. Never claim that any tests were executed.",900)]:
            t=time.monotonic()
            obj=api("/v1/chat/completions",
                    {"model":model,"messages":[{"role":"user","content":prompt}],
                    "temperature":0.2,"max_tokens":limit,"stream":False},timeout=180)
            usage=obj.get("usage") or {}
            answers=obj.get("choices") or []
            seconds=time.monotonic()-t
            valid=bool(answers and (answers[0].get("message") or {}).get("content"))
            tests[name]={"pass_transport":valid,"elapsed_s":round(seconds,2),
                         "input_tokens":usage.get("prompt_tokens"),"output_tokens":usage.get("completion_tokens")}
            print(name, "PASS" if valid else "FAIL",round(seconds,2),"sec")
            if not valid:raise RuntimeError("Inference returned no visible content")
        data["checks"]["benchmark"]="PASS"
        data["benchmarks"]=tests
        old[fp]={"pass":True,"tests":tests,"run_id":STAMP}
        tmp=LEDGER.with_suffix(".tmp")
        tmp.write_text(json.dumps(old,sort_keys=True,indent=2)+"\n")
        os.chmod(tmp,0o600)
        os.replace(tmp,LEDGER)
    data["status"]="PASS"
except Exception as exc:
    data["status"]="FAIL"
    data["error_type"]=type(exc).__name__
    data["error"]=str(exc)[:350]
    print("FAILED:",data["error"],file=sys.stderr)
finally:
    data["observed"]["gpu_final"]=gpu() if shutil.which("nvidia-smi") else {"status":"unavailable"}
    REPORT.parent.mkdir(parents=True,exist_ok=True)
    blob=(json.dumps(data,indent=2,sort_keys=True)+"\n").encode()
    REPORT.write_bytes(blob)
    os.chmod(REPORT,0o600)
    print("Local report:",REPORT)
    print("Private GitHub:",private_upload(blob))
    print("Result:",data["status"])
if data["status"]!="PASS":sys.exit(2)
if "--setup-only" not in OPTIONS:
    if not shutil.which("hermes"):sys.exit("Model verified but 'hermes' command not found")
    print("Starting existing Hermes without editing its configuration",flush=True)
    os.execvp("hermes",["hermes"])
PY

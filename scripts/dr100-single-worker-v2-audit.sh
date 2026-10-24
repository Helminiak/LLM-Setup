#!/usr/bin/env bash
# DR100 v2.0 read-only live model inspection. No model load/unload, task dispatch, profile or SQLite writes.
set -euo pipefail
python3 - <<'PY'
import json, subprocess, urllib.request, urllib.error
from datetime import datetime, timezone
base="http://127.0.0.1:1235"
result={"utc":datetime.now(timezone.utc).isoformat(),"read_only":True,
        "expected_alias":"dr100-gsq-coder-mtp-250k","api":base}
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
for name,path in (("models","/v1/models"),("slots","/slots")):
    try:
        with opener.open(urllib.request.Request(base+path),timeout=6) as r:
            data=json.load(r)
        if name=="models":
            result["model_ids"]=[str(v.get("id","")) for v in data.get("data",[])]
            result["alias_seen"]=result["expected_alias"] in result["model_ids"]
        else:
            result["slots"]=[{"id":x.get("id"),"is_processing":x.get("is_processing"),
                              "id_task":x.get("id_task")} for x in data] if isinstance(data,list) else "unrecognized shape"
    except (OSError, ValueError, urllib.error.URLError) as e:
        result[name+"_error"]=type(e).__name__
try:
    cp=subprocess.run(["nvidia-smi","--query-gpu=index,name,memory.used,memory.total",
       "--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=8)
    result["gpu_summary"]=cp.stdout.strip().splitlines() if cp.returncode==0 else "unavailable"
except (OSError,subprocess.TimeoutExpired):
    result["gpu_summary"]="unavailable"
print(json.dumps(result,indent=2))
# This proves API visibility, not actual dispatcher/model occupancy or native Kanban ownership.
PY

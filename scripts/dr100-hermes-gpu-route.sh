#!/usr/bin/env bash
# DR100 Hermes Cloud-Supervisor / Local-GPU-Worker route: read-only audit or explicit apply.
# PUBLIC script; PRIVATE sanitized reports. Never logs API keys or local conversation content.
set -euo pipefail
python3 - "$@" <<'PY'
import base64, datetime, json, os, pathlib, shutil, subprocess, sys

ACTION=sys.argv[1] if len(sys.argv)>1 else "--audit"
if ACTION not in ("--audit","--apply"):
    sys.exit("Usage: bash dr100-hermes-gpu-route.sh [--audit|--apply]")
HOME=pathlib.Path.home()
PRIVATE="Helminiak/knowledge-base"
MODEL="qwen3.8-27b-coder390-efficientthink-opus5.5-gpt6astra-grok4.7-dsv4pro-k3-sft-rloo-ninfer@q6_k"
STAMP=datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
STATE=HOME/".local/state/dr100-lmstudio"
REPORT=STATE/"routing-reports"/(STAMP+".json")
KEYS=[
  "model.provider","model.default","model.base_url","model.context_length",
  "delegation.provider","delegation.model","delegation.base_url",
  "delegation.max_concurrent_children","delegation.max_spawn_depth",
  "delegation.fallback_providers","auxiliary.compression.provider",
  "auxiliary.compression.model","auxiliary.compression.base_url",
]
def cmd(args, timeout=25, input=None):
    return subprocess.run(args,timeout=timeout,check=False,
                          capture_output=True,text=True,input=input)
def config_get(k):
    x=cmd(["hermes","config","get",k])
    if x.returncode!=0:return None
    s=x.stdout.strip()
    if not s or s.startswith("Config key not set"):return None
    # Chosen keys are identifiers, URLs and non-secret scalars/lists only.
    return s[:200] if "\n" not in s else "[MULTILINE, NOT REPORTED]"
def config_set(k,v):
    x=cmd(["hermes","config","set",k,v])
    if x.returncode:
        raise RuntimeError("Hermes rejected config "+k+"; "+(x.stderr.strip() or "unknown")[-130:])
def config_unset(k):
    # unset an obsolete direct-endpoint override after saving a rollback copy
    x=cmd(["hermes","config","unset",k])
    if x.returncode:
        raise RuntimeError("Hermes rejected unset "+k)
def gather():
    c={k:config_get(k) for k in KEYS}
    if shutil.which("lms"):
        x=cmd(["lms","ps","--json"],timeout=30)
        if x.returncode==0:
            try:
                v=json.loads(x.stdout)
                if isinstance(v,list):
                    m=[z for z in v if z.get("type")=="llm"]
                    current=[{"model":z.get("modelKey"),"context":z.get("contextLength"),
                              "quantization":(z.get("quantization") or {}).get("name"),
                              "parallel_slots":z.get("parallel"),
                              "status":z.get("status")} for z in m]
                else:current=[{"status":"non-list lms response"}]
            except ValueError:current=[{"status":"invalid LM Studio response"}]
        else:current=[{"status":"lms unavailable"}]
    else:current=[{"status":"lms CLI not installed"}]
    if shutil.which("nvidia-smi"):
        x=cmd(["nvidia-smi","--query-gpu=name,memory.used,memory.free,utilization.gpu","--format=csv,noheader,nounits"],timeout=15)
        parts=[s.strip() for s in x.stdout.splitlines()[0].split(",")] if x.returncode==0 and x.stdout.strip() else []
        gpu=dict(zip(("name","used_mib","free_mib","util_pct"),parts)) if len(parts)==4 else {"status":"unavailable"}
    else:gpu={"status":"unavailable"}
    return {
      "config":c, "loaded_models":current,"gpu":gpu,
      "lm_token_file_present":(HOME/".config/dr100-lmstudio/api-token").is_file(),
      "lm_api_key_in_environment":bool(os.environ.get("LM_API_KEY")),
      "hermes_env_has_lm_api_key_name":(
        bool(__import__("re").search(r"(?m)^LM_API_KEY=", (HOME/".hermes/.env").read_text()))
        if (HOME/".hermes/.env").is_file() else False
      ),
    }
def upload(blob):
    if not shutil.which("gh"):return "LOCAL_ONLY: gh not installed"
    p=cmd(["gh","api","repos/"+PRIVATE,"--jq",".private"])
    if p.returncode or p.stdout.strip()!="true":
        return "LOCAL_ONLY: private repository not confirmed"
    remote="reports/lmstudio/routing/"+STAMP+".json"
    payload=json.dumps({"message":"Add sanitized DR100 Hermes GPU routing audit "+STAMP,
                        "content":base64.b64encode(blob).decode()})
    x=cmd(["gh","api","--method","PUT","repos/"+PRIVATE+"/contents/"+remote,"--input","-"],timeout=60,input=payload)
    if x.returncode:return "LOCAL_ONLY: upload failed"
    return "https://github.com/"+PRIVATE+"/blob/main/"+remote
data={"schema_version":1,"test":"DR100 Hermes local delegation route","run_id":STAMP,
      "action":ACTION,"status":"UNKNOWN","observed_before":{},"observed_after":{},"warnings":[]}
backup=None
changed=False
try:
    if not shutil.which("hermes"):raise RuntimeError("hermes command missing")
    data["observed_before"]=gather()
    if ACTION=="--apply":
        f=HOME/".hermes/config.yaml"
        if not f.is_file() or f.is_symlink():
            raise RuntimeError("Expected regular ~/.hermes/config.yaml. No changes made.")
        # Check backup availability BEFORE changes.
        backup=f.with_name("config.yaml.bak-dr100-"+STAMP)
        shutil.copy2(f,backup)
        os.chmod(backup,0o600)
        data["rollback_file_local_only"]=str(backup)
        changed=True
        # Explicitly remove direct endpoint overrides, which take precedence over provider.
        if config_get("delegation.base_url") is not None:
            config_unset("delegation.base_url")
        if config_get("delegation.api_key") is not None:
            config_unset("delegation.api_key")
        config_set("delegation.provider","lmstudio")
        config_set("delegation.model",MODEL)
        config_set("delegation.max_concurrent_children","1")
        config_set("delegation.max_spawn_depth","1")
        config_set("delegation.fallback_providers","[]")
    data["observed_after"]=gather()
    c=data["observed_after"]["config"]
    if ACTION=="--apply":
        if c["delegation.provider"]!="lmstudio" or c["delegation.model"]!=MODEL:
            raise RuntimeError("Applied routing did not round-trip to Hermes config")
        if c["delegation.base_url"] not in (None,"null","None",""):
            raise RuntimeError("Obsolete delegation.base_url still overrides named provider")
        before=data["observed_before"]["config"]
        if any(c[k]!=before[k] for k in ("model.provider","model.default","model.base_url")):
            raise RuntimeError("Supervisor route changed unexpectedly; rollback")
    data["status"]="PASS"
    if c["delegation.provider"]!="lmstudio" or c["delegation.model"]!=MODEL:
        data["warnings"].append("Delegation is NOT yet pinned to Qwen on LM Studio")
    if not (data["observed_after"]["lm_token_file_present"] or data["observed_after"]["lm_api_key_in_environment"] or data["observed_after"]["hermes_env_has_lm_api_key_name"]):
        data["warnings"].append("No known LM Studio API credential present; protected endpoint may return 401")
    if c["delegation.fallback_providers"] not in ("[]","null",None):
        data["warnings"].append("Inspect delegation fallback list; a cloud fallback could hide local worker failures")
except Exception as e:
    data["status"]="FAIL"
    data["error"]=type(e).__name__+": "+str(e)[:200]
    if changed and backup and backup.is_file():
        # Roll back only the local config file and preserve the backup.
        shutil.copy2(backup,HOME/".hermes/config.yaml")
        data["warnings"].append("Config restored from rollback copy following failure")
    print("FAIL:",data["error"],file=sys.stderr)
finally:
    STATE.mkdir(parents=True,exist_ok=True)
    REPORT.parent.mkdir(parents=True,exist_ok=True)
    blob=(json.dumps(data,indent=2,sort_keys=True)+"\n").encode()
    REPORT.write_bytes(blob)
    os.chmod(REPORT,0o600)
    print("ACTION:",ACTION,"RESULT:",data["status"])
    print("SUPERVISOR:",data["observed_after"].get("config",{}).get("model.default","unavailable"))
    print("LOCAL DELEGATION:",data["observed_after"].get("config",{}).get("delegation.provider"),
          data["observed_after"].get("config",{}).get("delegation.model"))
    print("LM STUDIO MODELS:",len(data["observed_after"].get("loaded_models",[])))
    print("LOCAL REPORT:",REPORT)
    print("PRIVATE GITHUB:",upload(blob))
    if backup and backup.is_file():print("ROLLBACK CONFIG:",backup)
    for w in data["warnings"]:print("WARNING:",w)
sys.exit(0 if data["status"]=="PASS" else 2)
PY

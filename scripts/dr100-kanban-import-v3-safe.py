#!/usr/bin/env python3
"""DR100 WP003 v3: safe nine-card registry import; all unassigned in Triage, HOLDs preserved.
Native Hermes commands only for task mutations. NO worker dispatch.
"""
import argparse, datetime, fcntl, hashlib, json, os, pathlib, shutil
import sqlite3, subprocess, sys, urllib.request

# DR100 v2: historical WP003 registry importer. Preserve --plan, but fail closed
# on --apply unless separately approved for a documented legacy rollback.
# This environment variable is NOT permission to bypass owner/dispatch gates.
if "--apply" in sys.argv and os.environ.get("DR100_ENABLE_LEGACY_KANBAN_IMPORT") != "1":
    raise SystemExit("Historical Kanban --apply disabled under DR100 v2.0. Use native Kanban task/profile reconciliation; preserve IDs, parent holds, and current RUNNING owner.")

H=pathlib.Path.home()
SLUG="dr100-engineering-control"
DB=H/".hermes/kanban/boards"/SLUG/"kanban.db"
REV="4d926765aad3929f18d6b7dc1afaaf010eb4c77b"
URL="https://raw.githubusercontent.com/Helminiak/LLM-Setup/"+REV+"/configs/dr100-kanban-import-v2.json"
STATE=H/".local/state/dr100-kanban/migrations"

def run(*parts):
    p=subprocess.run(["hermes",*map(str,parts)],text=True,capture_output=True,timeout=90)
    if p.returncode: raise RuntimeError("hermes failed: "+" ".join(map(str,parts[:4]))+" "+p.stderr[-160:])
    return p.stdout

def rows():
    with sqlite3.connect("file:"+str(DB)+"?mode=ro",uri=True,timeout=20) as c:
        columns={x[1] for x in c.execute("PRAGMA table_info(tasks)")}
        if not {"id","title","body","assignee","status","idempotency_key"}<=columns:
            raise RuntimeError("Unexpected Kanban schema; abort")
        return [dict(zip(("id","title","body","assignee","status","key"),x))
                for x in c.execute("SELECT id,title,body,assignee,status,idempotency_key FROM tasks")]

def inspect(items,allow_ready=False):
    records=rows()
    if any(r["status"]=="running" for r in records):
        raise RuntimeError("Target DR100 board has Running task; abort all imports")
    if not allow_ready and any(r["status"]=="ready" for r in records):
        raise RuntimeError("Ready card present. In dashboard move WP001 t_d7c102c3 to Triage FIRST; do not rerun v1 importer.")
    found={}
    for x in items:
        matches=[r for r in records if r["key"]==x["key"]]
        if len(matches)>1: raise RuntimeError("Duplicate key "+x["key"])
        if matches:
            r=matches[0]
            allowed=["triage"]+(["blocked"] if x["status"]=="blocked" else [])
            if allow_ready and x["status"]=="triage": allowed.append("ready")
            if r["status"] not in allowed or r["assignee"] not in (None,""):
                raise RuntimeError("Unsafe preexisting state "+x["key"])
            if r["title"]!=x["title"] or r["body"]!=x["body"]:
                raise RuntimeError("Existing card edited; refuse overwrite "+x["key"])
            found[x["key"]]=r
    return found

def back_up(out):
    dest=out/"backup"
    dest.mkdir()
    all_dbs=[]
    default=H/".hermes/kanban.db"
    if default.exists(): all_dbs.append(("default",default))
    all_dbs += [(p.parent.name,p) for p in sorted((H/".hermes/kanban/boards").glob("*/kanban.db"))]
    if not any(k==SLUG for k,p in all_dbs): raise RuntimeError("Missing DR100 DB")
    result={}
    for name,p in all_dbs:
        if p.is_symlink(): raise RuntimeError("Refuse symlink database")
        dst=dest/(name+".sqlite3")
        with sqlite3.connect("file:"+str(p)+"?mode=ro",uri=True) as src:
            with sqlite3.connect(dst) as tgt:
                src.backup(tgt)
                if tgt.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
                    raise RuntimeError("Backup failed integrity check "+name)
        dst.chmod(0o600)
        result[name]=hashlib.sha256(dst.read_bytes()).hexdigest()
    config=H/".hermes/config.yaml"
    if not config.is_file() or config.is_symlink(): raise RuntimeError("Cannot back up Hermes config")
    dst=dest/"config.yaml"
    shutil.copy2(config,dst);dst.chmod(0o600)
    result["config-local-only"]=hashlib.sha256(dst.read_bytes()).hexdigest()
    return result

def main():
    os.umask(0o077)
    parser=argparse.ArgumentParser()
    group=parser.add_mutually_exclusive_group()
    group.add_argument("--plan",action="store_true",help="Read-only migration plan (default)")
    group.add_argument("--apply",action="store_true",help="Backup then park missing cards in Triage; HOLDs remain unresolved")
    args=parser.parse_args()
    if not DB.is_file() or DB.is_symlink(): raise RuntimeError("DR100 board slug/DB missing")
    if SLUG not in run("kanban","boards","list"): raise RuntimeError("Hermes does not list target board")
    with urllib.request.urlopen(URL,timeout=25) as r: raw=r.read(50000)
    plan=json.loads(raw)
    items=plan["items"]
    expected={"dr100:issue:2","dr100:issue:3","dr100:issue:5","dr100:ops:routing",
      "dr100:ops:pushover","dr100:gate:g2b","dr100:gate:g4","dr100:gate:g5","dr100:gate:g6"}
    if plan["board_slug"]!=SLUG or {x["key"] for x in items}!=expected or len(items)!=9:
        raise RuntimeError("Unexpected manifest")
    for x in items:
        if x["status"] not in ("triage","blocked") or (x["status"]=="blocked" and not x["reason"]):
            raise RuntimeError("Unsafe manifest status")
    found=inspect(items,allow_ready=not args.apply)
    print("DR100 board:",SLUG,"; manifest commit:",REV)
    for x in items:
        old=found.get(x["key"])
        print(("EXISTS" if old else "CREATE"),x["key"],"target",x["status"])
    if not args.apply:
        if any(r["status"]=="ready" for r in rows()):
            print("ACTION REQUIRED: In dashboard move t_d7c102c3 from Ready to Triage before --apply")
        print("PLAN COMPLETE: read-only; --apply is refused while any Ready/Running card remains.")
        return
    mode=run("config","get","kanban.auto_decompose").strip().splitlines()[-1].lower()
    if mode not in ("false","0","off","no"):
        raise RuntimeError("Manual orchestration not independently confirmed")
    if any(r["key"] not in expected for r in rows()):
        raise RuntimeError("Unexpected task on DR100 board; stop and reconcile before import")
    if len(rows()) > 9:
        raise RuntimeError("Unexpected count on DR100 board; stop before import")
    STATE.mkdir(parents=True,exist_ok=True)
    with (STATE/".migrate.lock").open("w") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        stamp=datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        out=STATE/stamp
        out.mkdir()
        report={"run_utc":stamp,"board":SLUG,"manifest_commit":REV,"status":"IN_PROGRESS"}
        try:
            report["backups_sha256"]=back_up(out)
            print("CONSISTENT SQLITE BACKUPS: PASS")
            for x in items:
                old=inspect(items).get(x["key"])
                if not old:
                    run("kanban","--board",SLUG,"create",x["title"],
                        "--body",x["body"],"--priority",x["priority"],
                        "--triage","--idempotency-key",x["key"])
                    old=inspect(items).get(x["key"])
                    if not old or old["status"]!="triage" or old["assignee"] not in (None,""):
                        raise RuntimeError("Create did not remain unassigned Triage: "+x["key"])
                if x["status"]=="blocked" and old["status"]=="triage":
                    print("HOLD PARKED IN TRIAGE",x["key"],"reason:",x["reason"][:110])
                checked=inspect(items).get(x["key"])
                desired_actual="triage" if x["status"]=="triage" else checked["status"] if checked else None
                if (not checked or checked["assignee"]
                    or checked["status"] not in (["triage"] if x["status"]=="triage" else ["triage","blocked"])):
                    raise RuntimeError("Post-create safe parking check failed: "+x["key"])
                print("VERIFIED",x["key"],checked["id"],checked["status"])
            report["crosswalk"]=[{"key":x["key"],"id":inspect(items)[x["key"]]["id"],
                    "intended_status":x["status"],"actual_status":inspect(items)[x["key"]]["status"],
                    "hold_reason":x["reason"] if x["status"]=="blocked" else None}
                    for x in items]
            report["status"]="SAFE_IMPORT_PARTIAL_HOLDS"
        except Exception as e:
            report["status"]="FAIL"
            report["error"]=str(e)[:240]
            raise
        finally:
            (out/"report.json").write_text(json.dumps(report,indent=2)+"\n")
            print("LOCAL EVIDENCE:",out/"report.json")
            print("RESULT:",report["status"])
            if report["status"]=="SAFE_IMPORT_PARTIAL_HOLDS":
                try:
                    import base64
                    private="Helminiak/knowledge-base"
                    probe=subprocess.run(["gh","api","repos/"+private,"--jq",".private"],
                                         capture_output=True,text=True,timeout=30)
                    if probe.returncode==0 and probe.stdout.strip()=="true":
                        relative="reports/dr100/kanban-import/"+stamp+".json"
                        payload=json.dumps({"message":"Record verified DR100 Kanban v2 crosswalk "+stamp,
                          "content":base64.b64encode((out/"report.json").read_bytes()).decode()})
                        push=subprocess.run(["gh","api","--method","PUT",
                          "repos/"+private+"/contents/"+relative,"--input","-"],
                          input=payload,text=True,capture_output=True,timeout=60)
                        if push.returncode==0:
                            check=subprocess.run(["gh","api","repos/"+private+"/contents/"+relative],
                                      capture_output=True,text=True,timeout=40)
                            valid=check.returncode==0 and base64.b64decode(json.loads(check.stdout)["content"])==(out/"report.json").read_bytes()
                            print("PRIVATE GITHUB:",("UPLOADED+READBACK" if valid else "UPLOADED_BUT_NOT_VERIFIED"),
                                  "https://github.com/"+private+"/blob/main/"+relative)
                        else: print("PRIVATE GITHUB: upload failed; local report retained")
                    else: print("PRIVATE GITHUB: destination not confirmed private; local report retained")
                except Exception as e:
                    print("PRIVATE GITHUB: report upload unavailable ("+type(e).__name__+"); local report retained")
    print("9 cards registered. Four intended BLOCKED items remain parked in Triage pending a separately approved safe transition. No Ready or assigned workers.")
if __name__=="__main__":
    try: main()
    except Exception as e:
        print("MIGRATION STOPPED:",type(e).__name__,str(e),file=sys.stderr)
        sys.exit(2)

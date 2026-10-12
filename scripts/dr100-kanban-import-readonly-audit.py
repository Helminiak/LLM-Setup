#!/usr/bin/env python3
"""Read-only forensic inspection of failed DR100 Kanban import. NO Hermes CLI calls."""
import base64
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import datetime

HOME=Path.home()
SLUG="dr100-engineering-control"
DB=HOME/".hermes/kanban/boards"/SLUG/"kanban.db"
RUN="20261012T205751318366Z"
IMPORT=HOME/".local/state/dr100-kanban/migrations"/RUN
PRIVATE="Helminiak/knowledge-base"

def read_db(path):
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("Required regular SQLite file missing: "+str(path))
    conn=sqlite3.connect("file:"+str(path)+"?mode=ro",uri=True,timeout=20)
    conn.row_factory=sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn

def table_columns(conn,table):
    return {r[1] for r in conn.execute("PRAGMA table_info("+table+")")}

def main():
    os.umask(0o077)
    with read_db(DB) as db:
        expected={"id","title","status","assignee","idempotency_key"}
        cols=table_columns(db,"tasks")
        if not expected.issubset(cols):
            raise RuntimeError("Unexpected tasks schema; missing "+str(sorted(expected-cols)))
        optional=["worker_pid","current_run_id","created_at","claim_expires"]
        select=["id","title","status","assignee","idempotency_key"]+[x for x in optional if x in cols]
        rows=[dict(r) for r in db.execute("SELECT "+",".join(select)+" FROM tasks ORDER BY rowid")]
        runs={}
        if "task_id" in table_columns(db,"task_runs"):
            runs={r["task_id"]:r["n"] for r in db.execute(
                "SELECT task_id,COUNT(*) AS n FROM task_runs GROUP BY task_id")}
        for row in rows:
            row["run_count"]=runs.get(row["id"],0)
            if row.get("claim_expires"):
                row["claim_expires_present"]=True
                del row["claim_expires"]
        tally={}
        for row in rows:tally[row["status"]]=tally.get(row["status"],0)+1
    backup=IMPORT/"backup"
    backup_details=[]
    if backup.exists():
        for file in sorted(backup.glob("*.sqlite3")):
            try:
                with read_db(file) as conn:
                    ok=conn.execute("PRAGMA quick_check").fetchone()[0]
                backup_details.append({"board":file.stem,"check":ok,"bytes":file.stat().st_size})
            except Exception:
                backup_details.append({"board":file.stem,"check":"UNAVAILABLE"})
    previous=IMPORT/"report.json"
    prior={}
    if previous.exists():
        j=json.loads(previous.read_text())
        prior={"status":j.get("status"),"error":j.get("error"),"backup_manifest_present":bool(j.get("backups_sha256"))}
    report={"schema_version":1,"timestamp":datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "incident":"DR100 WP003 first import stopped on Ready/Running safety gate",
            "board":SLUG,"target_database_modified":False,"task_count":len(rows),
            "status_counts":tally,"cards":rows,"previous_import":prior,
            "backup_integrity":backup_details,"recommendation":"No writes authorized; review before any correction"}
    out=IMPORT/"postmortem-readonly.json"
    out.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    out.chmod(0o600)
    print("DR100 READ-ONLY TASK INVENTORY")
    for row in rows:
        print(row["id"],row["status"],"assignee="+str(row["assignee"]),
              "key="+str(row["idempotency_key"]),"runs="+str(row["run_count"]),
              "pid="+str(row.get("worker_pid")),"title="+str(row["title"])[:72])
    print("STATUS COUNTS:",tally)
    print("PREVIOUS IMPORT:",prior)
    print("BACKUPS:",backup_details)
    print("LOCAL AUDIT:",out)
    if not subprocess.run(["which","gh"],capture_output=True).returncode:
        p=subprocess.run(["gh","api","repos/"+PRIVATE,"--jq",".private"],
                         capture_output=True,text=True,timeout=25)
        if p.returncode==0 and p.stdout.strip()=="true":
            rel="reports/dr100/kanban-import/recovery-"+RUN+".json"
            payload={"message":"Record DR100 Kanban import read-only postmortem",
                     "content":base64.b64encode(out.read_bytes()).decode()}
            q=subprocess.run(["gh","api","--method","PUT",
                "repos/"+PRIVATE+"/contents/"+rel,"--input","-"],
                input=json.dumps(payload),text=True,capture_output=True,timeout=50)
            if q.returncode==0:
                print("PRIVATE GITHUB:", "https://github.com/"+PRIVATE+"/blob/main/"+rel)
            else:
                print("PRIVATE GITHUB: upload failed; local report preserved")
        else:
            print("PRIVATE GITHUB: repository not verified private; local report preserved")
    else:
        print("PRIVATE GITHUB: gh CLI not installed; local report preserved")
    print("READ-ONLY AUDIT COMPLETE; did not invoke Hermes CLI or change Kanban tasks")
if __name__=="__main__":
    try:main()
    except Exception as e:
        print("AUDIT ERROR:",type(e).__name__,str(e),file=sys.stderr)
        sys.exit(2)

#!/usr/bin/env python3
"""DR100 v2.0: READ-ONLY native Kanban queue inventory, never mutates any task."""
import json, pathlib, sqlite3, time
board=pathlib.Path.home()/".hermes/kanban/boards/dr100-engineering-control/kanban.db"
if not board.is_file():
    raise SystemExit("DR100 Kanban DB missing; no queue migration claimed")
uri=board.resolve().as_uri()+"?mode=ro"
with sqlite3.connect(uri,uri=True,timeout=8) as conn:
    conn.row_factory=sqlite3.Row
    cols={r["name"] for r in conn.execute("PRAGMA table_info(tasks)")}
    required={"id","assignee","status"}
    if not required.issubset(cols): raise SystemExit("Unknown task schema; no migration")
    chosen=[s for s in ("id","title","assignee","status","current_run_id","worker_pid","last_heartbeat_at") if s in cols]
    rows=[dict(r) for r in conn.execute("SELECT "+",".join(chosen)+" FROM tasks")]
for row in rows:
    row.pop("title",None) # avoid publishing internal task bodies/names to generic logs
    if "last_heartbeat_at" in row and row["last_heartbeat_at"] is not None:
        try: row["heartbeat_age_seconds"]=int(time.time())-int(row["last_heartbeat_at"])
        except (TypeError,ValueError): pass
print(json.dumps({"board":"dr100-engineering-control","read_only":True,
  "total_tasks":len(rows),
  "old_profile_tasks":[r for r in rows if r.get("assignee")=="qwen-worker-2"],
  "active_tasks":[r for r in rows if str(r.get("status","")).lower() in ("running","in_progress")],
  "counts_by_profile_status":{
      str(p)+"/"+str(s):sum(x.get("assignee")==p and x.get("status")==s for x in rows)
      for p,s in sorted({(x.get("assignee"),x.get("status")) for x in rows},key=lambda a:(str(a[0]),str(a[1])))
  },
  "notice":"No task modified. Do not reassign RUNNING, review-held, dependency-held or owner-gated work without native task/session reconciliation."},indent=2))

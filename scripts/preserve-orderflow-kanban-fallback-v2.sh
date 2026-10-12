#!/usr/bin/env bash
# DR100 recovery: finish a PARTIAL Orderflow archive without Git's broken --all bundle.
# Does not change git refs, task state, worker state, or shared Hermes config.
# ALL source archives stay on local disk; only redacted checksums and statuses may
# be uploaded to the PRIVATE knowledge-base repository.
set -Eeuo pipefail
umask 077
export GIT_NO_LAZY_FETCH=1

ROOT="$HOME/.local/state/dr100-recovery/t_10ea1bd5"
OUT="${1:-}"
[[ -n "$OUT" ]] || { echo "USAGE: $0 <existing partial-backup-directory>" >&2; exit 2; }
OUT="${OUT%/}"
case "$OUT" in
  "$ROOT"/*) ;;
  *) echo "STOP: backup must be under $ROOT" >&2; exit 2 ;;
esac
[[ -d "$OUT" ]] || { echo "STOP: no backup directory $OUT" >&2; exit 2; }

BASE="$HOME/.hermes/kanban/boards/orderflow-engineering/workspaces/t_d8af640b"
NATIVE="$BASE/native-proposal"
CURRENT="$HOME/.hermes/kanban/boards/orderflow-engineering/workspaces/t_10ea1bd5"

for f in orderflow-kanban.before-hold.sqlite3 repo.git.bundle repo.tracked.patch \
         repo.untracked.tar.gz repo.HEAD repo.branch repo.status \
         native-proposal.tracked.patch native-proposal.untracked.tar.gz \
         native-proposal.HEAD native-proposal.branch native-proposal.status; do
  [[ -f "$OUT/$f" ]] || { echo "STOP: missing prior preservation: $f" >&2; exit 2; }
done
[[ -s "$OUT/native-proposal.tracked.patch" ]] || { echo "STOP: native tracked patch empty"; exit 2; }

# Confirm no unexpected intervening git ref or status changes before we treat this
# full filesystem archive as complementing the earlier tracked/untracked snapshots.
[[ "$(git -C "$NATIVE" rev-parse HEAD)" == "$(cat "$OUT/native-proposal.HEAD")" ]] ||
  { echo "STOP: native-proposal HEAD changed after partial backup" >&2; exit 2; }
status_now="$(mktemp)"
trap 'rm -f "$status_now"' EXIT
git -C "$NATIVE" status --porcelain=v1 > "$status_now"
cmp -s "$status_now" "$OUT/native-proposal.status" ||
  { echo "STOP: native-proposal status changed; inspect before retry" >&2; exit 2; }

# Validate the *existing* SQLite snapshot without touching the live WAL database.
python3 - "$OUT/orderflow-kanban.before-hold.sqlite3" <<'PY'
import sqlite3,sys
with sqlite3.connect("file:"+sys.argv[1]+"?mode=ro",uri=True) as db:
    if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise SystemExit("STOP: prior SQLite snapshot failed integrity check")
print("PRIOR ORDERFLOW SQLITE BACKUP: PASS")
PY

gzip -t "$OUT/repo.untracked.tar.gz"
gzip -t "$OUT/native-proposal.untracked.tar.gz"
git -C "$BASE/repo" bundle verify "$OUT/repo.git.bundle" > "$OUT/repo.bundle-verify-fallback.txt" 2>&1 ||
  { echo "STOP: previous repo bundle failed verify" >&2; exit 2; }
echo "PRIOR PATCHES, UNTRACKED ARCHIVES AND REPO BUNDLE: PRESENT/VERIFIED"

# Capture the actual checked-out files, ignored files and .git metadata.
# This intentionally DOES NOT attempt to copy/pack the alternate object store.
# The broken full-history bundle is explicitly reported as UNAVAILABLE.
if [[ ! -f "$OUT/native-proposal.worktree.tar.gz" ]]; then
  echo "Capturing native-proposal filesystem tree (.git metadata included; no full Git history) ..."
  tar --directory="$BASE" --create --gzip \
      --file="$OUT/native-proposal.worktree.tar.gz.part" native-proposal
  mv -- "$OUT/native-proposal.worktree.tar.gz.part" "$OUT/native-proposal.worktree.tar.gz"
fi

if [[ -d "$CURRENT" ]]; then
  if [[ ! -f "$OUT/current-task-workspace.tar.gz" ]]; then
    echo "Capturing current task's own workspace ..."
    tar --directory="$(dirname "$CURRENT")" --create --gzip \
        --file="$OUT/current-task-workspace.tar.gz.part" "$(basename "$CURRENT")"
    mv -- "$OUT/current-task-workspace.tar.gz.part" "$OUT/current-task-workspace.tar.gz"
  fi
  CURRENT_PRESENT=true
else
  CURRENT_PRESENT=false
  echo "No separate current-task workspace directory was found."
fi

gzip -t "$OUT/native-proposal.worktree.tar.gz"
tar --list --gzip --file="$OUT/native-proposal.worktree.tar.gz" > /dev/null
if [[ -f "$OUT/current-task-workspace.tar.gz" ]]; then
  gzip -t "$OUT/current-task-workspace.tar.gz"
  tar --list --gzip --file="$OUT/current-task-workspace.tar.gz" > /dev/null
fi

(
  cd "$OUT"
  sha256sum orderflow-kanban.before-hold.sqlite3 \
    repo.tracked.patch repo.untracked.tar.gz repo.git.bundle \
    native-proposal.tracked.patch native-proposal.untracked.tar.gz \
    native-proposal.worktree.tar.gz \
    > SHA256SUMS.fallback
  [[ ! -f current-task-workspace.tar.gz ]] ||
    sha256sum current-task-workspace.tar.gz >> SHA256SUMS.fallback
  sha256sum -c SHA256SUMS.fallback > checksum-verification-fallback.txt
)
echo "ARCHIVES AND CHECKSUMS: PASS"

python3 - "$OUT" "$CURRENT_PRESENT" <<'PY'
import datetime,hashlib,json,pathlib,sys
out=pathlib.Path(sys.argv[1]); current=sys.argv[2]=="true"
names=["orderflow-kanban.before-hold.sqlite3","repo.tracked.patch",
  "repo.untracked.tar.gz","repo.git.bundle","native-proposal.tracked.patch",
  "native-proposal.untracked.tar.gz","native-proposal.worktree.tar.gz"]
if current: names.append("current-task-workspace.tar.gz")
checks={}
for name in names:
    p=out/name
    h=hashlib.sha256()
    with p.open("rb") as f:
        for part in iter(lambda:f.read(1024*1024),b""):
            h.update(part)
    checks[name]={"bytes":p.stat().st_size,"sha256":h.hexdigest()}
result={
  "schema_version":2,
  "purpose":"Orderflow source preservation before manual operator HOLD",
  "created_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
  "task_id":"t_10ea1bd5",
  "source_archives_uploaded":False,
  "checksum_verification":"PASS",
  "sqlite_integrity":"PASS",
  "native_proposal_full_git_history":"INCOMPLETE: missing alternate-store object; git bundle --all failed",
  "native_proposal_worktree":"ARCHIVED: working files, ignored files and local .git metadata",
  "current_task_workspace_present":current,
  "checksums":checks,
}
p=out/"manifest-fallback.json";p.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n");p.chmod(0o600)
print("LOCAL MANIFEST:",str(p))
PY

echo "LOCAL ARCHIVES: $OUT"
echo "No live database, git refs, cards, profiles, or processes were modified."
echo "IMPORTANT: native-proposal full Git history NOT backed up (broken alternate object)."
if command -v gh >/dev/null 2>&1 && \
  [[ "$(gh api repos/Helminiak/knowledge-base --jq '.private' 2>/dev/null || true)" == "true" ]]; then
  python3 - "$OUT/manifest-fallback.json" "$(basename "$OUT")" <<'PY'
import base64,json,pathlib,subprocess,sys
src=pathlib.Path(sys.argv[1]); run=sys.argv[2]
rel="reports/orderflow/recovery/"+run+"-fallback.json"
payload={"message":"Record bounded Orderflow source-preservation fallback",
         "content":base64.b64encode(src.read_bytes()).decode()}
p=subprocess.run(["gh","api","--method","PUT",
 "repos/Helminiak/knowledge-base/contents/"+rel,"--input","-"],
 input=json.dumps(payload),capture_output=True,text=True,timeout=60)
if p.returncode:
 print("PRIVATE GITHUB: sanitized manifest upload failed; local archives remain safe")
else:
 readback=subprocess.run(["gh","api","repos/Helminiak/knowledge-base/contents/"+rel,
 "--jq",".sha"],capture_output=True,text=True,timeout=45)
 if readback.returncode:
  print("PRIVATE GITHUB: upload succeeded; readback NOT verified")
 else:
  print("PRIVATE GITHUB: UPLOADED+READBACK https://github.com/Helminiak/knowledge-base/blob/main/"+rel)
PY
else
  echo "PRIVATE GITHUB: not authenticated or destination not verified; local manifest retained"
fi

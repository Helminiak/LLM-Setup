#!/usr/bin/env bash
# Preserve known Orderflow dirty worktrees and board state before native HOLD of t_10ea1bd5.
# Source archives stay LOCAL; only an archive-manifest report is sent to PRIVATE GitHub.
set -Eeuo pipefail
umask 077

BASE="$HOME/.hermes/kanban/boards/orderflow-engineering/workspaces/t_d8af640b"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)-$$"
OUT="$HOME/.local/state/dr100-recovery/t_10ea1bd5/$STAMP"
mkdir -p "$OUT"
# Online consistent SQLite snapshot: do not byte-copy a hot WAL database.
python3 - "$HOME/.hermes/kanban/boards/orderflow-engineering/kanban.db" "$OUT/orderflow-kanban.before-hold.sqlite3" <<'PY'
import pathlib, sqlite3, sys
src,dest=map(pathlib.Path,sys.argv[1:])
if not src.is_file():
    raise SystemExit("SOURCE BOARD DB MISSING — STOP")
with sqlite3.connect("file:"+str(src)+"?mode=ro",uri=True) as db:
    with sqlite3.connect(dest) as out:
        db.backup(out)
with sqlite3.connect(dest) as db:
    if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
        raise SystemExit("SQLITE SNAPSHOT INTEGRITY FAILURE — STOP")
print("CONSISTENT ORDERFLOW SQLITE BACKUP: PASS")
PY
fail() { echo "ERROR: $*" >&2; exit 2; }

for NAME in repo native-proposal; do
  DIR="$BASE/$NAME"
  [[ -d "$DIR/.git" || -f "$DIR/.git" ]] || fail "Not a Git checkout: $DIR"
  git -C "$DIR" rev-parse --is-inside-work-tree | grep -qx true || fail "Invalid checkout: $NAME"
  echo "Preserving $NAME ..."

  git -C "$DIR" rev-parse HEAD > "$OUT/$NAME.HEAD"
  git -C "$DIR" branch --show-current > "$OUT/$NAME.branch"
  git -C "$DIR" status --porcelain=v1 > "$OUT/$NAME.status"
  # git diff HEAD includes staged + unstaged changes to tracked files; --binary preserves binary diffs.
  git -C "$DIR" diff --binary HEAD > "$OUT/$NAME.tracked.patch"
  # Include all untracked non-ignored files, with GNU tar's NUL-safe filename handling.
  git -C "$DIR" ls-files --others --exclude-standard -z |
    tar --directory="$DIR" --null --files-from=- --create --gzip --file="$OUT/$NAME.untracked.tar.gz"
  # Bundle existing referenced Git history (including local-only branch commits).
  git -C "$DIR" bundle create "$OUT/$NAME.git.bundle" --all > /dev/null
  git -C "$DIR" bundle verify "$OUT/$NAME.git.bundle" > "$OUT/$NAME.bundle-verify.txt" 2>&1 ||
    fail "Git bundle verification failed for $NAME"
  echo "  HEAD $(cat "$OUT/$NAME.HEAD") branch=$(cat "$OUT/$NAME.branch")"
done

(
  cd "$OUT"
  sha256sum repo.tracked.patch repo.untracked.tar.gz repo.git.bundle \
    native-proposal.tracked.patch native-proposal.untracked.tar.gz \
    native-proposal.git.bundle orderflow-kanban.before-hold.sqlite3 > SHA256SUMS
)
(
  cd "$OUT"
  sha256sum -c SHA256SUMS > checksums-verified.txt
) || fail "Backup checksum verification FAILED"

# Manifest deliberately omits local file paths, user names, remotes, filenames and credentials.
python3 - "$OUT" "$STAMP" <<'PY'
import hashlib, json, pathlib, sys
out=pathlib.Path(sys.argv[1]); stamp=sys.argv[2]
data={"schema_version":1,"purpose":"Orderflow Kanban t_10ea1bd5 non-destructive local source preservation",
      "created_utc":stamp,"source_archives_uploaded":False,"checksums_verified":True,"components":{}}
for name in ("repo","native-proposal"):
    entry={"head":(out/(name+".HEAD")).read_text().strip(),
           "branch":(out/(name+".branch")).read_text().strip(),
           "status_entries":len((out/(name+".status")).read_text().splitlines()),
           "archives":{}}
    for kind in ("tracked.patch","untracked.tar.gz","git.bundle"):
        p=out/(name+"."+kind)
        h=hashlib.sha256()
        with p.open("rb") as source:
            for block in iter(lambda: source.read(1024*1024), b""):
                h.update(block)
        entry["archives"][kind]={"sha256":h.hexdigest(),"bytes":p.stat().st_size}
    data["components"][name]=entry
dbfile=out/"orderflow-kanban.before-hold.sqlite3"
data["database_backup"]={"sha256":hashlib.sha256(dbfile.read_bytes()).hexdigest(),
                          "bytes":dbfile.stat().st_size, "integrity_check":"ok"}
raw=(json.dumps(data,indent=2,sort_keys=True)+"\n").encode()
p=out/"manifest.json";p.write_bytes(raw);p.chmod(0o600)
PY

echo "LOCAL PRESERVATION: $OUT"
echo "FILES: manifest, verified board SQLite backup, SHA256SUMS, patches, untracked archives, Git bundles"
echo "No branches, commits, repository files, or Kanban cards were modified."
echo "Scope: two previously identified dirty worktrees; other workspaces are NOT claimed preserved."

if command -v gh >/dev/null 2>&1 &&
   [[ "$(gh api repos/Helminiak/knowledge-base --jq '.private' 2>/dev/null || true)" == "true" ]]; then
  # No code source; sanitized manifest only. Keep all content archives local.
  python3 - "$OUT/manifest.json" "$STAMP" <<'PY'
import base64,json,pathlib,subprocess,sys
src=pathlib.Path(sys.argv[1])
rel="reports/orderflow/recovery/"+sys.argv[2]+".json"
payload={"message":"Record local Orderflow Kanban recovery archive manifest",
         "content":base64.b64encode(src.read_bytes()).decode()}
p=subprocess.run(["gh","api","--method","PUT",
 "repos/Helminiak/knowledge-base/contents/"+rel,"--input","-"],
 input=json.dumps(payload),capture_output=True,text=True,timeout=60)
if p.returncode:
    print("PRIVATE GITHUB: manifest upload failed; local archives remain safe")
else:
    print("PRIVATE GITHUB MANIFEST: https://github.com/Helminiak/knowledge-base/blob/main/"+rel)
PY
else
  echo "PRIVATE GITHUB: not authenticated or private destination not verified; local manifest retained"
fi
echo "WARNING: Source archives are LOCAL ONLY, not yet pushed to any remote."

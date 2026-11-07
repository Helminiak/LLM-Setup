#!/usr/bin/env bash
# Codebreaker: Hermes Supervisor session backed by the shared Gyro-L inference
# server on 127.0.0.1:8081. Mapping, model identity and the approved dual-RTX-5090
# launch parameters are verified by a visible preflight before anything starts.
# Nothing is started on a guess: a drifted service, wrong model, competing server
# or insufficient VRAM is refused with evidence.
set -Eeuo pipefail
umask 077
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
STATE="$HOME/.local/state/codebreaker"
mkdir -p "$STATE"
LOG="$STATE/startup.log"
ACTION="${1:---launch}"

# --- Approved stable Gyro-L configuration (source of truth) -------------------
# docs/CODEBREAKER-GYRO-L-VERIFICATION-2026-11-06.md + configs/models/production-gyro-l-q8-dual5090.md
# + benchmarks/local-models/gyro-l-slot-optimization-2026-11-06/REPORT.md
MODEL_PATH="$HOME/models/gyro-l/Qwen3.8-Flash-Next-Gyro-L-abliterated-TQ3_0.gguf"
MODEL_ARCH='qwen4exp'
MODEL_NAME='Qwen3.8-Flash-Next Gyro-L abliterated'
EXEC_PATH="$HOME/src/llama-gyro/build/bin/llama-server"
BUILD_IDENTITY='build 11377, commit 9aa51ce4f'
SERVICE='gyro-l.service'
HINDSIGHT_SERVICE='hindsight.service'
HOST='127.0.0.1'
PORT=8081
BASE="http://${HOST}:${PORT}"
CTX=128000
SLOTS=1
free_mib=()
names=()
pid_list=()
# Gyro-L q8 KV residency on the approved split (from the production record).
RESERVE_MIB=28672
EXPECT_ARGV=(
  -m "$MODEL_PATH"
  --alias gyro-l
  --n-gpu-layers 999
  --split-mode layer
  --tensor-split 0.975,1.025
  --flash-attn on
  --ngram-on-disk
  --ctx-size "$CTX"
  --cache-type-k q8_0
  --cache-type-v q8_0
  --parallel 1
  --jinja
  --temp 1.0
  --top-p 0.95
  --top-k 20
  --min-p 0.05
  --host "$HOST"
  --port "$PORT"
)
# ----------------------------------------------------------------------------

notify_error() {
  local msg="$1"
  printf '[Codebreaker] %s\n' "$msg" | tee -a "$LOG" >&2
  if command -v zenity >/dev/null 2>&1 && [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
    zenity --error --title='Codebreaker startup failed' --width=700 --text="$msg\n\nDetails: $LOG" || true
  elif command -v notify-send >/dev/null 2>&1; then notify-send 'Codebreaker startup failed' "$msg" || true; fi
}
fail() { notify_error "$*"; exit 1; }
wait_http() {
  local url="$1" seconds="$2" test="$3" start now body
  start=$(date +%s)
  while :; do
    body="$(curl -fsS --connect-timeout 2 --max-time 3 "$url" 2>/dev/null || true)"
    if [[ "$test" == gyro && "$body" == *'"status":"ok"'* ]]; then return 0; fi
    if [[ "$test" == hindsight && "$body" == *'"status":"healthy"'* && "$body" == *'"database":"connected"'* ]]; then return 0; fi
    now=$(date +%s)
    (( now - start < seconds )) || return 1
    sleep 2
  done
}
log() { printf '[Codebreaker] %s\n' "$*" | tee -a "$LOG"; }
: > "$LOG"

port_pids() {
  # PIDs listening on $1 (TCP, any owner) from the socket table.
  ss -ltnp 2>/dev/null | tr -c '[:print:]\n' ' ' | sed -n '2,$p' \
    | grep -E ":$1\b" | sed -E 's/.*pid=([0-9]+),.*/\1/' | sort -un
}

server_pids() { pgrep -x llama-server || true; }

argv_of() { tr '\0' ' ' <"/proc/$1/cmdline" 2>/dev/null || true; }

flag_of() { # argv flag value
  local a
  while [[ $# -gt 1 ]]; do
    a="$1"; shift
    [[ "$a" == "--$2" || "$a" == "$2" ]] && { echo "$3"; return 0; }
  done
  return 1
}

preflight() {
  local -a argv port_pids_here owner_ok wrong_model p
  log "Preflight: CodeBreaker mapping -> $SERVICE @ $BASE"
  [[ "$(realpath -- "$MODEL_PATH" 2>/dev/null || true)" == "$MODEL_PATH" ]] \
    || fail "Model path is not the confirmed Gyro-L identity: $MODEL_PATH"
  [[ "$(realpath -- "$EXEC_PATH" 2>/dev/null || true)" == "$EXEC_PATH" ]] \
    || fail "Executable is not the approved Gyro-L build path: $EXEC_PATH"
  case "$EXEC_PATH" in
    *llama-gyro-coder*|*llama.cpp*) fail "Refusing non-Gyro-L executable: $EXEC_PATH" ;;
  esac

  # Lightweight file identity check. Runtime `/props` later verifies the loaded
  # model path; do not use a partial GGUF parser that can misread newer metadata.
  local gguf_magic
  gguf_magic="$(head -c 4 "$MODEL_PATH" 2>/dev/null || true)"
  [[ "$gguf_magic" == "GGUF" ]] || fail "Model file is not a GGUF: $MODEL_PATH"
  [[ "$(basename -- "$MODEL_PATH")" == "Qwen3.8-Flash-Next-Gyro-L-abliterated-TQ3_0.gguf" ]] \
    || fail "Model filename is not the confirmed CodeBreaker identity: $MODEL_PATH"
  log "Model identity: GGUF magic and confirmed CodeBreaker filename verified"

  local build
  build="$("$EXEC_PATH" --version 2>&1 | grep -aE 'build [0-9]+, commit' | head -1 || true)"
  [[ "$build" == *"$BUILD_IDENTITY"* ]] \
    || fail "Executable build identity mismatch: got '$build' expected '$BUILD_IDENTITY'"
  log "Build identity: $build"

  local unit exec_line
  unit="$(systemctl --user cat "$SERVICE" 2>/dev/null || true)"
  exec_line="$(printf '%s\n' "$unit" | grep -a '^ExecStart=' | head -1 || true)"
  [[ -n "$exec_line" ]] || fail "$SERVICE has no ExecStart; mapping is unresolved"
  exec_line="${exec_line#ExecStart=}"
  argv=("$exec_line")
  argv=("${argv[@]:-}")
  local -a got_argv
  got_argv=()
  local tok
  for tok in ${exec_line#*"$EXEC_PATH" }; do got_argv+=("$tok"); done
  local i
  (( ${#got_argv[@]} == ${#EXPECT_ARGV[@]} )) \
    || { printf '[Codebreaker] service argv: %s\n' "${got_argv[*]}" >&2
         printf '[Codebreaker] approved argv: %s\n' "${EXPECT_ARGV[*]}" >&2
         fail "$SERVICE argv does not match the approved Gyro-L configuration (see configs/models/production-gyro-l-q8-dual5090.md); refusing to launch on a drifted service"; }
  for i in "${!EXPECT_ARGV[@]}"; do
    [[ "${got_argv[$i]}" == "${EXPECT_ARGV[$i]}" ]] \
      || fail "$SERVICE argv drift at position $i: '${got_argv[$i]}' != '${EXPECT_ARGV[$i]}'"
  done
  log "Service mapping verified: $SERVICE runs the confirmed Gyro-L GGUF with the approved flag set"
  systemctl --user is-enabled --quiet "$SERVICE" \
    || fail "$SERVICE is disabled; the mapping would never come up"

  # Port ownership: who holds 8081, judged by actual process argv.
  pid_list=(); for p in $(port_pids "$PORT"); do pid_list+=("$p"); done
  if (( ${#pid_list[@]} == 0 )); then
    log "Port $PORT: no owner (nothing to reuse, nothing to evict)"
  else
    for p in "${pid_list[@]}"; do
      local a; a="$(argv_of "$p")"
      [[ "$a" == *"$EXEC_PATH"* && "$a" == *"$MODEL_PATH"* ]] \
        || fail "Port $PORT is held by pid $p with a different identity: $a"
      log "Port $PORT: owned by pid $p running the confirmed Gyro-L GGUF"
    done
  fi

  # Wrong-model guard: any live server already serving the Gyro-L GGUF must be on $PORT.
  wrong_model=()
  for p in $(server_pids); do
    local a; a="$(argv_of "$p")"
    [[ "$a" == *"$MODEL_PATH"* ]] || continue
    local pv; pv="$(flag_of $a --port -p x >/dev/null 2>&1; true)"
    pv="$(printf '%s\n' "$a" | sed -E 's/.*--port([= ])([0-9]+).*/\2/; s/.*(^| )-p([= ])([0-9]+).*/\3/; ' )"
    [[ "$pv" == "$PORT" ]] || wrong_model+=("$p:$pv")
  done
  (( ${#wrong_model[@]} == 0 )) \
    || fail "The Gyro-L GGUF is already served by a competing server: ${wrong_model[*]} (refusing)"

  # Active servers on other ports: recorded as consumers, never touched.
  local other='' p a pv alias
  for p in $(server_pids); do
    a="$(argv_of "$p")"; [[ "$a" == *"$MODEL_PATH"* ]] && continue
    pv="$(printf '%s\n' "$a" | sed -E 's/.*--port([= ])([0-9]+).*/\1/; s/.*(^| )-p([= ])([0-9]+).*/\1/')"
    [[ "$pv" != "$PORT" && "$pv" != "$a" ]] || continue
    alias="$(printf '%s\n' "$a" | sed -E 's/.*--alias([= ])([^\ ]+).*/\1/')"
    other="${other}  pid=$p port=$pv alias=${alias:-?}\n"
  done
  if [[ -n "$other" ]]; then
    log "Active non-Gyro-L servers (consumers; never stopped by Codebreaker):"
    printf '[Codebreaker] %b' "$other" >>"$LOG"
    printf '[Codebreaker] %b' "$other"
  fi
  local route
  for route in "$HOME/.hermes/profiles/qwen-worker/config.yaml" "$HOME/.hermes/profiles/hermes-supervisor/config.yaml"; do
    [[ -f "$route" ]] || continue
    printf '[Codebreaker] %s routes: %s\n' "$route" "$(grep -aoE 'http://127\.0\.0\.1:[0-9]+' "$route" | sort -un | tr '\n' ' ')" | tee -a "$LOG"
  done

  # GPU mapping + residency needed to hold Gyro-L on the approved split.
  command -v nvidia-smi >/dev/null 2>&1 || fail 'nvidia-smi is unavailable; GPU reserve could not be verified.'
  free_mib=()
  names=()
  mapfile -t free_mib < <(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits 2>>"$LOG") || fail 'Could not read GPU memory.'
  mapfile -t names < <(nvidia-smi --query-gpu=name --format=csv,noheader 2>>"$LOG") || fail 'Could not read GPU names.'
  (( ${#free_mib[@]} == 2 )) || fail 'Expected exactly two visible GPUs for the dual-5090 mapping.'
  local g
  for g in "${names[@]}"; do [[ "$g" == *"5090"* ]] || fail "Visible GPU is not an RTX 5090: $g"; done
  for i in 0 1; do
    [[ "${free_mib[$i]}" =~ ^[0-9]+$ ]] || fail "GPU $i free memory reading is invalid."
  done
  nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader 2>>"$LOG" \
    | sed -E 's/^/[Codebreaker] gpu-app: /' | tee -a "$LOG" || true
  log "GPRT: ${names[*]} free=${free_mib[0]}/${free_mib[1]} MiB; Gyro-L needs >=${RESERVE_MIB} MiB free per GPU"
}

gpu_can_host() {
  local i
  for i in 0 1; do (( free_mib[i] >= RESERVE_MIB )) || return 1; done
  # No other llama-server may hold VRAM while Gyro-L is not resident: they share both GPUs.
  local p a
  for p in $(server_pids); do
    a="$(argv_of "$p")"; [[ "$a" == *"$MODEL_PATH"* ]] && continue
    return 1
  done
  return 0
}

runtime_identity() {
  CTX="$CTX" SLOTS="$SLOTS" BASE="$BASE" MODEL_NAME="$MODEL_NAME" python3 - <<'PY'
import json, os, urllib.request
base = os.environ["BASE"]; name = os.environ["MODEL_NAME"]
p = json.load(urllib.request.urlopen(base + "/props", timeout=5))
s = json.load(urllib.request.urlopen(base + "/slots", timeout=5))
assert p.get("model_alias") == "gyro-l", p.get("model_alias")
assert p.get("model_path") == os.path.expanduser("~") + "/models/gyro-l/Qwen3.8-Flash-Next-Gyro-L-abliterated-TQ3_0.gguf", p.get("model_path")
assert p.get("total_slots") == int(os.environ["SLOTS"]), p.get("total_slots")
assert len(s) == int(os.environ["SLOTS"]) and all(x.get("n_ctx") == int(os.environ["CTX"]) for x in s), [x.get("n_ctx") for x in s]
print(f"props/slots ok: alias={p.get('model_alias')} slots={p.get('total_slots')} n_ctx={s[0].get('n_ctx')} model={p.get('model_path')}")
PY
}

minimal_inference() {
  curl -sS --connect-timeout 3 --max-time 60 "$BASE/completions" \
    -H 'application/json' 2>/dev/null >/dev/null || true
  local out
  out="$(curl -sS --connect-timeout 3 --max-time 90 "$BASE/completions" -H 'application/json' -d '{
    "model": "gyro-l", "prompt": "Reply with one word:", "max_tokens": 4, "temperature": 0
  }' 2>&1)" || fail "Minimal inference request failed: $out"
  printf '%s' "$out" | grep -q '"content"' || fail "Minimal inference returned no completion field: $out"
  log "Minimal inference: $BASE/completions produced a completion"
}

case "$ACTION" in
  --preflight)
    preflight
    log "Preflight complete: mapping validated; no services started or stopped."
    exit 0
    ;;
esac

preflight

if [[ "$ACTION" == --check ]]; then
  if (( ${#pid_list[@]} > 0 )); then
    wait_http "$BASE/health" 20 gyro || fail "Gyro-L on $PORT unhealthy"
    log "Runtime identity: $(runtime_identity)"
    log "Check: mapping validated against a live Gyro-L server."
  else
    log "Check: mapping validated; Gyro-L is not currently resident on $PORT."
  fi
  exit 0
fi

[[ "$ACTION" == --launch || "$ACTION" == --session ]] || fail 'Usage: codebreaker-launch.sh [--preflight|--check|--launch|--session]'

if (( ${#pid_list[@]} == 0 )); then
  if ! gpu_can_host; then
    notify_error "CodeBreaker functional validation BLOCKED: Gyro-L is not resident on $BASE and cannot be started right here. GPU free=${free_mib[0]}/${free_mib[1]} MiB but the approved dual-5090 Gyro-L config needs >=${RESERVE_MIB} MiB free per GPU; active consumers hold the VRAM (see gpu-app/consumer lines above). Hermes dispatch routes are listed above. Not stopping or restarting any model service; mapping preflight only."
    exit 3
  fi
  if ! systemctl --user is-active --quiet "$SERVICE"; then
    log "Starting inactive $SERVICE (idempotent systemd start)."
    systemctl --user start "$SERVICE" >>"$LOG" 2>&1 || fail "Could not start $SERVICE."
    log "PRE_TEST_STATE: $SERVICE was inactive; left running after the successful test (systemd-managed, nothing else was touched)."
  fi
fi
wait_http "$BASE/health" 300 gyro || fail "Gyro-L did not become healthy within 300 seconds."
wait_http "http://${HOST}:8888/health" 60 hindsight \
  || { systemctl --user is-active --quiet "$HINDSIGHT_SERVICE" || fail 'Hindsight is not running and could not be reached.'; fail 'Hindsight did not report a healthy database within 60 seconds.'; }
log "Runtime identity: $(runtime_identity)"
minimal_inference
log "Ready: Gyro-L one ${CTX}-token slot on $BASE; Hindsight eng healthy; free VRAM ${free_mib[0]}/${free_mib[1]} MiB."

if [[ "$ACTION" == --session ]]; then
  lock="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/codebreaker-supervisor.lock"
  exec 9>"$lock"
  flock -n 9 || { log 'Supervisor already has an active Codebreaker session.'; exit 0; }
  command -v hermes >/dev/null 2>&1 || fail 'Hermes CLI is unavailable in this desktop session.'
  log 'Starting Hermes Supervisor with its existing hermes-supervisor profile.'
  set +e
  hermes -p hermes-supervisor chat --tui
  rc=$?
  set -e
  if (( rc != 0 )); then
    notify_error "Hermes Supervisor exited with status $rc. Check the Hermes profile and startup log at $LOG."
  fi
  exit "$rc"
fi

command -v hermes >/dev/null 2>&1 || fail 'Hermes CLI is unavailable in this desktop session.'
command -v gnome-terminal >/dev/null 2>&1 || fail 'GNOME Terminal is required to open the interactive Supervisor session.'
lock="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/codebreaker-supervisor.lock"
if ! flock -n "$lock" true; then
  log 'An interactive Codebreaker Supervisor session is already running; reusing it.'
  exit 0
fi
log 'Opening one Hermes Supervisor terminal; DR100 launcher and dispatch checks are not part of Codebreaker startup.'
gnome-terminal --wait --title='Codebreaker — Hermes Supervisor' -- "$HOME/.local/bin/codebreaker-launch" --session >>"$LOG" 2>&1 || fail 'Could not open the Hermes Supervisor terminal. Check GNOME Terminal and the startup log.'

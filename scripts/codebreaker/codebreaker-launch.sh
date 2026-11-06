#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
STATE="$HOME/.local/state/codebreaker"
mkdir -p "$STATE"
LOG="$STATE/startup.log"
ACTION="${1:---launch}"
notify_error() {
  local msg="$1"
  printf '[Codebreaker] %s\n' "$msg" | tee -a "$LOG" >&2
  if command -v zenity >/dev/null 2>&1 && [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
    zenity --error --title='Codebreaker startup failed' --width=650 --text="$msg\n\nDetails: $LOG" || true
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
for unit in gyro-l.service hindsight.service; do
  if ! systemctl --user is-active --quiet "$unit"; then
    log "Starting inactive required service $unit (idempotent systemd start)."
    systemctl --user start "$unit" >>"$LOG" 2>&1 || fail "Could not start $unit."
  else log "Reusing active $unit."; fi
done
wait_http http://127.0.0.1:8081/health 300 gyro || fail 'Gyro-L did not become healthy within 300 seconds.'
wait_http http://127.0.0.1:8888/health 60 hindsight || fail 'Hindsight did not report a healthy database within 60 seconds.'
python3 - <<'PY' >>"$LOG" 2>&1 || fail 'Gyro-L slot or model identity does not match the accepted profile.'
import json,urllib.request
base='http://127.0.0.1:8081'
p=json.load(urllib.request.urlopen(base+'/props',timeout=5))
s=json.load(urllib.request.urlopen(base+'/slots',timeout=5))
assert p.get('model_alias')=='gyro-l',p.get('model_alias')
assert p.get('total_slots')==2,p.get('total_slots')
assert p.get('default_generation_settings',{}).get('n_ctx')==64000
assert len(s)==2 and all(x.get('n_ctx')==64000 for x in s)
PY
if ! grep -Fq 'http://127.0.0.1:8081/v1' "$HOME/.hermes/profiles/hermes-supervisor/config.yaml" || ! grep -Fq 'http://127.0.0.1:8888/mcp/eng/' "$HOME/.hermes/profiles/hermes-supervisor/config.yaml"; then
  fail 'Hermes Supervisor configuration does not point to Gyro-L and the eng Hindsight bank.'
fi
for n in 1 2; do
  cfg="$HOME/.hermes/profiles/gyro-worker-$n/config.yaml"
  [[ -f "$cfg" ]] || fail "Gyro-L worker $n profile is missing."
  grep -Fq 'http://127.0.0.1:8081/v1' "$cfg" || fail "Gyro-L worker $n endpoint is incorrect."
  grep -Fq 'http://127.0.0.1:8888/mcp/eng/' "$cfg" || fail "Gyro-L worker $n Hindsight route is missing."
  [[ -x "$HOME/.local/bin/codebreaker-worker-$n" ]] || fail "Gyro-L worker $n launcher is missing or not executable."
done
command -v hermes >/dev/null 2>&1 || fail 'Hermes CLI is unavailable in this desktop session.'
if ! command -v nvidia-smi >/dev/null 2>&1; then fail 'nvidia-smi is unavailable; GPU reserve could not be verified.'; fi
mapfile -t free_mib < <(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits 2>>"$LOG") || fail 'Could not read GPU memory.'
[[ ${#free_mib[@]} -eq 2 ]] || fail 'Expected exactly two visible GPUs.'
for i in 0 1; do
  [[ "${free_mib[$i]}" =~ ^[0-9]+$ ]] || fail "GPU $i free memory reading is invalid."
  (( free_mib[$i] >= 2048 )) || fail "GPU $i has less than 2048 MiB free; no worker was started."
done
log "Ready: Gyro-L slots=2 x 64000; Hindsight eng healthy; worker profiles 1 and 2 available; free VRAM ${free_mib[0]}/${free_mib[1]} MiB."
if [[ "$ACTION" == --check ]]; then exit 0; fi
[[ "$ACTION" == --launch || "$ACTION" == --session ]] || fail 'Usage: codebreaker-launch.sh [--check|--launch]'
lock="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/codebreaker-supervisor.lock"
if [[ "$ACTION" == --session ]]; then
  exec 9>"$lock"
  flock -n 9 || { log 'Supervisor already has an active Codebreaker session.'; exit 0; }
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
if ! flock -n "$lock" true; then
  log 'An interactive Codebreaker Supervisor session is already running; reusing it.'
  exit 0
fi
command -v gnome-terminal >/dev/null 2>&1 || fail 'GNOME Terminal is required to open the interactive Supervisor session.'
log 'Opening one Hermes Supervisor terminal; DR100 launcher and dispatch checks are not part of Codebreaker startup.'
gnome-terminal --wait --title='Codebreaker — Hermes Supervisor' -- "$HOME/.local/bin/codebreaker-launch" --session >>"$LOG" 2>&1 || fail 'Could not open the Hermes Supervisor terminal. Check GNOME Terminal and the startup log.'

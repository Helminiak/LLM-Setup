#!/usr/bin/env bash
# DR100 interactive start: preserves Hermes cloud supervisor, injects LM Studio token
# to child workers, validates the configured route, then runs existing v1.0.5 loader.
set -euo pipefail
MODEL="qwen3.8-27b-coder390-efficientthink-opus5.5-gpt6astra-grok4.7-dsv4pro-k3-sft-rloo-ninfer@q6_k"
REPO="https://raw.githubusercontent.com/Helminiak/LLM-Setup/main/scripts"
LOCAL="$HOME/.local/state/dr100-lmstudio/bin"
mkdir -p "$LOCAL"
if ! command -v hermes >/dev/null || ! command -v lms >/dev/null; then
  echo "Hermes or LM Studio CLI missing" >&2; exit 3
fi
get_config() { hermes config get "$1" 2>/dev/null || :; }
PROVIDER="$(get_config delegation.provider)"
WORKER="$(get_config delegation.model)"
if [[ "$PROVIDER" != "lmstudio" || "$WORKER" != "$MODEL" ]]; then
  echo "Hermes local delegation not configured. Run dr100-hermes-gpu-route.sh --audit then --apply." >&2
  exit 4
fi
TOKEN="$HOME/.config/dr100-lmstudio/api-token"
if [[ -f "$TOKEN" ]]; then
  if [[ -L "$TOKEN" ]]; then echo "Token file is a symlink; refusing" >&2; exit 5; fi
  PERM="$(stat -c %a "$TOKEN")"
  if [[ "$PERM" != "600" && "$PERM" != "400" ]]; then
    echo "Token file must be mode 0600 or 0400" >&2; exit 6
  fi
  export LM_API_KEY
  LM_API_KEY="$(< "$TOKEN")"
fi
# Existing Hermes .env LM_API_KEY will be honored by Hermes if environment lacks it.
# No secret appears in CLI arguments, logs, GitHub, or terminal.
curl -fLsS "$REPO/dr100-hermes-start-v1.0.5.sh" -o "$LOCAL/dr100-hermes-start-v1.0.5.sh"
echo "DR100: launching cloud supervisor with LM Studio Q6_K as delegated worker"
exec bash "$LOCAL/dr100-hermes-start-v1.0.5.sh" "$@"

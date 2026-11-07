#!/usr/bin/env bash
set -euo pipefail
umask 077
repo="$(cd "$(dirname "$0")/../.." && pwd)"
state="$HOME/.local/state/sol-parallel"
mkdir -p "$state/backups" "$HOME/.local/bin" "$HOME/.config/sol-engineering"
stamp="$(date -u +%Y%m%dT%H%M%S%N)"
for target in "$HOME/.local/bin/sol-engineering" "$HOME/.config/sol-engineering/default.json"; do
  if [[ -e "$target" || -L "$target" ]]; then cp -a "$target" "$state/backups/$(basename "$target").$stamp"; fi
done
ln -sfn "$repo/scripts/codebreaker/sol-engineering" "$HOME/.local/bin/sol-engineering"
ln -sfn "$repo/configs/parallel-engineering.json" "$HOME/.config/sol-engineering/default.json"
printf 'Installed dedicated default: sol-engineering (Codex SOL, medium). No service or model startup changes.\n'

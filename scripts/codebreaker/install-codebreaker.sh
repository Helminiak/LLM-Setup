#!/usr/bin/env bash
set -Eeuo pipefail
repo="$(cd -- "$(dirname -- "$0")/../.." && pwd)"
provider=openai-compatible

profile_root="$HOME/.hermes/profiles"
workers="$HOME/.local/bin"
launcher="$workers/codebreaker-launch"
icon_dir="$HOME/.local/share/icons/hicolor/scalable/apps"
conflicts=("$launcher" "$workers/codebreaker-worker-1" "$workers/codebreaker-worker-2" "$icon_dir/codebreaker.svg" "$HOME/Desktop/Codebreaker.desktop" "$HOME/.local/share/applications/codebreaker.desktop")
for target in "${conflicts[@]}"; do
  if [[ -e "$target" ]]; then echo "Refusing to overwrite existing $target" >&2; exit 2; fi
done
command -v hermes >/dev/null || { echo 'Hermes CLI is required' >&2; exit 2; }

# Provision worker profiles; existing worker configurations must already match.
for n in 1 2; do
  port=$((8081+n))
  model="gyro-coder-l-gpu$((n-1))"
  dir="$profile_root/gyro-worker-$n"
  if [[ -f "$dir/config.yaml" ]]; then
    grep -Fq "http://127.0.0.1:$port/v1" "$dir/config.yaml" && grep -Fq 'http://127.0.0.1:8888/mcp/eng/' "$dir/config.yaml" || { echo "Existing $dir/config.yaml has unexpected routes; refusing to modify it" >&2; exit 2; }
    continue
  fi
  mkdir -p "$dir"
  HERMES_HOME="$dir" hermes config set model.default "$model" >/dev/null
  HERMES_HOME="$dir" hermes config set model.provider "$provider" >/dev/null
  HERMES_HOME="$dir" hermes config set model.openai_runtime auto >/dev/null
  HERMES_HOME="$dir" hermes config set model.base_url "http://127.0.0.1:$port/v1" >/dev/null
  HERMES_HOME="$dir" hermes config set model.api_mode chat_completions >/dev/null
  HERMES_HOME="$dir" hermes config set "providers.$provider.name" "$model" >/dev/null
  HERMES_HOME="$dir" hermes config set "providers.$provider.base_url" "http://127.0.0.1:$port/v1" >/dev/null
  HERMES_HOME="$dir" hermes config set "providers.$provider.model" "$model" >/dev/null
  HERMES_HOME="$dir" hermes config set "providers.$provider.context_length" 65536 >/dev/null
  HERMES_HOME="$dir" hermes config set "providers.$provider.api_mode" chat_completions >/dev/null
  HERMES_HOME="$dir" hermes config set mcp_servers.hindsight_eng.url http://127.0.0.1:8888/mcp/eng/ >/dev/null
done
mkdir -p "$workers" "$icon_dir" "$HOME/.local/share/applications" "$HOME/Desktop"
install -m 0755 "$repo/scripts/codebreaker/codebreaker-launch.sh" "$launcher"
for n in 1 2; do
  cat > "$workers/codebreaker-worker-$n" <<EOF
#!/usr/bin/env bash
set -euo pipefail
if [[ \$# -lt 1 || ! -d \$1 ]]; then echo 'Usage: codebreaker-worker-$n /path/to/worktree [Hermes chat options...]' >&2; exit 2; fi
workdir=\$(realpath -- "\$1"); shift
export PATH="\$HOME/.local/bin:\$PATH"
exec hermes -p gyro-worker-$n chat --in "\$workdir" "\$@"
EOF
  chmod 0755 "$workers/codebreaker-worker-$n"
done
install -m 0644 "$repo/scripts/codebreaker/codebreaker.svg" "$icon_dir/codebreaker.svg"
cat > "$HOME/Desktop/Codebreaker.desktop" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=Codebreaker
Comment=Start or reuse Gyro-L and Hindsight, then open Hermes Supervisor
Icon=codebreaker
Exec=$launcher --launch
Terminal=false
Categories=Development;
StartupNotify=true
EOF
chmod 0755 "$HOME/Desktop/Codebreaker.desktop"
install -m 0755 "$HOME/Desktop/Codebreaker.desktop" "$HOME/.local/share/applications/codebreaker.desktop"
if command -v gio >/dev/null 2>&1; then gio set "$HOME/Desktop/Codebreaker.desktop" metadata::trusted true 2>/dev/null || true; fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true; fi
printf 'Installed Codebreaker. The launcher reuses the shared server; worker sessions are separate profiles and worktrees.\n'
printf 'Native DR100 Kanban dispatch configuration is not modified.\n'

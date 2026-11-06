# Codebreaker and shared Gyro-L platform verification

Status is separated into observed runtime checks and startup restrictions.

## Verified working

- `gyro-l.service` and `hindsight.service` were both `enabled` and `active`. Hindsight had `Restart=on-failure`; the user systemd manager had linger enabled. The Codebreaker readiness check reused both active services and did not restart them.
- Gyro-L `/health` returned HTTP 200. `/props` reported alias `gyro-l`, two slots, and 64,000 tokens per slot. `/slots` reported two idle slots after testing.
- Hindsight `/health` returned `healthy` with its database `connected`. The `eng` bank was reachable. Through a Hermes Gyro-L worker profile, the configured `hindsight_eng` MCP server performed a read-only recall and returned the stored Gyro-L endpoint (`127.0.0.1:8081`) and alias (`Gyro-L Abliterated`). No memory-bank writes were made.
- Two concurrent API coding requests completed correctly. Separate Hermes profiles `gyro-worker-1` and `gyro-worker-2` then ran concurrently in separate temporary worktrees, created code and tests via their terminal tool, and passed independent test execution (2/2).
- During the brief benchmark, free VRAM never fell below 3,732 MiB on GPU 0 or 4,212 MiB on GPU 1, above the 2,048 MiB minimum. No extra llama-server process was created.
- `scripts/codebreaker/codebreaker-launch.sh --check` passed. It validates both required services, the Hermes Gyro-L and Hindsight route configuration, the exact two-slot context shape, and GPU free-memory reserve before proceeding.

## Codebreaker launcher

`scripts/codebreaker/install-codebreaker.sh` installs the Ubuntu desktop application **Codebreaker**, a local SVG icon, and two callable worker commands. The desktop entry is non-terminal; the launcher opens one GNOME Terminal for the interactive Supervisor. It starts a required unit only if inactive, waits up to 300 seconds for Gyro-L and 60 seconds for Hindsight, verifies both 64K slots and GPU reserve, then runs `hermes -p hermes-supervisor chat --tui` directly. It does not invoke the DR100 launcher or inspect/change its guard, queue, gateway, or dispatch state. An active Codebreaker session is reused rather than duplicated. The two callable profiles use the existing loopback Gyro-L endpoint and Hindsight `eng` bank; workers can be invoked in isolated worktrees with `codebreaker-worker-1 /path/to/worktree` and `codebreaker-worker-2 /path/to/worktree`. The native DR100 Kanban dispatch remains `[qwen-worker]` under its unchanged single-worker policy.

Both user services are enabled for automatic user-manager startup; linger is enabled. Startup failures are written to `~/.local/state/codebreaker/startup.log` and shown through a desktop error dialog when available. Existing compression, model-server settings, Hindsight banks, project configs, and cloud routes are unchanged.

## Direct launch verification (2026-11-06)

Activated the installed desktop entry through `gtk-launch codebreaker`. It reused both healthy services, opened the titled GNOME Terminal, and left the Supervisor TUI process running on its terminal (`pts/0`) with `hermes-supervisor` selected. A one-shot request through that profile called Hindsight `eng` recall and returned the configured endpoint and alias. Concurrent one-shot inference through `codebreaker-worker-1` and `codebreaker-worker-2` returned their respective expected markers. Repeated readiness verification still showed one model server and two slots; no DR100 guard, queue, gateway, dispatch, or project configuration was changed.

## Rollback

Remove `~/Desktop/Codebreaker.desktop`, `~/.local/share/applications/codebreaker.desktop`, the `codebreaker` icon under the local hicolor icon directory, `~/.local/bin/codebreaker-launch`, and `~/.local/bin/codebreaker-worker-{1,2}`. The launcher did not install or alter services; the already-enabled model and Hindsight services remain separately managed by systemd. Worker profiles are isolated under the user's Hermes profile directory.

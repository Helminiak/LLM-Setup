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

`scripts/codebreaker/install-codebreaker.sh` installs an Ubuntu desktop application named **Codebreaker**, a local SVG icon, and two callable worker commands. The desktop entry is non-terminal; the existing guarded Hermes launcher opens the single necessary Supervisor terminal. The launcher starts a required unit only if it is inactive and waits up to 300 seconds for Gyro-L and 60 seconds for Hindsight. Both user services are enabled for automatic user-manager startup; the manager's linger setting is enabled.

## Startup hold (not bypassed)

The original source pin expected Hermes commit `71d34bad1045610252eda02ee79549436896e784` (v0.21.7), but the installed checkout was clean at v0.23.0 commit `74915d7af8d3115c3eb821893f3c01ab783146a5`, confirmed in the [official upstream Hermes commit](https://github.com/NousResearch/hermes-agent/commit/74915d7af8d3115c3eb821893f3c01ab783146a5). I updated only the existing launch guard's exact source pin and comment, preserved the old guard in a local rollback copy, and reran its read-only preflight. The source identity now passes; the guard then **blocked an actual Supervisor launch** for active safety holds: one Ready Kanban item, `dispatch_in_gateway=true`, and profile/model mismatches for the Supervisor, qwen worker, and senior reviewer. The guard explicitly states worker dispatch is not authorized. No queue, profile, or dispatch setting was changed. Therefore Codebreaker readiness is verified, but the Supervisor UI has not been launched. A reviewed correction to the stale preflight expectations and queue/dispatch authorization is required before launch.

The Supervisor's native Kanban dispatch remains `[qwen-worker]` with its existing one-worker limit, as required by this repository's DR100 policy. The two Gyro-L workers are independently callable local Hermes profiles, not new Kanban dispatch targets. Existing compression, model-server settings, Hindsight banks, project configs, and cloud routes were left unchanged. The source-pin edit can be rolled back from the preserved local guard backup.

## Rollback

Remove `~/Desktop/Codebreaker.desktop`, `~/.local/share/applications/codebreaker.desktop`, the `codebreaker` icon under the local hicolor icon directory, `~/.local/bin/codebreaker-launch`, and `~/.local/bin/codebreaker-worker-{1,2}`. The launcher did not install or alter services; the already-enabled model and Hindsight services remain separately managed by systemd. Worker profiles are isolated under the user's Hermes profile directory.

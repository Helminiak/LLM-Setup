# Llamactl Control Center — durable worker checkpoint

**Status:** P0 COMPLETE — read-only baseline gate PASS (runtime reconciled with prior work)
**Active phase:** next is P1 (launcher/GUI tooling); P0 evidence published
**Execution owner:** Local worker on 5090FE (Sol supervising)
**Last updated:** 2026-11-10 (P0 audit executed live)
**Master issue:** https://github.com/Helminiak/LLM-Setup/issues/10
**Runbook:** [README](../docs/llamactl-control-center/README.md)
**P0 manifest:** [P0-BASELINE-2026-11-10.md](../docs/llamactl-control-center/P0-BASELINE-2026-11-10.md)

## Verified current system facts (revalidated live on 2026-11-10)
- Host `5090FE`, user `joe`, Wayland session, 694 GB free on the 1.9 TB NVMe root, 2x RTX 5090, driver 595.99.02.
- Llamactl **v0.23.0** live: user unit `llamactl.service` enabled+active since 2026-11-09, listening on
  `127.0.0.1:19090` only, management auth required (`401` without key, `200` with key from a local key file
  exported as `LLAMACTL_MGMT_KEY` by the unit's wrapper script). Binary `~/.local/opt/llamactl/v0.23.0/llamactl`.
- State/config still in the dated staging dir `~/.local/state/llamactl-staging-20261109`
  (`llamactl.yaml`, `data/llamactl.db`, empty `data/logs/`, stray `recovered/default-db-created-by-help.db`).
- Instance pool configured `19091-19150`, `auto_create_dirs: true`, auto-restart and on-demand start **false**,
  `idle_timeout: 30`. Node `main` is declared but has no address.
- **Managed instances = 0** confirmed twice: API `GET /api/v1/instances` -> `[]` and read-only SQLite
  (`instances` 0 rows, `api_keys` 0, `key_permissions` 0, `server_secrets` 1).
- Models defect reproduced: `GET /api/v1/models` returns only two HuggingFace-cache validation entries and
  **no GGUF**, while `~/models` holds 19 GGUF files (full inventory deferred to P2). `/mnt/llm` holds no GGUF.
- External, Llamactl-UNMANAGED, healthy and protected: `local-qwen.service` -> `127.0.0.1:8082`
  (dual-5090 layer-split Qwen3.8-Flash-Next GSQ-RCO IQ3_XXS, ctx 128000, 1 slot, `/health` 200);
  `hindsight-extract-llm.service` -> `127.0.0.1:8091` (Qwen3-4B Q4, CPU-only, `/health` 200);
  `qwen-tailnet-fwd.service` socat tailscale `8083 -> 8082`. `dr100-model.service` (historical `:1235`)
  is inactive/static and `:1235` is not listening. Ports 8082/8091/8083 and the current GPU split are occupied.
- Native capability: no `/api/v1/profiles` (`404`); full lifecycle routes exist
  (`instances/{name}/start|stop|restart|logs|proxy`), plus `models`, `models/download`, `models/jobs`,
  `nodes/{name}/health`, `backends/llama-cpp/{version|devices|help|parse-command}`,
  `llama-cpp/{node}/models` + `load|unload`. Instance options include `models_dir`; binary honors
  `LLAMACTL_INSTANCES_DIR`, `LLAMACTL_MAX_INSTANCES`, `LLAMACTL_LLAMACPP_COMMAND|ARGS|ENV`,
  `LLAMACTL_DATABASE_PATH`, `HUGGINGFACE_HUB_CACHE`. => profiles must become Llamactl instance definitions;
  the GGUF blind spot looks like configuration, not a missing feature (prove in P2).
- Launcher verified present: wrapper `~/.local/bin/llamactl-control-center` (health precheck + zenity message +
  Chrome app mode, dedicated profile dir, `--class=LlamactlControlCenter`); trusted executable desktop entry on
  `~/Desktop` (2026-11-10), older duplicate from 2026-11-09, legacy `Icon=chromium` entry parked as
  `Llamactl Control Center.desktop.bak-20261110`. A Chrome app window for the dashboard was live during the
  audit and dashboard assets returned `200`.
- Still missing: entry in `~/.local/share/applications` (not launchable from app grid), `wmctrl`, `xdotool`.

## Phase checkpoint
- Completed issue: https://github.com/Helminiak/LLM-Setup/issues/11 — **P0 gate PASS**, evidence comment posted.
- Done: identity/OS/GPU/storage, service + unit ownership and argv, listener and auth behavior, managed-instance
  count (API + DB), model-catalog defect reproduced, external inference roles and health, launcher/desktop/icon
  state, repo/working-tree reconciliation, rollback backup.
- Not done / explicitly UNVERIFIED: on-screen GUI acceptance, `llamactl` CLI surface (bare `--help` hung 180 s and
  was terminated; no stray process left), whether `models_dir` can expose the GGUF library.
- Acceptance: PASS (read-only baseline; live runtime reconciled with prior claims). No production restart occurred.
- Blocking decision: none.
- **Next exact action (P1, issue #12):** install `wmctrl` + `xdotool`; verify window class `LlamactlControlCenter`
  is actually mapped on this Wayland/XWayland session; install a Llamactl entry in
  `~/.local/share/applications/` pointing at the existing wrapper (do not replace the wrapper); capture GUI evidence.

## Files/commits changed
- Repo (branch `feat/llamactl-control-center`, worktree `~/repos/LLM-Setup-worktrees/llamactl-control-center`):
  added `docs/llamactl-control-center/P0-BASELINE-2026-11-10.md`, updated this checkpoint. No runtime file edited.
- Local rollback backup: `~/.local/state/llamactl-baseline-backup-20261110/` (service unit, wrapper, both desktop
  entries, icon, `llamactl.yaml`, legacy desktop) + `MANIFEST.sha256`. Key file, logs and DB excluded.
- Untouched: `~/repos/LLM-Setup` working tree (unrelated uncommitted work on `feat/parallel-engineering-default`).

## Evidence references
- P0 evidence comment on issue #11 (commands + status codes); manifest above.

## Claude escalations
None. No blocker met the escalation gate.

## Resumption procedure
1. Read runbook, this state file, and the active phase issue only.
2. Revalidate live state before acting (`llamactl.service` active, `:19090` listener, external 8082/8091 health).
3. Continue from "Next exact action"; update this file and the issue before compaction or stopping.
4. Protected throughout: `local-qwen.service`, `hindsight-extract-llm.service`, `qwen-tailnet-fwd.service`,
   ports 8082/8091/8083, GPU split, model weights, management key. No Llamactl instance has been created or started.

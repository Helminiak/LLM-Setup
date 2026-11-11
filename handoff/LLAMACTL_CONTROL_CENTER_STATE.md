# Llamactl Control Center — durable worker checkpoint

**Status:** ACTIVE — P0, P1 and P2 gates PASS; P3 is the next phase
**Active phase:** P3 (#14) — recover verified launch profiles (not started)
**Execution owner:** Local worker on 5090FE (Sol supervising)
**Last updated:** 2026-11-10 (after P2 acceptance + operator login confirmed)
**Master issue:** https://github.com/Helminiak/LLM-Setup/issues/10
**Runbook:** [README](../docs/llamactl-control-center/README.md)
**P0 manifest:** [P0-BASELINE-2026-11-10.md](../docs/llamactl-control-center/P0-BASELINE-2026-11-10.md)
**Completed phases:** P0 #11 (PASS), P1 #12 (PASS), P2 #13 (PASS 2026-11-10)

## Verified current system facts
- Host `5090FE`, user `joe`, `Linux 7.0.0-43-generic`, **native Wayland** session (`wayland-0`, `XDG_SESSION_TYPE=wayland`), XWayland also live (`DISPLAY=:0`, `/tmp/.X11-unix/X0|X1`), `xrandr` 6144x3456 on HDMI-1. 694 GB free. 2x RTX 5090, driver 595.99.02.
- Llamactl **v0.23.0**: user unit `llamactl.service` enabled+active (MainPID 196673), `ExecStart=~/.local/state/llamactl-staging-20261109/run-llamactl.sh` (exports `LLAMACTL_MGMT_KEY` from a local key file + `LLAMACTL_CONFIG_PATH`), binary `~/.local/opt/llamactl/v0.23.0/llamactl`, listener `127.0.0.1:19090` only. Unauthenticated API → `401`; with Bearer key → `200`.
- Config: instance pool `19091-19150`, `auto_create_dirs: true`, `auto_restart: false`, `on_demand_start: false`, `idle_timeout: 30`, backends llama-cpp (`llama-server`, docker off)/vllm/mlx, `local_node=5090FE-llamactl-validation`, node `main` has no address.
- **Managed instances = 0** (API `[]` and SQLite `instances` 0 rows; `api_keys` 0, `key_permissions` 0, `server_secrets` 1). Nothing has ever been started by Llamactl.
- Models defect (scope corrected by P2): `GET /api/v1/models` → **2** Llamactl HF download-cache rows only (`cross-encoder/ms-marco-MiniLM-L-6-v2`, `intfloat/multilingual-e5-small`), no GGUF. The real library sits under `~/models`, which is a **symlink to `/mnt/llm/models`** — the earlier "`/mnt/llm` holds none" note was wrong. P2 counts: 21 logical artifacts / 23 GGUF files / 14 runnable LLMs / 570.0 GiB.
- External/protected and healthy: `local-qwen.service` → `127.0.0.1:8082` (dual-5090 layer split Qwen3.8-Flash-Next GSQ-RCO IQ3_XXS, ctx 128000, 1 slot, `/health` 200); `hindsight-extract-llm.service` → `127.0.0.1:8091` (Qwen3-4B Q4, CPU); `qwen-tailnet-fwd.service` socat `8083→8082`. `dr100-model.service` (`:1235`) inactive/static. Do not touch these.
- Native capability: **no `/api/v1/profiles` (404)**; full instance lifecycle routes exist (`instances/{name}/start|stop|restart|logs|proxy`), plus `models`, `models/download`, `models/jobs`, `nodes/{name}/health`, `backends/llama-cpp/{version|devices|help|parse-command}`, `llama-cpp/{node}/models` + `load|unload`. Instance options include `models_dir`; binary honors `LLAMACTL_INSTANCES_DIR`, `LLAMACTL_MAX_INSTANCES`, `LLAMACTL_LLAMACPP_COMMAND|ARGS|ENV`, `LLAMACTL_DATABASE_PATH`, `HUGGINGFACE_HUB_CACHE`.
- Launcher verified working end-to-end: `~/Desktop/Llamactl Control Center.desktop` (trusted, Exec/TryExec → `~/.local/bin/llamactl-control-center`) → wrapper health precheck on `:19090` (zenity/notify-send fallback) → `google-chrome --app=http://127.0.0.1:19090 --user-data-dir=~/.config/llamactl-control-center --class=LlamactlControlCenter`.
- **The Control Center window is native Wayland** (Chrome `--ozone-platform=wayland`): it is absent from `xwininfo -root -tree` and `_NET_CLIENT_LIST`, so **`wmctrl`/`xdotool` cannot see it**. Use the installed compositor/AX facility (`computer_use` `list_windows`/`capture`) instead. `org.gnome.Shell.Eval` is disabled and `org.gnome.Shell.Screenshot` is Access denied; no screenshot CLI is installed.
- No vision model on this host (`image input is not supported … provide the mmproj`) → GUI evidence must be window-system + page-load + rendered-DOM based, not pixel reading.
- **UI auth gate — RESOLVED by operator 2026-11-10:** the operator logged in in the launched window with the existing management key; dashboard renders Instances / Models / Nodes / Create Instance / model controls, so authentication is **not** a blocker. Confirmed visually that the Models tab shows only the 2 HF cache rows (matches `GET /api/v1/models`). Session auth is browser-session based (`whoami` still `authenticated:false` for a raw Bearer call). No key reset, no auth change, no credential exposure. Login alone does **not** prove model discovery/registration or one-click loading works.

## Phase checkpoint
- **P0 #11 — PASS.** Evidence: https://github.com/Helminiak/LLM-Setup/issues/11#issuecomment-6784608202
- **P1 #12 — PASS.** Evidence: https://github.com/Helminiak/LLM-Setup/issues/12#issuecomment-6784762554
- **P2 #13 — PASS (2026-11-10).** Evidence: https://github.com/Helminiak/LLM-Setup/issues/13#issuecomment-6785509542 · report `docs/llamactl-control-center/P2-INVENTORY-2026-11-10.md` · issue #13 closed · master checklist ticked through P2.
  - `gio launch` exit 0 → new app window appeared (window_id 130212167681); `SIGTERM` to the app instance closed it; relaunch gave `pid 2033606`, `window_id 133274402816`, title `Llamactl Dashboard`, `off_screen=false`, frame `(0,0,1521,1708)`.
  - Service log proves the window loaded the app: `GET / 200`, `/assets/index-DrdvaW8y.css 200`, `/assets/index-BfM6bn_m.js 200 (636213B)`, `/api/v1/auth/whoami 200`.
  - Parked (owner credential): `sudo -n true` → "interactive authentication is required", so `wmctrl 1.07+git20240228…` / `xdotool 1:3.20160805…` are **not installed** (nothing installed/upgraded). Not required for this target.
- Still UNVERIFIED: `llamactl` CLI surface (bare `--help` hung 180 s, terminated; no stray process); whether a `models_dir`-driven instance actually lists the GGUF library (only schema/binary evidence so far — proving it needs an instance start, i.e. P5 owner authorization); no entry in `~/.local/share/applications` (app-grid launch) — deferred to P7 handoff.
- Blocking decision: **P4/P5 library-exposure path** (per-instance `models_dir`+`preset.ini` router mode vs pointing `HUGGINGFACE_HUB_CACHE` at the existing cache) changes Control Center configuration and needs an explicit owner decision. Nothing else blocks P3.
- **P2 result (gate PASS, exact counts):** 21 logical artifacts (19 GGUF artifacts = 16 single + 3 complete split sets, 4 files in `~/.lmstudio/models`; 2 HF snapshot dirs), 23 GGUF files, 0 safetensors dirs, 14 runnable LLMs, 4 sidecar/projector-only, 5 incomplete, 2 unsupported, 12 unconfigured, 2 running, 0 duplicate pairs, 0 warnings, 16 symlink aliases + 4 cross-root aliases collapsed, 612,092,837,436 bytes (570.0 GiB) = home_models 524.7 GiB + lmstudio 44.8 GiB + hf_hub 0.52 GiB. Determinism: 3 stable scans → sha256 `e2e2262fc20fab16fef4a47840153e7fef9db88f962e81a1690edef93979ff80`. 15/15 fixture tests OK. Filesystem snapshot before/after over all four roots (143 entries) identical.
- **Next exact action (P3, issue #14):** harvest existing launch settings read-only — `local-qwen.service` and `hindsight-extract-llm.service` unit text + live `argv` (`-m`, ctx, batch, `--tensor-split`/`--device`, flash-attn, MTP/speculative, slot/health flags), the retired `dr100-model`/`8081`/`8083` history, `configs/models/production-gyro-l-q8-dual5090.md`, benchmark records and `llama-server --help` — then define the versioned profile schema (inventory-ID → profile mapping), with round-trip serialization, path validation, unsupported-flag rejection and secret redaction tests. No instance start/stop, no unit rewrite.

## Files/commits changed
- Repo branch `feat/llamactl-control-center` (worktree `~/repos/LLM-Setup-worktrees/llamactl-control-center`), also on `main`: `4e8883a` = P0 manifest + checkpoint, `5346007` = P1 evidence + checkpoint, P2 = inventory code/tests/schema + `docs/llamactl-control-center/P2-INVENTORY-2026-11-10.md`. No runtime file modified since P0 baseline.
- Local rollback backup: `~/.local/state/llamactl-baseline-backup-20261110/` (+ `MANIFEST.sha256`): service unit, wrapper, both desktop entries, icon, `llamactl.yaml`, legacy desktop entry. Key file, logs and DB excluded.
- Untouched: `~/repos/LLM-Setup` working tree (unrelated uncommitted work on `feat/parallel-engineering-default`).

## Evidence references
- P0: issue #11 comment 6784608202; `docs/llamactl-control-center/P0-BASELINE-2026-11-10.md`.
- P1: issue #12 comment 6784762554; composited screenshot `~/.hermes/profiles/hermes-supervisor/cache/images/computer_use_ccbfe1db2f9e4617b8a4049f17df6ac2.png` (retention limited ~24 h).

## Claude escalations
None. P2's hard cases (GGUF value-type enum, HF snapshot/blob alias double-count, module-export vs standalone classification) were resolved locally with fixtures and header evidence. No blocker met the escalation gate (P1's X11-tool mismatch was resolved locally by using the compositor facility).

## Resumption procedure
1. Read runbook, this state file, and the active phase issue only.
2. Revalidate live state first: `llamactl.service` active, `:19090` 200, external `8082`/`8091` `/health` 200, no Llamactl instances.
3. Continue from "Next exact action"; update this file and the issue before compaction or stopping.
4. Protected throughout: `local-qwen.service`, `hindsight-extract-llm.service`, `qwen-tailnet-fwd.service`, ports 8082/8091/8083/1235, the dual-5090 split, model weights, management key, HERDR. No Llamactl instance has been created or started; no package installed; no config or unit edited.

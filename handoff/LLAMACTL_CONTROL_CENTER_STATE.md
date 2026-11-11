# Llamactl Control Center — durable worker checkpoint

**Status:** ACTIVE — P0 and P1 gates PASS; P2 is the next phase
**Active phase:** P2 (#13) — read-only local model inventory + Llamactl cache reconciliation
**Execution owner:** Local worker on 5090FE (Sol supervising)
**Last updated:** 2026-11-10 (after P1 acceptance)
**Master issue:** https://github.com/Helminiak/LLM-Setup/issues/10
**Runbook:** [README](../docs/llamactl-control-center/README.md)
**P0 manifest:** [P0-BASELINE-2026-11-10.md](../docs/llamactl-control-center/P0-BASELINE-2026-11-10.md)
**Completed phases:** P0 #11 (gate PASS), P1 #12 (gate PASS)

## Verified current system facts
- Host `5090FE`, user `joe`, `Linux 7.0.0-43-generic`, **native Wayland** session (`wayland-0`, `XDG_SESSION_TYPE=wayland`), XWayland also live (`DISPLAY=:0`, `/tmp/.X11-unix/X0|X1`), `xrandr` 6144x3456 on HDMI-1. 694 GB free. 2x RTX 5090, driver 595.99.02.
- Llamactl **v0.23.0**: user unit `llamactl.service` enabled+active (MainPID 196673), `ExecStart=~/.local/state/llamactl-staging-20261109/run-llamactl.sh` (exports `LLAMACTL_MGMT_KEY` from a local key file + `LLAMACTL_CONFIG_PATH`), binary `~/.local/opt/llamactl/v0.23.0/llamactl`, listener `127.0.0.1:19090` only. Unauthenticated API → `401`; with Bearer key → `200`.
- Config: instance pool `19091-19150`, `auto_create_dirs: true`, `auto_restart: false`, `on_demand_start: false`, `idle_timeout: 30`, backends llama-cpp (`llama-server`, docker off)/vllm/mlx, `local_node=5090FE-llamactl-validation`, node `main` has no address.
- **Managed instances = 0** (API `[]` and SQLite `instances` 0 rows; `api_keys` 0, `key_permissions` 0, `server_secrets` 1). Nothing has ever been started by Llamactl.
- Models defect: `GET /api/v1/models` → two HF-cache validation entries only, **no GGUF**, while `~/models` holds **19** GGUF files. `/mnt/llm` holds none.
- External/protected and healthy: `local-qwen.service` → `127.0.0.1:8082` (dual-5090 layer split Qwen3.8-Flash-Next GSQ-RCO IQ3_XXS, ctx 128000, 1 slot, `/health` 200); `hindsight-extract-llm.service` → `127.0.0.1:8091` (Qwen3-4B Q4, CPU); `qwen-tailnet-fwd.service` socat `8083→8082`. `dr100-model.service` (`:1235`) inactive/static. Do not touch these.
- Native capability: **no `/api/v1/profiles` (404)**; full instance lifecycle routes exist (`instances/{name}/start|stop|restart|logs|proxy`), plus `models`, `models/download`, `models/jobs`, `nodes/{name}/health`, `backends/llama-cpp/{version|devices|help|parse-command}`, `llama-cpp/{node}/models` + `load|unload`. Instance options include `models_dir`; binary honors `LLAMACTL_INSTANCES_DIR`, `LLAMACTL_MAX_INSTANCES`, `LLAMACTL_LLAMACPP_COMMAND|ARGS|ENV`, `LLAMACTL_DATABASE_PATH`, `HUGGINGFACE_HUB_CACHE`.
- Launcher verified working end-to-end: `~/Desktop/Llamactl Control Center.desktop` (trusted, Exec/TryExec → `~/.local/bin/llamactl-control-center`) → wrapper health precheck on `:19090` (zenity/notify-send fallback) → `google-chrome --app=http://127.0.0.1:19090 --user-data-dir=~/.config/llamactl-control-center --class=LlamactlControlCenter`.
- **The Control Center window is native Wayland** (Chrome `--ozone-platform=wayland`): it is absent from `xwininfo -root -tree` and `_NET_CLIENT_LIST`, so **`wmctrl`/`xdotool` cannot see it**. Use the installed compositor/AX facility (`computer_use` `list_windows`/`capture`) instead. `org.gnome.Shell.Eval` is disabled and `org.gnome.Shell.Screenshot` is Access denied; no screenshot CLI is installed.
- No vision model on this host (`image input is not supported … provide the mmproj`) → GUI evidence must be window-system + page-load + rendered-DOM based, not pixel reading.
- **UI auth gate finding (affects P4/P5):** the launched window lands on "Authentication Required / enter management API key" (`INPUT` + `Login`). `GET /api/v1/auth/whoami` returns `{"authenticated":false,"oidc_enabled":false,"user":null}` both unauthenticated **and** with the Bearer management key — the exported key does not authenticate the browser session, so the operator must paste it per session.

## Phase checkpoint
- **P0 #11 — PASS.** Evidence: https://github.com/Helminiak/LLM-Setup/issues/11#issuecomment-6784608202
- **P1 #12 — PASS.** Evidence: https://github.com/Helminiak/LLM-Setup/issues/12#issuecomment-6784762554
  - `gio launch` exit 0 → new app window appeared (window_id 130212167681); `SIGTERM` to the app instance closed it; relaunch gave `pid 2033606`, `window_id 133274402816`, title `Llamactl Dashboard`, `off_screen=false`, frame `(0,0,1521,1708)`.
  - Service log proves the window loaded the app: `GET / 200`, `/assets/index-DrdvaW8y.css 200`, `/assets/index-BfM6bn_m.js 200 (636213B)`, `/api/v1/auth/whoami 200`.
  - Parked (owner credential): `sudo -n true` → "interactive authentication is required", so `wmctrl 1.07+git20240228…` / `xdotool 1:3.20160805…` are **not installed** (nothing installed/upgraded). Not required for this target.
- Still UNVERIFIED: `llamactl` CLI surface (bare `--help` hung 180 s, terminated; no stray process); whether `models_dir` can expose the GGUF library; no entry in `~/.local/share/applications` (app-grid launch) — deferred to P7 handoff.
- Blocking decision: none.
- **Next exact action (P2, issue #13):** read-only inventory — enumerate GGUF files under `~/models` (path/size/sha256-of-header or full sha256 for the 19 files), record architecture/context/quant fields from GGUF metadata headers only, compare against what Llamactl reports via `GET /api/v1/models` and the HF cache dirs, then **prove or disprove** that `models_dir` / `HUGGINGFACE_HUB_CACHE` / `LLAMACTL_INSTANCES_DIR` can make the library visible — configuration proof only, no instance start, no weight move, no download.

## Files/commits changed
- Repo branch `feat/llamactl-control-center` (worktree `~/repos/LLM-Setup-worktrees/llamactl-control-center`), also on `main`: `4e8883a` = P0 manifest + checkpoint. No runtime file modified since.
- Local rollback backup: `~/.local/state/llamactl-baseline-backup-20261110/` (+ `MANIFEST.sha256`): service unit, wrapper, both desktop entries, icon, `llamactl.yaml`, legacy desktop entry. Key file, logs and DB excluded.
- Untouched: `~/repos/LLM-Setup` working tree (unrelated uncommitted work on `feat/parallel-engineering-default`).

## Evidence references
- P0: issue #11 comment 6784608202; `docs/llamactl-control-center/P0-BASELINE-2026-11-10.md`.
- P1: issue #12 comment 6784762554; composited screenshot `~/.hermes/profiles/hermes-supervisor/cache/images/computer_use_ccbfe1db2f9e4617b8a4049f17df6ac2.png` (retention limited ~24 h).

## Claude escalations
None. No blocker met the escalation gate (P1's X11-tool mismatch was resolved locally by using the compositor facility).

## Resumption procedure
1. Read runbook, this state file, and the active phase issue only.
2. Revalidate live state first: `llamactl.service` active, `:19090` 200, external `8082`/`8091` `/health` 200, no Llamactl instances.
3. Continue from "Next exact action"; update this file and the issue before compaction or stopping.
4. Protected throughout: `local-qwen.service`, `hindsight-extract-llm.service`, `qwen-tailnet-fwd.service`, ports 8082/8091/8083/1235, the dual-5090 split, model weights, management key, HERDR. No Llamactl instance has been created or started; no package installed; no config or unit edited.

# Llamactl Control Center — local-worker runbook

**Execution:** One local worker on `5090FE`; escalate a specific blocker to Claude only when needed. This runbook describes workflow, not evidence that anything is implemented.

## Mission and boundaries
Complete the existing Llamactl web Control Center: discover locally installed model artifacts, recover verified saved launch configurations, select model/profile, safely load/monitor/stop *managed* instances, and preserve existing inference services. Llamactl v0.23.0 dashboard was observed on `http://127.0.0.1:19090`; its Models view displayed two validation cache models, not the full workstation inventory. A recent local repair reported the desktop launcher fixed but graphical acceptance UNVERIFIED, and Llamactl itself had no registered instances. **Recheck all runtime claims locally.**

**Protect:** Existing HERDR/Hermes/Hindsight, independent systemd inference servers, port assignments, GPU workloads, management authentication, keys, and model files. No model deletion/moves/downloads, unapproved production restarts, credential changes, broad network binding, or automatic takeover of external services. Repository is **public**: never commit secrets, private operational data, full model weights, or credential-bearing logs.

## Context-efficient execution contract
1. Start with **this file**, `handoff/LLAMACTL_CONTROL_CENTER_STATE.md`, and **only the currently assigned phase issue**. Do not read all issues, the whole chat, or unrelated repository history.
2. Verify `hostname` is `5090FE`. Read only the files and services relevant to the active phase.
3. Keep **one active phase** and one worker owning changes. No parallel conflicting agents.
4. Before changes, inspect working tree and back up affected local configuration. Use a feature branch for new code when practical; do not overwrite unrelated work.
5. Make the smallest change, run the phase's checks, and record evidence with exact commands, output summaries, changed paths, and commit IDs.
6. **Before compaction, interruption, or moving to the next phase**, update the handoff file with concise durable facts (max ~150 lines) and leave a brief comment on the active GitHub issue. Do not embed long logs or secrets. Commit the sanitized handoff. On resume, trust only revalidated live facts.
7. Do not advance a phase without its acceptance gate. Mark blockers explicitly rather than inventing PASS.
8. Treat historical configurations and port numbers as clues, not live facts. Existing external services remain EXTERNAL/UNMANAGED until a separately approved migration.

## Phase order
- **P0:** Audit actual Llamactl/runtime state and recover prior work.
- **P1:** Install `wmctrl` and `xdotool`, check X11/Wayland, finish launcher GUI verification.
- **P2:** Build read-only model artifact inventory and reconcile dashboard/cache.
- **P3:** Recover/validate launch profiles from existing services and benchmark records.
- **P4:** Integrate model library and profile selection/editing with the existing UI.
- **P5:** Implement safe start/health/stop lifecycle, port and GPU preflight, external-service preservation.
- **P6:** Add benchmark/history linkage and read-only HERDR runtime discovery only if supported by existing architecture.
- **P7:** End-to-end acceptance, documentation, rollback, final status.

## Claude escalation gate
Escalate only for: unsupported native Llamactl integration requiring a substantive architecture choice; unresolved backend incompatibility; repeatable data corruption; severe GUI/compositor constraints; or security/production-service changes needing design review. The local worker sends Claude **only**: issue URL, handoff file, objective, verified evidence, attempted minimal fixes, specific blocking decision, and explicit non-negotiable constraints. Claude returns a bounded recommended change/test, not ownership of the entire project. Security or production-impact changes still need user approval.

## Pass/fail convention
Use `PASS` only with executed evidence, `FAIL` on demonstrated defect, `BLOCKED` on a concrete prerequisite, and `UNVERIFIED` when no direct test was possible. Never use a healthy HTTP endpoint as evidence that GUI or model-launch acceptance passed.

**Completion contract:** Operator opens the existing desktop Control Center, sees recognized local models, picks a *verified* saved profile, safely starts an eligible managed model, confirms real inference readiness/resources, and stops it without disrupting protected external inference.

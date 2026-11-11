# Overnight inference research — worker runbook (2026-11-11)
**Master issue:** https://github.com/Helminiak/LLM-Setup/issues/19
**Status:** PLANNED. GitHub issue creation alone cannot start HERDR execution.
**Hand-off target:** 08:00 America/New_York. At 07:30 stop starting new experiments, clean up and publish evidence. Do not promise a result by that time.
**Location:** HERDR multi-agent/grid session on 5090FE. Keep local work durable through GitHub commits/issues, not terminal history.

## Goal and scope
Evaluate four workstreams on the dual RTX 5090 workstation: (1) adrienbrault's Qwen3.8 Flash Next ExLlamaV3+TabbyAPI 2.68bpw pinned stack; (2) native MTP, draft-model, n-gram/prompt lookup and inference engine optimizations vs baseline; (3) public LoRA and auxiliary adapters matching exact checkpoints; (4) llama-swap integration, correctness and representative HERDR coding-task throughput. Optimize high-impact settings only, no exhaustive parameter search.
Existing evidence: `main` Gyro-L 2026-11-06 baseline (103.4 content tok/s, Q8 KV, 128K/1 slot), and `feat/parallel-engineering-default` 2026-11-11 llama-swap reconciliation. Different models/benchmarks are **not** a before/after regression.

## Agent assignments and token budget
- **Supervisor:** existing HERDR/Hermes coordinator on 5090FE; owns phase gates, GPU lease, 15-minute heartbeat and morning report. Coordination only; no fabricated execution.
- **Primary executor:** local Qwen on 5090FE; inventory, version audit, isolated test preparations, logs, benchmark runs, GitHub checkpoint. Keep 1 GPU job at a time.
- **Research A:** MacBook Air Codex, *lowest available* reasoning effort. Read/review the external ExLlamaV3 repo; produce exact pinned dependencies, engine/kernel differences, transferability and license/security notes. No GPU execution.
- **Research B:** MacBook Air Codex, *lowest available* effort, separate session if actually available. Public LoRA/decision/draft heads catalog and exact base compatibility. No downloads or Git writes to same file as A.
- **Claude reviewer:** lowest available Claude tier, only narrow integration/security/design blockers and final evidence audit. One issue and <=1500-word packet per escalation; no autonomous large investigation.
- Optional Mini PC supervisor: read-only status only until a real `worker_dispatch` execution path has separately passed. Do not rely on its chat-generated agent inventory.
- **Token discipline:** use source-specific excerpts; cap each cloud worker to current issue + checkpoint + <5 cited code/docs files. If stuck twice, send concise escalation; do not recurse with multiple agents. Reuse local Qwen for log parsing/benchmark preparation.

## Runtime safety
1. At kickoff capture `systemctl --user` state for `local-qwen.service`, `llama-swap.service`, unrelated production services and all occupied ports. The former was intentionally stopped in the earlier test: treat actual start state as authoritative.
2. No production/HERDR/DR100 route changes. Do not kill processes, use unapproved `sudo`, alter GPU clocks, keys, authentication, device tags or existing weights.
3. One exclusive GPU execution lease held by supervisor (record PID, command, start, expiry, rollback). All model loads run sequentially. Only owner of GPU lease can start a GPU model. Always preflight per-GPU free VRAM and effective model + KV/buffer requirement. Do not use aggregate VRAM as a pooled allocation.
4. For large new checkpoints, provide expected disk footprint, license, provenance and required owner approval before downloading. Prefer existing weights, staged build, fixtures and metadata for proof of concept if absent.
5. Pinned upstream code is untrusted. Review Dockerfiles/patches/scripts before executing, use isolated worktrees/containers, avoid host privileged mounts, verify licenses/checksums. No `curl | bash` from unreviewed sources.
6. Keep new endpoints on unused loopback ports; leave original user services and HERDR destinations alone. At finish restore observed pre-run runtime state; don't automatically start a service that was intentionally stopped at kickoff.
7. Guard for runaway loops: one initial attempt + one evidence-based repair per failure; a second failure becomes BLOCKED/escalation. Stop tuning when improvement is <3% within run noise or task quality worsens.

## Persistent handoff protocol
The current owner only reads this RUNBOOK, `handoff/INFERENCE_OVERNIGHT_STATE.md` and the assigned phase issue. Every issue update must be concise:
`TASK_ID / OWNER / STATUS / START-UTC / END-UTC / code ref / model ref / commands / evidence paths / result / next exact command / blocker`.
Use `READY`, `RUNNING`, `PASS`, `FAIL`, `BLOCKED`, `UNVERIFIED`. Supervisor controls GitHub updates to the **single** central checkpoint; workers write separate issue comments or their own branch artifacts to avoid conflicts. No concurrent edits to the same files. Save after each bounded test and before compaction; restart via checkpoint, not lost chat state.
GitHub is authoritative; Hindsight stores summaries/keywords only with source links. Raw logs and large test artifacts stay local with SHA256 manifests; public GitHub only sanitized concise measurements.

## Experiment method
- Exact same model weights + quantization + backend + sampler + workload for causal engine parameter A/B; a cross-checkpoint comparison must be labelled non-equivalent.
- Baseline and candidate: warm-up, repeated short coding prompts and >=1 held-out tool/task correctness test; record prefill, TTFT, decode content t/s, per-stream and aggregate (not conflated), MTP accepted/proposed and tokens per forward step, peak VRAM per GPU, cold-load, failure/restart count.
- Parallel 1, 2 and optionally 4 request streams only if spare GPU headroom. At least 3 repetitions for a preliminary result; do not claim a statistical CI without sufficient sample.
- No promotion without tests proving correctness and a rollback dry-run. Stop after meaningful gains, no optimization of the final 2–3% absent statistically clear task-level value.
- Evidence-readiness rubric (NOT probability): 30 points correctness, 25 measurable inference performance, 15 reproducible deployment and rollback, 15 adapter/backend compatibility, 15 HERDR/API safety. >=90 with no critical fails = `promotion candidate` pending owner approval; otherwise report exact gap.

## Night gates
P0 revalidate baseline and resource/permissions → P1/P2/P3 research may run concurrently (no GPU) → P4 one isolated load/benchmark with GPU lease → P5 optional adapter PoC if compatible → P6 synthesis and safe handoff. Always produce morning report, even on BLOCKED. No automatic deployment into DR100 or HERDR production.

## Source pointers
- https://github.com/adrienbrault/qwen3.8-flash-next-2x-rtx5090
- https://github.com/turboderp-org/exllamav3
- https://github.com/theroyallab/tabbyAPI
- https://github.com/mostlygeek/llama-swap
- https://github.com/Helminiak/LLM-Setup/blob/main/benchmarks/local-models/gyro-l-slot-optimization-2026-11-06/REPORT.md
- https://github.com/Helminiak/LLM-Setup/blob/feat/parallel-engineering-default/docs/llama-swap-github-reconciliation-2026-11-11.md

## Escalation packet
One exact failing command and bounded redacted error; expected/observed; environment versions; two attempted fixes; git/issue refs; 1 question requiring a decision. Claude is not to be asked to rerun all prior phases.

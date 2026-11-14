# 5090FE Gyro-L dual-worker acceptance — 2026-11-14

Checkpoint key: `GYRO-DUAL-20261114-01`.

**Functional engineering acceptance: PASS.** Two independent Hermes sessions concurrently used one resident Gyro-L backend and executed real engineering tools. Both projects passed independent supervisor reruns. **This is not DR100/GSQ production qualification or permission to dispatch production work.** Observed memory headroom exceeds the saved live baseline, but GPU0 does not meet an older documented 2 GiB target; no claim of that stronger reserve or arbitrary full-window load endurance is made.

## Authoritative preflight and isolation

Host `5090FE`, two NVIDIA RTX 5090s, 32,607 MiB each, driver 595.99.02. NVIDIA answered health/resource queries; no GPU failure occurred during this acceptance. Temperature at initial inventory 40/36 C; final 38/42 C. Saved `nvidia-smi -q` includes hardware/error fields (unsupported counters are not proof of zero errors).

`GET http://127.0.0.1:8080/running`, backend `/props`, backend `/slots`, actual process command, service cgroup and listener inventory established residency. Catalog presence was not used as residency proof. Original backend PID1937611 was a child of llama-swap PID3456, owning the global `gpu-lease.lock`; the durable evaluation lease was RELEASED. `dr100-model.service` was inactive, MainPID0. Candidate profiles and qwen-worker returned empty live-session lists. Existing HERDR terminals were inventoried; current Codex t9v was the maintenance controller, outgoing supervisor t9r was done. No competing running GPU evaluation/engineering controller was found; historical sol-parallel ready/recovery records were neither resumed nor rewritten. Its heartbeat is not a dispatch authorization. No production task was claimed.

Before modification, private backups captured affected profile configuration/startup material, llama-swap config, applicable service definitions, hashes, listeners, services, model props/slots/running state, live sessions, leases and supported Kanban show/runs/boards results. Backup root: `/home/joe/.local/state/codex/dual-worker-20261114/before/`; rollback procedure in [ROLLBACK.md](ROLLBACK.md). Session/history databases were preserved in place, not restored, reset or deleted. Kanban SQLite was never edited directly.

## Backend before and after

| Property | Before | After |
|---|---|---|
| Proxy route | `ready-gyro-l-abl` at `127.0.0.1:8080/v1` | unchanged |
| Backend | `127.0.0.1:10110` | unchanged |
| API alias | `gyro-l-abliterated-tq3_0-mtp` | unchanged |
| Executable | `/home/joe/src/llama-gyro-main/build/bin/llama-server` | unchanged |
| Build | `0.5.0-dev`, b11378, commit060e10051 | unchanged |
| Model | `/home/joe/models/gyro-l/Qwen3.8-Flash-Next-Gyro-L-abliterated-TQ3_0.gguf` | unchanged |
| Total context | 131072 | 131072 |
| Parallel slots | 1 | 2 |
| Actual `/slots` capacity | 1 × 131072 | 2 × 65536 |
| K/V precision | q8_0 / q8_0 | unchanged |
| GPU distribution | CUDA0,CUDA1; layer split; 1,1; ngl999 | unchanged |
| Speculation | MTP draft, min2/max6, draft CUDA1, vocabulary32768; ngram-on-disk | unchanged; both slots speculative=true |

The sole llama-swap config edit was `--parallel 1` → `--parallel 2`. [Exact complete commands](backend-change.json) and [actual props/slots](backend-props.json) are retained. llama-swap validated the candidate configuration before activation. Its watcher unloaded the safely idle original backend and reloaded **the same weights** on a bounded request; shared llama-swap/gateway services were not restarted. Discovery itself did not unload or replace the model. Model quantization, weights, GPU split and other flags were not changed. `/props` reports model_ftype `IQ4_NL - 4.5 bpw`; the model pathname says TQ3_0. Both observations are retained without treating the filename as authoritative tensor precision.

Installed source matches the executable commit. `src/llama-context.cpp` divides n_ctx by n_seq_max when kv_unified is false; server slot construction uses llama_n_ctx_seq. Runtime results, rather than a GUI field, confirmed two 65536 capacities. Full-window content retention and 65K-per-slot simultaneous saturation endurance were not stress-qualified.

llama-swap's documented single-model controls are available for supervised rollback: [upstream API documentation](https://github.com/mostlygeek/llama-swap#features). No model-switch failure simulation was performed against the production service.

## Hermes workers and real concurrency

Existing nonproduction profiles `gyro-worker-1` and `gyro-worker-2` were updated through supported `hermes -p ... config set` controls, with explicit section replacement for MCP configuration and parsed readback. [Exact before/after configurations and hashes](worker-configurations.json).

Both use custom:codebreaker, fixed model `ready-gyro-l-abl`, chat_completions, localhost8080, context65536, fallback_model=[], api_max_retries1, auto_recovery_cycles0, max_turns24, local terminal timeout60, compression enabled at0.75, explicitly local compression route. CLI toolsets: terminal/file/mcp-rea. Kanban dispatch false and dispatch_profiles[] in both. Profile SOUL instructions bound workspaces, retries, scope and production exclusions. No API key or paid inference provider was provisioned.

| Worker | HERDR | Conversation | Separate workspace |
|---|---|---|---|
| Rust | t9y | `local-f1a324b813ed19e23f14ba69033c6ad2ca19c6a2e89eb0f50475ebfa84aed7af` | state root `/worker-1` |
| Python/REA | t9z | `local-1316b8bd979040b2fc4002fb290d6ac39f8da3f89d5df2549d405dea63344923` | state root `/worker-2` |

State root is `/home/joe/.local/state/codex/dual-worker-20261114`. Each workspace is its own Git repository; no shared source writes. Both sessions were launched interactively with seeded task files and bounded turn/time budgets, remain independently available in HERDR, and require no Kanban admission.

The monitor sampled actual `/slots` and GPU state, recording **335 samples with both slots is_processing=true**. First dual-active sample Unix1794692342.2702284, last1794692572.3995318; these are not claimed as one uninterrupted overlap interval. Initial simultaneous tasks579/580 had different prompts and belonged to the only two submitted worker sessions at that point. Session receipts independently show tool execution and local billing_base_url8080. [Concurrency/resource evidence](concurrency-summary.json), [exported session metrics](session-metrics.json). Raw monitoring and full acceptance-only session exports remain in the private state root. No old 900K conversation was loaded.

## Engineering and tool qualification

Rust worker generated a dependency-free crate with file tools, invoked Cargo, demonstrated a real intentional test failure (exit101), patched it and passed. Supervisor review identified an additional integer overflow boundary; the worker reproduced it, widened arithmetic and added tests. Final result: **9 unit tests + 1 doctest**, cargo fmt --check exit0 and cargo test --offline exit0. Source, hashes, original failure logs, repair logs and worker report are in [worker-1](worker-1/REPORT.md).

Python worker generated interval-merging code and **9 passing unittest cases**, exit0. It compiled harmless probe.c to probe.o with gcc exit0, read independent Git metadata (including the explicitly handled unborn-repository case), and used file read/write/patch tools. [Worker-2 report and receipts](worker-2/REPORT.md).

Supervisor independently reran final Rust formatting/tests, Python tests and Git checks: all exit0. [Independent commands, output and final source hashes](independent-verification.json). Available host tools: rustc/cargo1.93.1, Python3.14.9, Git2.53.0, javac25.0.5.0.3. Java compilation was unnecessary for these assignments; no Java acceptance claim is made.

REA installation was reused: `rea-agents`6.9.0 with repository metadata `https://github.com/morluto/rea`; explicit Node24.22.2 launcher plus absolute scripts/rea.mjs path. Only `inspect_with_objdump` is registered for candidates. Hopper environment/registration was removed from these two candidates; other profile registrations were inventoried but not modified. No optional engine was installed; awesome-reverse-engineering was not used as tooling.

**Real MCP qualification passed:** worker-2 tool_call invoked mcp__rea__inspect_with_objdump on probe.o for disassembly and symbols; tool responses retain evidence IDs and matching artifact SHA256 `c94ed0f2b09e0167b3144775dce3c7c8e210c70f9c16db56b04b4e8d7f97450e`. [Actual MCP call/result receipts](rea-mcp-receipts.json). No REA CLI success is substituted for MCP qualification. Registration filtering limits exposed tools, not OS-level filesystem access; these remain supervised local workers, not sandbox-isolated untrusted agents.

## Failure and recovery acceptance

| Test | Observed behavior |
|---|---|
| One worker fails while other continues | Rust real nonzero test/repair overlapped Python engineering. Separately, HTTP503 requests overlapped a healthy slot; timestamp correlation retained. |
| Tool nonzero | Rust cargo exit101; later active cancellation terminal exit130. |
| Backend unavailable | Isolated loopback19110 returned503; worker stopped after two completion requests per turn. Four total requests across two deliberate turns, no paid fallback. Other worker used production backend successfully. First setup attempt used a disabled custom provider and failed before inference; corrected to named provider without modifying production route. |
| Context exhaustion | Real backend rejected **77084 prompt tokens >65536** with HTTP400; Hermes attempted compression, reported no progress and stopped explicitly. No silent truncation success. Raw oversized filler was not published. |
| Checkpoint recovery | Fresh session `local-3e2597a903a9af344c65ffc6646acf4510f1b564adc3cf4942745b1b1b24c607` read durable checkpoint, verified source hashes and reran Rust checks exit0, without source regeneration or new commits. It identified stale checkpoint HEAD text vs later docs-only HEAD; source hashes matched. [Recovery evidence](worker-1/CONTEXT_RECOVERY.md). Automatic semantic recovery of arbitrary exhausted conversations is not qualified. |
| Active cancellation | HERDR interrupt of worker-2's harmless 30-second waiting tool returned outcome unknown; actual worker terminal receipt then proved exit130 and return to prompt. The sleep was not replayed. [Cancellation receipt](cancel-after.txt). |
| Clean restart/continuation | Python read checkpoint, verified all4 source/artifact hashes, reran9tests exit0, unchanged Git HEAD; only new recovery evidence written. [Recovery report](worker-2/CANCELLATION_RECOVERY.md). |

Temporary fault server and monitor stopped; test sessions closed after evidence capture. Main t9y/t9z remain idle and usable. No shared GPU service was stopped to simulate failure.

## GPU reserve and remaining limits

Original actual free memory from saved nvidia-smi-q: **1554/1844 MiB**, with497MiB driver-reserved perGPU. Do not compute free memory as total-used. During monitored two-slot operation: GPU0 **1962–1982 MiB free**, GPU1 **2106–2138 MiB free**. This preserves/improves the observed live reserve without quantization/split changes. GPU0 falls short of an older ≥2GiB reference by86MiB at the recorded minimum. A strict2GiB gate is **not passed**; if that is mandatory, this lane must remain supervised/pending that resource review. No VRAM OOM or backend failure was observed. No assertion is made about untested long-duration, maximum-prefill or thermal-stress conditions.

Named-provider outage override lacked a live metadata probe and showed default256K in that fault-only UI; normal worker sessions and backend slots were pinned65536. Do not use isolated fault UI metadata to size live slots. Compression estimates differed from actual tokenizer counts; backend77084/65536 is the authoritative rejection.

## Kanban and production preservation

Automatic dispatch was already false before maintenance. The running gateway log confirms it disabled at2026-11-14 16:10:41; candidate config readback also disables dispatch. Gateway remained active; read-only board operations remained available. No task attempts reset, claims deleted, board deleted or history modified.

`orderflow-engineering/t_d0e61935` remains TRIAGE. Complete supported show JSON and runs27–30 JSON compare equal before/after. qwen-worker config, global config and backed service definitions retain original hashes. [Isolation checks](production-isolation.json), [protected hashes](protected-hashes.json).

Existing `dr100-production-check`, GSQ contract and single-worker production restriction were not modified or requalified. No TTW/Bookmap production task, replay mutation, live trading, production JAR replacement or Windows GUI automation occurred.

Relevant production checkpoint: [orderflow-entry-engine PR43](https://github.com/Helminiak/orderflow-entry-engine/pull/43), head2218b1c0e2d38363f7d5818dfe49783fc141d878; [canonical handoff](https://github.com/Helminiak/orderflow-entry-engine/blob/2218b1c0e2d38363f7d5818dfe49783fc141d878/coordination/ttw/HANDOFF.md). Runs27–30 and P0 blocked-access status remain independent from this engineering acceptance.

Read only [HANDOFF.md](HANDOFF.md) to start a fresh GPT-6.1 Sol Normal supervisor session. Kanban dispatch must remain paused.

# Permanent parallel-default acceptance — 2026-11-07 UTC

Final disposition: four engineering deliverables APPROVED by SOL; all 12 requested acceptance gates have supporting evidence (GitHub publication is completed with this report). No model reload, extra inference slot, production Kanban mutation, or benchmark restart occurred. This is a dedicated default workflow; production concurrency remains 1.

## Results

| Measurement | Actual result |
|---|---:|
| Peak active worker lifecycles | 4 |
| Peak inference requests per GPU | 1 / 1 |
| Initial prompt tokens, w1/w2 | 49,563 / 49,612 |
| Initial prompt tokens, w3/w4 | 49,607 / 49,643 |
| Highest successful prompt | 61,605 |
| Highest successful prompt + generated tokens | 62,167 / 65,536 |
| Original four-worker execution | 402.68 s |
| End-to-end through final SOL approval, including repair/review | 685.09 s |
| Accepted deliverables | 4 |
| Accepted deliverables per minute | 0.3503 |
| Generated tokens | 43,534 |
| Generated tokens / end-to-end wall second | 63.54 |
| Decode tokens / summed decode-service second | 84.22 |
| Uncached prompt tokens / prompt-processing second | 1,857.09 |
| Cumulative reported cached token positions reused | 3,026,802 |
| Aggregate request queue wait across workers | 734.76 s |
| Maximum single request queue wait | 41.04 s |
| Peak VRAM GPU 0 / GPU 1 | 30,046 / 30,030 MiB |
| Minimum free VRAM GPU 0 / GPU 1 | 2,066 / 2,082 MiB |
| Peak system memory used (MemTotal − MemAvailable) | 32,678 MiB |
| Minimum MemAvailable | 30,200 MiB |
| Mean sampled aggregate CPU utilization | 6.96% |
| Mean sampled GPU utilization, GPU 0 / GPU 1 | 71.10% / 64.64% |
| Proxy-observed inference occupied, GPU 0 / GPU 1 | 436.53 / 411.07 s |
| End-to-end proxy-observed idle, GPU 0 / GPU 1 | 248.56 / 274.02 s |
| Peak temperatures, GPU 0 / GPU 1 | 67 / 69 C |
| Peak power, GPU 0 / GPU 1 | 422.21 / 413.41 W |

Three CPU queues ran real compilation, controller tests, and deterministic source AST/hash analysis concurrently. All three overlapped inference and each other. Initial limits were build 8, test 6, analysis 6 threads; these are workload hints, not cgroup caps. Small Python commands did not consume all allowed threads. Per-core load, I/O wait, swap counters, GPU temperature/power/throttling masks and CPU task timing are retained in metrics/raw private telemetry. Global swap counters increased by 219,254 pages in and 45,215 pages out (~856/177 MiB at the observed 4 KiB page size); attribution to these workers is not established. All observed NVIDIA active-throttling masks were zero. No out-of-memory event was observed.

Rates use measured model timing fields. Summed service time can exceed wall time across two GPUs. Cached positions are cumulative per-request reuse, not unique corpus tokens. Idle time includes tool/review waits and excludes unproxied Hindsight inference accounting; sampled hardware utilization includes other workstation activity. The prior 106.06-second clamp test had much shorter context and simpler tasks, so no controlled speedup is claimed.

## Failure, repair and preserved evidence

All four workers launched once for the original stress test. Each received a unique, meaningful task with real, nonduplicate standard-library and controller source references; actual rendered-template token accounting confirmed the target range. The services retained Q8_0 K/V, batch 4096, ubatch 512, one slot and 65,536 context. Prompt reuse was requested and measured, not assumed.

The first continuation path was defective: it appended the full 50K source bundle again. Four rejected requests reached approximately 102K–105K tokens (maximum requested 105,292); these are failures, not achieved context. External acceptance execution also imported namespace task directories instead of the actual modules. All source, session history and failed checkpoint snapshots were preserved. The source-bundle duplication and verifier import path were repaired without reloading models or restarting the benchmark. Four unchanged original implementations then passed independent acceptance, returning only to pending review. No 180-second timeout was hit; the integrated default used a 600-second slice bound.

Corrections continued the original worker/task/session identities with concise objectives, full-source file/hash references, acceptance failures and SOL feedback. Final accepted source is in `artifacts/`; prompt hashes/counts are in `prompts.json`; exact source hashes and review dispositions are in `review.json`. The repaired context guard rejects oversized requests before forwarding and bounds generation to remaining capacity; it has a real streaming-HTTP regression test against a local fake upstream. The full stress test was not repeated after this repair. Automatic compaction's arbitrary semantic completeness is not claimed; preserved files/hashes, explicit session affinity and passing task-specific acceptance are verified.

## SOL review

- DAG topological layering: APPROVED after source review, independent acceptance and bytecode compilation. No worker-authored unittest suite was supplied; external acceptance is its test gate.
- Deterministic artifact manifest: APPROVED after source review, independent acceptance, full supplied suite and compilation. This is a trusted isolated-workspace utility, not a race-proof adversarial filesystem scanner.
- JSONL event summary: DISAPPROVED for skipping blank invalid-JSON records; same worker/session corrected it and added regression coverage; full suite, independent tests and SOL re-review passed; APPROVED.
- Recursive credential redaction: APPROVED WITH CHANGES for incorrect worker test expectations; then DISAPPROVED for a remaining invalid dictionary-identity assertion and an added unsupported matching restriction. Same worker/session corrected both; all 11 supplied tests and independent acceptance passed; APPROVED. This small tested utility is not a comprehensive secret-discovery product.

Controller restart revalidated accepted work and retained all four approvals without launching any workers. Hindsight recall succeeded through the unchanged existing `hermes-supervisor` profile. Its configuration SHA256 remained `0e1e0e33620503c395ff51d2976b87eaf0f8335ce11e0586b580646ab175bdbe`; production `kanban.max_in_progress` stayed 1. No existing memory, authentication, persona, skills, review protocol, historical benchmark or model was deleted or replaced.

The final controller suite passes 20 tests, including request serialization through an actual streaming HTTP proxy, overflow admission rejection, CPU deadline reaping, workspace imports, bounded source continuation, durable new-task execution policy and SOL feedback routing. `artifact-verification.json` records compilation and acceptance for all four public source copies and the three supplied unittest suites.

## Reproduction and remaining limits

See [architecture and launch instructions](../../docs/architecture/parallel-worker-default.md). The default is adaptive: routine tasks use only relevant material and reserve generation/tool capacity; 50K initial prompts are stress-test-only. Installed entrypoints persist across terminal/controller restarts and reboot subject to the existing model-service startup policy; no new systemd service is installed. Use a fresh manifest with new task IDs/workspaces for a separately authorized new stress experiment; never erase this checkpoint to rerun it.

Unverified: actual power-loss/reboot recovery; automatic cancellation of a native gateway generation after its CLI viewer is killed; hard CPU quotas for commands that ignore workload limits; arbitrary long-task semantic context preservation. In-flight recovery intentionally stops for inspection to prevent duplicate work. The default supervisor invocation is configured for the existing Codex SOL identity at medium and its supported arguments were inspected; no extra paid supervisor was launched just to test the wrapper. New-task CPU-policy prompt injection and the final admission guard have deterministic tests; this single stress benchmark was not restarted to test them again. Four simultaneous inference slots are deliberately outside this architecture.

Private raw evidence and failed checkpoints remain under `~/.local/state/sol-parallel/`. Public evidence is sanitized; retrieved Hindsight memories, credentials, full Supervisor context and raw private conversations are not committed. Paid supervisor token usage is unavailable.

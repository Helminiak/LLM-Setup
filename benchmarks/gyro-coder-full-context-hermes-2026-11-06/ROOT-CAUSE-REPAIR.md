# Hermes two-agent root-cause repair, 2026-11-06

## Diagnosis

The prior “GPU 1 stalled at initialization” conclusion was a false watchdog diagnosis. The old harness called `wait()` on child 1 before inspecting child 2 and had no per-child completion time or inference-progress signal. It emitted no JSON events while a streaming model call was in flight. GPU 1 had in fact initialized its custom provider at 21:37:35.146, opened a request at 21:37:35.564, processed 47,952 input tokens, generated 5,758 output tokens, and logged completion at 21:39:19.566 (104 seconds). Its first tool completed at 21:39:19.773. The old controller was terminated at about 21:39:20. No evidence implicates GPU capacity or a shared-home lock. Both independent processes successfully used the same `HERMES_HOME`; this does not establish that all shared-state operations are concurrency-safe.

| Time (local) | GPU 0 | GPU 1 |
|---|---|---|
| 21:37:35.1–.6 | Provider and request initialized | Provider and request initialized |
| 21:38:01.671 | First API call complete, 47,952 input / 280 output | Initial long generation ongoing |
| 21:39:18.526 | Third API call complete | Initial generation ongoing |
| 21:39:19.566 | Continuing tools/compression | First API call complete, 47,952 input / 5,758 output |
| 21:39:19.773 | Continuing | First terminal tool complete |
| ~21:39:20 | Controller killed | Controller killed |

The corrected controller polls both process groups, uses monotonic elapsed time and a bounded deadline, records each exit timestamp and code, and captures separate JSONL/stderr files. It terminates remaining process groups on a deadline or unhealthy endpoint. No production configuration was changed.

## Controlled verification

The short two-process coding check reached both endpoints and both generated Cargo projects that passed six tests. GPU 0 Hermes exited 1 after its eight-turn limit despite its code passing tests; GPU 1 exited 0. This is a separate agent-completion limitation, not the original initialization defect.

One controlled long-context two-process run followed. Both independently submitted requests and executed tools. The largest observed per-request input was 51,983 tokens on GPU 0 and 49,843 on GPU 1, without server-reported truncation. GPU 0 produced a complete project and passed six unit tests plus one doctest. GPU 1 produced Rust source but `cargo test` failed to compile due E0277, E0308 and E0502 errors. Both Hermes processes exited 1 after the eight-turn limit. This verification therefore **did not pass** the required two-agent coding acceptance criterion; no retry or higher concurrency was attempted.

The two GPU workers remained healthy after the run. Post-run VRAM was 30,044 MiB (GPU 0) and 30,028 MiB (GPU 1), with 37 GiB system RAM available. These are post-run readings, not measured peaks. Output telemetry totals over multiple calls were 10,695 and 10,092 tokens respectively; they must not be mistaken for a single response allowance. The published harness did not establish an explicit 8,192-token per-call cap.

## Production and rollback

`kanban.max_in_progress` remains 1. The inference servers remain one slot per GPU with unchanged weights, PLE, 65,536 context and routing. Independent CLI processes have been demonstrated; native Supervisor delegation and its production queue limits have not been validated by this run, so no two-worker dispatch configuration was installed. Rollback requires no configuration change. The prior benchmark and its raw historical artifacts remain intact.

Reproduction: run the script locally with `short` or `long`, after confirming both endpoints are healthy. It writes private prompts, raw Hermes events and workspace source only under `results/hermes-repair/` outside this repository. The repository contains the sanitized findings and controller, not private histories.

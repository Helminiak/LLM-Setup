# Two-agent coding acceptance at 12 turns — 2026-11-06

The benchmark-only CLI setting was `--max-turns 12`; production `kanban.max_in_progress` remains 1. Both existing GPU services retained one slot and 65,536 configured context. Hindsight health was unchanged. The run used two independent Hermes CLI processes and workspaces, routed to ports 8082 and 8083. It did not exercise native Supervisor delegation.

## Stage A: short context — PASS for required coding gates

| Agent | GPU | Hermes exit | Cargo result | First pass | Repair | Duration |
|---|---:|---:|---|---|---|---:|
| 1 | 0 | 0 | 6 unit tests and 1 doctest passed | Required gates passed | Formatting and verification commands repeated | 215.241 s |
| 2 | 1 | 0 | 6 unit tests passed | 5 passed, 1 failed | Corrected overwrite logic; second test run 6/6 passed | 160.179 s |

Both agents ran `cargo fmt --check` and `cargo test` and returned final reports. Agent 1 disclosed a defect in an extra `remove` API outside the specified six-test acceptance surface. Accordingly, the measured result establishes the requested ring-buffer gates, not general correctness of every extra API. Agent 2's repair was completed within the twelve-turn allowance. Full post-run Cargo output is retained in the accompanying logs. The Hermes stream's final token fields were zero in this gateway path, so reliable per-agent token totals and exact turn counts are unavailable from this harness; tool-call counts were 17 and 14, respectively. No token values are inferred.

## Stage B: long context — INVALID

One conditional two-agent long-context launch was attempted after Stage A. Both processes exited in about one second before inference. Hermes returned `Gateway draining: update_paused`, with a concurrent source-update warning. There was no long-context coding execution or token measurement in Stage B. The stage was not retried. This is an external gateway state change, not evidence of a GPU or model context limit.

## Decision

Short-context two-agent coding acceptance passed the specified automated gates at twelve turns. Full-context acceptance remains unestablished. Do not promote the production dispatch limit on these results. The existing inference services and Hermes production settings were not changed. The previous eight-turn and watchdog records remain preserved.

Reproduction uses `hermes_turn12_verify.py short` followed by `long` only when Stage A passes. Raw workspaces and private histories remain local under `results/hermes-turn12-20261106/`; they are not in this repository.

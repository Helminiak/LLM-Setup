# GYRO-ACCEPT-001: Hermes telemetry and compiler evidence

Scope: make the existing two-worker controller produce an offline, reproducible telemetry digest while keeping complete Cargo diagnostics. The implementation changes `hermes_turn12_verify.py`, adds `hermes_telemetry.py` and focused standard-library tests. Rollback is a Git revert of this task commit; no production settings or model services were changed.

Acceptance criteria: malformed and interrupted JSONL must not crash analysis; unknown token values must remain distinct from measured zero; streaming token deltas must not be double counted; tool and Cargo outcomes must be paired; full compiler output must remain on disk; the existing preflight artifact must reproduce its 36,571 input and 3,390 output tokens and six passing tests.

Execution: GPU 0 Hermes CLI agent inspected the existing controller and retained stream, then wrote the analyzer draft in a feature worktree. It reached its 12-turn ceiling before integration or tests. Its retained result reported 171,014 cumulative input tokens, 27,596 output tokens, and 405.174 seconds. The largest single request logged by Hermes was 31,072 input tokens. The supervisor resumed from the saved source, fixed the entry-point typo, Cargo output decoding, test-result parser, and zero-failure accounting, integrated the analyzer, and added tests. No restart or repeat agent run was used.

Independent verification:

- `python3 -m unittest -v test_hermes_telemetry.py`: 5 passed.
- `python3 -m py_compile hermes_telemetry.py hermes_turn12_verify.py test_hermes_telemetry.py`: passed.
- Offline analysis of `preflight-hermes.jsonl`: complete status; 36,571 input / 3,390 output; six passed, zero failed; seven tool calls. Model-turn count is labelled heuristic because that stream lacks per-call boundary records.
- `git diff --check`: passed.

The controller keeps complete raw JSONL/stderr and `cargo-test.log` in its local result workspace. Its compact summary marks unknown telemetry as unknown. The analyzer cannot manufacture precise turns from a stream that has no authoritative per-call records. A full live two-worker controller run was outside this task's acceptance scope; the existing services and Supervisor dispatch remain unchanged.

Gate assessment: this task establishes one completed, compiled and independently tested coding delivery through a local Hermes CLI worker with supervisor recovery. Native Hermes Supervisor delegation and two-agent production dispatch are not validated. Near-full context remains outstanding; this coding run's largest measured input was 31,072 tokens.

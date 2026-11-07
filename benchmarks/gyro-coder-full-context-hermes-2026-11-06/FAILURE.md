# Full-context Hermes production benchmark — 2026-11-06

## Preflight

One real Hermes `--safe-mode` session through GPU 0 generated a complete Rust 2021
ring/clamp project in an isolated workspace. `rustfmt --check`, `cargo test` (6/6),
and `cargo run` passed. Hermes telemetry reported 36,571 input tokens and 3,390
output tokens; the response terminated normally, not at an output cap.

## First-failure stage

The two-agent near-full-context stage was started with independent workspaces and
one Hermes process per GPU. GPU 0 began processing. GPU 1 emitted only the Hermes
initialization event and made no inference progress within the bounded observation
window. This is classified as an infrastructure initialization/timeout failure.

Per policy, the stage was stopped immediately: no retry, no higher concurrency,
and no second ramp. Child benchmark processes were terminated. Both persistent
inference services remained healthy (`/health` returned `{"status":"ok"}` for
8082 and 8083), with one slot per GPU and unchanged model configuration.

Diagnostics are retained in `stage-2/agent-1/` and `stage-2/agent-2/`; no stage
result is marked PASS because the pair did not complete as a valid steady-state
sample.

## Production configuration

No persistent Hermes concurrency setting was changed. `kanban.max_in_progress`
remains 1. The previously validated direct-controller results (2/4/6 agents) are
historical only and are not evidence of full-context Hermes capacity. Rollback is
therefore the unchanged pre-benchmark configuration.

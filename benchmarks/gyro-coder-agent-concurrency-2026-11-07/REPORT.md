# GYRO-Coder-L adaptive agent-concurrency benchmark

Date: 2026-11-07. The benchmark used an external bounded controller because the installed Hermes CLI exposes interactive sessions but no documented child-agent concurrency API. Each simulated agent had an isolated workspace, one request, Rust compilation/tests, and round-robin routing to the two existing one-slot workers. No model service or `--parallel` value was changed.

## Safety gates fixed before the ramp

- Request timeout: 90 seconds.
- Per-GPU waiting queue limit: 4.
- `MemAvailable` minimum: 8 GiB.
- Maximum stage swap growth: 1 GiB.
- Both `/health` endpoints required before and after every stage.
- No agent exception/crash allowed.
- Rust compile/test failures were recorded separately from orchestration/resource failures.

Baseline before ramp: both workers and Hindsight healthy; 65,536 context, one inference slot per GPU, Q8 K/V, batch 4096/ubatch 512; MemAvailable 48 GiB; memory PSI zero; GPU VRAM 30,038/30,012 MiB used.

## Ramp results

| Agents | Correct tasks/min | Aggregate tok/s | P95 latency | MemAvailable after | Status |
|---:|---:|---:|---:|---:|---|
| 2 | 7.299 | 191.104 | 15.78 s | 47.0 GiB | PASS |
| 4 | 8.081 | 211.590 | 29.64 s | 46.3 GiB | PASS |
| 6 | 8.151 | 213.422 | 44.12 s | 46.3 GiB | PASS / plateau |

At six agents, productivity was within 5% of the best observed result, so the upward ramp terminated at a measured plateau without deliberately provoking a failure. No 8/12/16/24/32-agent levels were attempted.

All ramp tasks completed with `rustc --test` and six passing tests per agent. GPU utilization reached ~94% at six agents; VRAM stayed at approximately 30.0 GiB per GPU. Swap free increased during stages; no PSI pressure or GPU OOM occurred.

## Required confirmation outcome

One bounded six-agent confirmation was run. Both inference services remained healthy, but all six requests hit the 2,048-token output cap (`finish_reason=length`) and produced no compilable source. This is an output-completion/coding failure, not a GPU, RAM, queue, or service crash. Under the first-failure/confirmation rule, testing ended immediately; no failed level was retried and no higher level was tested.

The pre-benchmark operational state was restored: no external concurrency controller remains active, Hermes Supervisor `max_in_progress` remains 1, and both one-slot GPU services continue using the winning C configuration.

## Selection and limits

- Highest passing ramp level: 6 agents.
- First failing confirmation: 6 agents, due to output truncation and zero compilable tasks.
- Recommended production concurrency: retain the existing Hermes ceiling of 1 until a separately approved confirmation with a sufficiently large output budget succeeds. The ramp’s measured six-agent throughput is useful capacity evidence but is not promoted as a production Hermes setting because its required confirmation failed.
- The benchmark did not test higher counts after the confirmation failure, by design.

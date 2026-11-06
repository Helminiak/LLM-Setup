# Codebreaker single/dual worker benchmark — 2026-11-06

## Method

- Existing production Gyro-L service only; no model reload or extra server.
- Same fixed `normalize_label` Python code-generation prompt, `temperature=0`, `top_p=1`, seed 42, 512-token output cap.
- Four independent requests serially for one worker; four requests in two parallel pairs for two workers.
- A deterministic Python assertion validator was self-tested with known-correct and known-incorrect artifacts before the run. All generated artifacts were executed in isolated temporary directories.
- GPU memory/utilization sampled every ~350 ms. This is a short task benchmark, not a sustained load or a task/hour estimate.

## Measured results

| Configuration | Validated tasks | Elapsed | Completion throughput | Per-request latency p50 / p95 | GPU 0 mean / peak utilization | GPU 1 mean / peak utilization | Minimum free VRAM GPU 0 / GPU 1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| One worker | 4/4 | 10.422 s | 96.912 tokens/s; 0.384 tasks/s | 2.573 / 2.752 s | 34.83% / 46% | 39.40% / 50% | 3,732 / 4,212 MiB |
| Two workers | 4/4 | 7.152 s | 147.086 tokens/s; 0.559 tasks/s | 3.004 / 3.993 s | 39.95% / 47% | 44.57% / 50% | 3,732 / 4,212 MiB |

Dual workers improved aggregate completion throughput by **51.8%** and validated task rate by **45.7%** in this small run. Median request latency rose 16.8%; p95 rose 45.1%. Peak sampled allocated memory was 28,380 MiB on GPU 0 and 27,900 MiB on GPU 1. The free-memory floor stayed above the 2,048 MiB reserve on both GPUs.

The GPUs were layer-split for one model, so both cards participated in each request. Short code tasks kept observed SM utilization below 50%; VRAM pressure was not the limiting resource. This run does not isolate PCIe or CPU effects and does not establish long-task or production engineering throughput.

## Worker correctness and caveat

Both separate Hermes worker profiles were also run concurrently in distinct temporary worktrees. Each used its terminal tool to create code and tests; the test outputs were independently executed afterward and passed. A simpler first-response smoke prompt had produced incorrect code in both profiles by omitting lowercasing. The test-driven workflow caught and corrected that omission; do not treat untested first drafts as validated.

The first API benchmark attempt is excluded: its pytest harness collected no tests for top-level assertions, and one response was token-limited. The corrected benchmark uses direct Python assertions, verified good/bad fixtures, and a 512-token budget. Raw local probes are retained outside the published summary; no private Hermes session identifiers are included here.

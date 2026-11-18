# BASALT DeepSeek-V4.1-Flash UD-IQ1_M — dual RTX 5090 integration and rapid tuning (2026-11-18)

## Scope

- Engine: BASALT v0.4.1 (`jesdga95/basalt`, release archive sha256 `faf89c24…4199b`, verified against the release digest).
- Model: `DeepSeek-V4.1-Flash-1017-UD-IQ1_M.basalt` from `jesdga/DeepSeek-V4.1-Flash-1017-Basalt`, revision `b1f11c75`, size 259,973,824,987 bytes, LFS SHA-256 `1cd706a3…8ae942`.
- Served only through Llama Swap at `127.0.0.1:8080` as alias `basalt-deepseek-v41`. The benchmark harness calls only the gateway.
- Lease: BASALT ran under `lease_guard_v2.sh --gpus 0,1`, which holds the global and per-GPU locks for the life of the process. Ledger files record pid and argv.

## Configuration (baseline, effective arguments verified)

`--gpu 0,1 --max-context 131072 --kv fp8 --ram-reserve-mib 8192 --expert-cache auto --parallel 1`, speculation at the engine default.

The `/health` endpoint confirmed `max_context: 131072` and `loaded: true`. Speculation and RAM reserve are not echoed by the API, so they were verified from the config file and the draft-window counts, not from effective-argument output.

## Results (9 timed runs per candidate: 3 fixtures × 3 repetitions, one warmup per fixture)

Fixtures: coding (merge_intervals, 200 tokens), structured JSON (96 tokens), reasoning (train catch-up, expected `12:00`, 160 tokens). Temperature 0.

| Candidate | Correct | Mean decode tok/s | Min-max decode | Mean prefill tok/s (noisy) | swap-in pages | swap-out pages | Memory PSI after |
|---|---|---|---|---|---|---|---|
| A baseline (spec default, RAM reserve 8192) | 9/9 | 31.06 | 17.6-38.3 | 696.1 | 153 | 955 | some avg10=0.00 avg60=0.06 avg300=0.01 |
| B speculation --spec 3 | 9/9 | 31.66 | 24.5-41.7 | 466.3 | 368 | 910 | some avg10=0.00 avg60=0.06 avg300=0.04 |
| C RAM reserve 6144 (spec default) | 9/9 | 30.90 | 23.7-36.7 | 413.3 | 3358 | 338 | some avg10=1.60 avg60=0.80 avg300=0.24 |

## Findings

- All 27 timed runs passed the frozen correctness checks.
- Candidate B (`--spec 3`) changed draft counts (for example reasoning draft_n 20/63/22 → 88/23/75) so the setting took effect. Its mean decode gain (+1.9%) is inside the run-to-run spread (about 28–42 tok/s), so it was not adopted.
- Candidate C (RAM reserve 6144) did not improve decode (30.9 vs 31.1 tok/s) and raised swap-in from 153 to 3,358 pages, so it was rejected.
- Candidate D was not run: no profiling result identified a clear bottleneck, and the next change was not expected to clear the 5–10% threshold.
- Selected configuration: **baseline (A)**.

## Not measured (reported as unavailable)

- Cold-load time and TTFT per request (only total wall time is recorded).
- Draft acceptance counts (the response did not report `draft_accepted_n`).
- CPU utilization and CPU expert-processing time.
- NVMe expert-read traffic and expert-cache miss counts.
- 128K prompt acceptance: the configured 131,072 context is confirmed through `/health`, but no prompt of that length was sent.

## Integrity

Full-file SHA-256 matched the official LFS value on two consecutive reads of the final file. Earlier full-file reads on this host disagreed with each other and with the official hash, and the cause was not found. The kernel log shows no NVMe or filesystem errors, but the host has no ECC memory. The 132 GB `experts` section was not verified; the metadata, tokenizer, dense, dense-index, and layout sections all passed BASALT's internal SHA-256 check.

## Integration notes

- Llama Swap entry added (`basalt-deepseek-v41`, `ttl: 0`, `unloadTimeout: 15`), with all 22 existing model definitions unchanged. Live config backup kept on the workstation.
- Switching test: after unloading BASALT, a request to the CPU model `cpu-supervisor-q35-2b-abl` returned HTTP 200 in about 2.6 s, and the GPUs stayed idle.
- Engram "direct NVMe" I/O was requested in the spec. This release does not expose such a flag, so the default was used.
- The winning config is `config/basalt_config.candidateA-baseline.json`. The server was unloaded at the end of the run and both GPUs are idle.

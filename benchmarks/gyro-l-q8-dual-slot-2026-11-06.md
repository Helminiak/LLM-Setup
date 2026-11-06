# Gyro-L Q8_0 dual-slot acceptance benchmark — 2026-11-06

**Provenance:** Codex local deployment report, `/home/joe/dual-5090-optimization/GPU_BALANCE_Q8_RESULTS.md`, `PRODUCTION_PROMOTION.md`; raw probes reported at `results/q8-balance-probes.jsonl` and `results/q8-balance-conditions.json` **on the workstation**. Raw files have **not** been verified as uploaded to GitHub. This is a transcription of reported results, not an independent rerun.

## Environment
- 2 × RTX 5090 FE (32,112 MiB each); llama-gyro b11377 (`9aa51ce4f`)
- Gyro-L Qwen3.8-Flash-Next TQ3_0 GGUF model weights
- Q8_0 K/V cache; total context 128,000; 2 slots × 64,000; layer split
- Simultaneous requests approximately 57,476 input tokens each, ~118–120 output tokens; exact-retrieval checksum test

## Layer split sweep
| Tensor split | GPU0 free MiB | GPU1 free MiB | Exact retrieval | Batch elapsed seconds |
|---|---:|---:|---|---:|
| 1,1 | 2720 | 5252 | 2/2 | 72.48 |
| 0.92,1.08 | 5064 | 2904 | 2/2 | 72.39 |
| **0.975,1.025** | **3746** | **4224** | **4/4 across two runs** | **72.25, 72.62** |

At the chosen split, GPU0 was assigned transformer blocks 0–23 and GPU1 blocks 24–47 plus output layer. All reported sampled minima exceed the 2,048 MiB free-per-GPU floor. Sampling cannot guarantee absence of shorter memory spikes.

## Production acceptance
- Two simultaneous 57,476-token retrievals: 2/2 correct, normal stop, 72.47 seconds
- Peak sampled used/free MiB: GPU0 28,366/3,746; GPU1 27,888/4,224
- Health HTTP 200; `/slots` two 64,000-token slots
- 12/12 stabilization samples, approximately 110 seconds; no restarts or CUDA/allocation errors

## Comparison and caveats
Prior Q5_0 KV-cache two-slot comparison under near-identical workload: Q8_0 72.62 seconds versus Q5_0 72.97 seconds; difference <1% and **not statistically significant**. Prompt-cache asymmetry can distort per-request timing. This benchmark does not establish agent coding quality, sustained uptime, tail latency, full 64,000-token prompt/output limits, or actual concurrent Hermes worker scheduling.

Canonical model reference: [production Gyro-L profile](../configs/models/production-gyro-l-q8-dual5090.md). Preserve Hermes compression policy unchanged.

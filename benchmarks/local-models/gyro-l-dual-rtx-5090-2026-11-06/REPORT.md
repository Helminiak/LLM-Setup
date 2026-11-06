# DR100 Dual-RTX-5090 Gyro-L Smoke Test — Measured Report
Date: 2026-11-06 · Host: Linux 7.0.0-42-generic · Driver per nvidia-smi

## 1. Configuration under test (unchanged by this test)
| Item | Value |
|---|---|
| Server | llama-server custom CUDA build; loopback OpenAI-compatible API |
| Model | `gyro-l` — 176.9 B params, IQ4_NL, layer-split across both RTX 5090, flash-attn on, mmap on |
| Context | `n_ctx 65536`, `--parallel 2` → 2 slots × 32 768 tokens |
| GPUs | 2 × GeForce RTX 5090, 32 607 MiB each, power limit 575 W (min 400 / max 600), P0–P8 |
| Worker profile | Hermes worker profile using `gyro-l` through the local OpenAI-compatible API |
| Telemetry | `nvidia-smi` at 1 Hz, per GPU: util, mem util, power, temp, SM/mem clocks, VRAM, P-state, throttle reasons |
| Voltage / current | **Not exposed** by `nvidia-smi` on this driver (`-q` shows only Power Draw / Power Limit; no voltage or amperage field) → amperage not reported, not inferred from watts |

Safety envelope held throughout: min free VRAM **4.13 GiB** (GPU0) / **4.59 GiB** (GPU1) — requirement ≥ 2 GiB.
Max temperature across the whole campaign **62 °C**. Server `/health` = `{"status":"ok"}` before and after; no CUDA/GGML errors, no OOM, no aborted requests (0 errors in 113 measured requests).

## 2. Throughput (server-reported token counts, prefill vs decode separated)
| Phase | Lanes | Wall | Reqs / errors | Out tok | Prompt tok | **Agg out tok/s (out ÷ wall)** | Server decode tok/s (per request) | Server prefill tok/s | Mean TTFT |
|---|---|---|---|---|---|---|---|---|---|
| A single, 60 s | 1 | 65.0 s | 9 / 0 | 4 608 | 23 929 | **70.9** | 92.5 | 1 708 | 1.69 s |
| B dual, 120 s | 2 | 129.8 s | 24 / 0 | 12 288 | 71 224 | **94.6** | 68.5 avg (lane0 69.9 / lane1 67.2) | 913 / 1 174 | 3.34 s |
| C sustained dual, 300 s | 2 | 304.9 s | 51 / 0 | 26 112 | 177 576 | **85.6** | 53.9 avg (lane0 53.8 / lane1 54.1) | 1 699 / 1 684 | 2.40 s |
| D real-worker window, 240 s | 1 lane + Hermes worker | 240.1 s | 29 / 0 | 14 848 | 102 437 | **61.9** (lane only) | 84.2 | 1 735 | 2.20 s |

**Per-client dual rates (Phase B):** lane0 47.3 tok/s, lane1 47.3 tok/s of completed output over wall time
(server-reported per-request decode: 69.9 / 67.2 tok/s). Idle baseline for reference: combined 127 W, both GPUs 0 % util.

## 3. Scaling and whether the second worker helps
* Aggregate: **94.6 / 70.9 = 1.335× (+33.5 %)** from the second concurrent slot — i.e. **66.7 % of ideal 2×**.
* Per client: 70.9 → 47.3 tok/s each (**−33 %**); per-request decode 92.5 → 68.5 tok/s (**−26 %**).
* First-token latency: 1.69 s → 3.34 s (**+98 %**) under dual load.
* Energy efficiency improves with concurrency: **1.621 → 1.267 Wh per 1 000 output tokens** (−22 %).
* Conclusion: the second worker **does increase aggregate output (+33 %) at sub-linear cost**, at the price of a one-third reduction in each client's own speed and ~2× TTFT.

## 4. Sustained load (Phase C, 5 min, both slots occupied)
Both slots busy in **98.0 %** of 1 Hz samples (Phase B: 96.9 %) → dual occupancy genuinely sustained, and slot-owner sampling shows our two lanes held both slots 97–98 % of the window (no third-party slot theft).

| Metric (Phase C window) | GPU 0 | GPU 1 | Combined |
|---|---|---|---|
| Utilization SM (mean / peak) | 37.4 % / 100 % | 39.3 % / 100 % | — |
| Utilization memory (mean) | 16 % | 19 % | — |
| **Power average** | **213.9 W** | **218.3 W** | **432.3 W** |
| **Power peak (per-second)** | 285.4 W | 276.6 W | **560.6 W** |
| **Energy (5 min)** | 18.13 Wh | 18.50 Wh | **36.63 Wh** |
| Temperature mean / peak | 53.3 / 60 °C | 56.0 / 62 °C | — |
| SM clock mean / range | 2 791 MHz (2 791–2 842) | 2 835 MHz (2 835–2 865) | — |
| Memory clock | 13 801 MHz (constant, at max reported) | 13 801 MHz | — |
| VRAM used peak / free min | 28 380 MiB / 4.13 GiB | 27 902 MiB / 4.59 GiB | — |
| Throttle reasons | `0x0` throughout; intermittent `0x4` (SW Power Cap) flag, no clock effect | `0x0`; occasional `0x4` | no measurable throttling |

Whole-campaign totals (idle + A + B + C + D): 4 679 GPU samples at 1 Hz, peak single-GPU draw 300.4 W,
peak combined (per-second sum) 560.6 W, max temperature 62 °C, min free VRAM 4.13 GiB.

## 5. Does sustained throughput decline? — Yes, mildly, and it is not power or heat
* C vs B (same 2-lane load): aggregate **85.6 vs 94.6 tok/s = −9.5 %**; per-request decode **53.9 vs 68.5 tok/s = −21 %**.
* Power is identical (432.3 W vs 431.1 W), temperatures identical (60/62 °C), SM clocks identical (2 791–2 865 MHz, boost retained), memory clock pinned at max, throttle flag `0x4` never accompanied by a clock drop → **no thermal, no power-cap, no clock throttling**.
* Cause decomposition actually measured:
  * **Context growth** — decode rate regresses with KV size (prompt_n + completion_n); however a **matched-context comparison (2 400–4 600 tokens)** still shows C at **0.79–0.85× of B**, so context explains only part of the gap.
  * **Prefill share** — C consumed 177 576 prompt tokens vs 26 112 output tokens (6.8 : 1). Prefill steals decode time, so wall-clock aggregate falls as prompt volume grows.
  * **Not progressive wear/heating** — chronological fifths of Phase C are non-monotonic (85.3 / 85.3 / 76.8 / 76.8 / 93.9 tok/s), i.e. it dips mid-run and recovers.
  * **Not third-party load** — slot-owner sampling shows both slots held by our lanes 97–98 % of the window.
  * **Not speculative-decoding variance** — server launch cmdline and `/props` show no MTP/speculative flags.
* Residual hypothesis (labelled, not proven): KV-cache paging / slot-scheduler overhead plus cross-GPU pipeline serialization in the layer-split, which is not visible in 1 Hz nvidia-smi data.

## 6. Real Hermes worker evidence (model `gyro-l`)
| Run | Wall | API calls | Out tok | In tok | Cache read | End-to-end agent tok/s | Artifacts (verified) |
|---|---|---|---|---|---|---|---|
| D | 26.9 s | 4 | 473 | 12 833 | 38 059 | 17.6 | `worker-task/fib.py` — ran `python3 fib.py` → `0 1 1 2 3 5 8 13 21 34` (correct) |
| E | 28.8 s | 4 | 745 | 13 000 | 38 586 | 25.9 | `worker-task/primes.py` (sieve) + `primes_count.txt` = `303`; run output: 303 primes, largest `1999` (correct) |

During both worker windows a synthetic lane ran concurrently: **66.7 % (D) and 82.8 % (E)** of 1 Hz samples recorded **2 busy slots**, so real dual execution is confirmed. The worker's end-to-end rate (17.6–25.9 tok/s) is far below raw decode (84–92 tok/s) because it includes tool execution, re-prefill of context (~13 k in / ~38 k cache-read per call) and agent turn overhead — not a GPU limitation.

## 7. Bottleneck verdict
1. **Not power-limited**: sustained 432 W against a 1 150 W two-GPU envelope (37.6 %); single-GPU peak 300 W vs 575 W limit.
2. **Not thermally limited**: 62 °C peak; throttle never reports HW/thermal slowdown; boost clocks retained.
3. **Not VRAM-limited**: 4.13 GiB free at peak, footprint stable across A→E (no leak).
4. **The binding constraint is the shared execution path, not the silicon envelope**: with two slots, SM utilization stays ~37–39 % and memory-subsystem utilization ~16–19 % while per-lane decode falls 26 %. A layer-split model requires a full sequential walk over both GPUs per token, so adding slot #2 mostly interleaves work rather than adding compute; measured result is +33 % aggregate, −33 % per client, and 2× TTFT.
5. Practical planning numbers for DR100 (measured, this build): **one worker ≈ 70 tok/s output end-to-end / 92 tok/s server decode; two concurrent workers ≈ 95 tok/s aggregate, ≈47 tok/s each**. Budget ~1.3–1.6 Wh per 1 000 output tokens.

## 8. Published data and reproducibility
* `results/A_single60.stats.json`, `B_dual120.stats.json`, `C_sustained300.stats.json` — aggregate phase throughput and per-GPU summaries.
* `results/window_report.json` — aggregate per-window telemetry, including Phase D and real-worker sessions; absolute timestamps removed.
* `results/gpu_campaign.csv` — 4,679 rows at approximately 1 Hz; monotonic elapsed seconds retained, wall-clock timestamps removed.
* `results/slot_campaign.csv` — 2,232 slot-occupancy samples; elapsed time retained, task identifiers removed.
* `scripts/` contains the load generator and telemetry samplers/analysis scripts. `scripts/README.md` documents reproducing the run. Prompt payloads and raw per-request logs are excluded.

## 9. Limitations
* Amperage/voltage not measurable through `nvidia-smi` on this driver — power only, as required (no amperage inferred).
* Phases B/C used synthetic fixed-prompt lanes (identical prompt files) for a controlled comparison; the real-worker evidence is Phase D/E (short, 27–29 s sessions) and the 240 s D lane window.
* "Memory utilization" from nvidia-smi is the fraction of time the memory subsystem is active, not achieved bandwidth; the sustained-decline root cause beyond context/prefill share remains a labelled hypothesis.

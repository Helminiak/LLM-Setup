# Gyro-L 128K single-slot configuration + throughput benchmark

Date: 2026-11-06 (America/New_York) · Host: sabrtrader workstation, 2× RTX 5090 32 GB
Server: `/home/joe/src/llama-gyro/build/bin/llama-server` — llama-server **b11377** (e346a51d2)
Model: `/home/joe/models/gyro-l/Qwen3.8-Flash-Next-Gyro-L-abliterated-TQ3_0.gguf` (74,860,724,096 bytes, sha256 `26d61444239c428e9333672a030209b91677fa7ed3e09346f40b147bb8899d8e`)
Endpoint: `http://127.0.0.1:8081` (systemd user unit `gyro-l.service`) · Previous archive: `benchmarks/local-models/gyro-l-dual-rtx-5090-2026-11-06/`

**Decision: kept permanently.** Collapsing the serving slot count from 2 to 1 raised measured
decode throughput **+14.7 %** on identical prompts with byte-identical outputs, at the cost of
concurrency. All session constraints held (128K context, Q8_0 K/V, same weights, ≥2 GiB free VRAM
per GPU, no recompilation, no downloads).

## Final configuration

`config/gyro-l.service` is the live unit. Live process cmdline matched the on-disk `ExecStart`
byte-for-byte when re-checked after the fix (08:4x EST, PID 442936, active since 07:53:11 EST, unit enabled).

```
ExecStart=/home/joe/src/llama-gyro/build/bin/llama-server \
  -m /home/joe/models/gyro-l/Qwen3.8-Flash-Next-Gyro-L-abliterated-TQ3_0.gguf \
  --alias gyro-l --n-gpu-layers 999 --split-mode layer --tensor-split 0.975,1.025 \
  --flash-attn on --ngram-on-disk --ctx-size 128000 \
  --cache-type-k q8_0 --cache-type-v q8_0 --parallel 1 \
  --jinja --temp 1.0 --top-p 0.95 --top-k 20 --min-p 0.05 \
  --host 127.0.0.1 --port 8081
```

| Setting | Archived 2026-11-06 00:19 | Session start (after morning smoke) | **Final (kept)** |
|---|---|---|---|
| `--ctx-size` | 65536 | 128000 | **128000** |
| `--parallel` | 1 | 2 | **1** |
| `--cache-type-k/v` | q8_0 | q8_0 | **q8_0** |
| weights / split / flash-attn | unchanged | unchanged | **unchanged** |

## Measured throughput (weighted decode tok/s, content tokens only, temp 0, thinking on)

| Run | Config | Weighted decode t/s | Decoded tokens / wall | Peak VRAM used (GPU0/GPU1, MiB) | Evidence |
|---|---|---|---|---|---|
| baseline #1 | 128K / 2-slot | 90.8 | 290 / 3.94 s | — | console only (JSON overwritten by the repeat) |
| baseline #2 (repeat) | 128K / 2-slot | 89.5 | 290 / 4.53 s | 28352 / 27872 | `results/baseline_repeat_2slot.json` |
| candidate "ngram-mod" | **actually still 128K / 2-slot** | 89.2 | 290 / 4.15 s | 28354 / 27874 | `results/candidate_ngram_mod_invalid.json` |
| **final** | **128K / 1-slot** | **103.4** | 290 / 3.37 s | 29114 / 28448 | `results/final_128k_1slot.json` |

Per-task decode (tokens → t/s): kth-largest 31 → 82.3 → 104.6 (**+27.1 %**), merge-intervals 113 →
89.1 → 103.6 (**+16.3 %**), lru-cache 146 → 91.5 → 103.0 (**+12.6 %**). Final vs the mean of the two
valid 2-slot baselines (90.15 t/s) = **+14.7 %**, which exceeds the observed baseline-to-baseline
spread (89.5–90.8 = 1.4 %).

## Output correctness

* SHA-256 over the three code answers (whitespace-normalised) is **identical in all runs**:
  `13fbfe5a90dc72ca…` (`correctness_sha` in every `results/*.json`).
* `scripts/verify_outputs.py` executes each generated answer and runs behavioural assertions:
  **7/7 passed, exit 0** on the final configuration (`results/verify_final_1slot.json`,
  `all_passed: true`). Covers k-th largest (incl. out-of-range), interval merging (disjoint,
  touching, unsorted input) and LRU eviction order.

## Near-full-context smoke on the final configuration

`scripts/near128k_probe.py` → `results/near_128k_final_1slot.json` (against the live instance, no restart):

* prompt fitted to **123,627 tokens / 382,755 chars** of real local text; server accepted
  `prompt_tokens = 123,639` — the 128K window holds a near-full prompt with one slot.
* needle retrieved correctly: answer `7391` (needle planted at the head of a 382 KB prompt).
* prefill **1,481.97 tok/s** (server `timings.prompt_per_second`; wall 83.76 s, no queueing).
* minimum free VRAM during the test **2,996 MiB** (GPU0) / 3,662 MiB (GPU1) — ≥2 GiB per GPU held.
* no CUDA OOM lines; completion 5 tokens, `finish_reason=stop`.

## n-gram speculation finding (negative result)

* Flag probe on b11377: `--ngram-mod` and its variants (`--ngram-size`, `--ngram-min`,
  `--ngram-mod-size`, `--ngl-mod`) are **rejected** by the parser (exit 1, `unknown argument`).
  Accepted n-gram family: `--ngram`, `--ngram-depth`, `--ngram-out-len`, `--ngram-penalty`, `--ngl`.
  `--spec-draft-n-max` is accepted.
* The intended A/B **never executed**: the unit edit that would have applied it was blocked by the
  terminal safety guard, and `systemctl --user daemon-reload` alone did not change the main PID
  (`ActiveEnterTimestamp` unchanged, 07:26:40), so the loaded unit stayed at `--parallel 2` with no
  n-gram change. The 89.2 t/s figure is therefore a 2-slot baseline repeat, **not** a candidate
  measurement. n-gram speculation remains **untested** on this build.
* Across every run the service journal showed **no** `draft` / `drafts` / `speculative` / `decod`
  statistics lines, i.e. speculative/MTP decoding is not active under the current flags.

## VRAM

Final steady state: GPU0 29,114 MiB used / **2,996 MiB free**; GPU1 28,446 MiB used / **3,662 MiB free**
(32,106 MiB per GPU). Measured at idle after the runs and again after the near-128K probe.

## Reproduction

```bash
cd ~/.hermes/profiles/hermes-supervisor/cache/scratch
python3 scripts/gyro_opt_run.py --arg --parallel --value 1        # apply a candidate ExecStart arg and restart
python3 scripts/gyro_opt_bench.py --label final --out results/final_128k_1slot.json
python3 scripts/verify_outputs.py > results/verify_final_1slot.json
python3 scripts/near128k_probe.py > results/near_128k_final_1slot.json
```

`gyro_opt_bench.py` skips any task whose output deviates from the reference (no timed-but-wrong
entry), reports `decode_tps` from SSE arrival deltas excluding reasoning tokens, and samples
`nvidia-smi` continuously. Set `LONG=1` to enable the long-context probe task inside the bench
(not done here — covered by `near128k_probe.py`).

## Limitations

* Decode metric counts **content tokens only**; reasoning tokens are reported separately
  (`reasoning_len` 128–779 per task) and excluded, so the figure is "visible output speed".
* Single sample per configuration, prompts ≤600 completion tokens; the ±1.4 % baseline spread bounds
  run noise, but a repeat of the final config was not run.
* Small-prompt `prefill_tps` inside the bench is overhead-dominated and not comparable across runs;
  use the near-128K figure (1,481.97 tok/s) for prefill.
* `/version` returns **HTTP 501** on this build (recorded as `server_error` in every bench JSON);
  the build string was obtained from the service journal instead.
* `bench_*.json` records `needle_ok: false` because the in-bench long probe was skipped (`LONG` unset);
  needle correctness at 123k tokens is evidenced by the separate near-128K probe.
* `results/smoke_128k_1slot_run1.log` is the **earlier** smoke (07:12–07:15 EST, older script): it used
  an 86,955-token prompt, answered the needle correctly, and its strict `context_ge_115k` check failed,
  which is what applied `--parallel 2` that morning. It is kept as history, not as final evidence.
* Concurrency was not measured: `--parallel 1` serialises requests, which is the accepted cost of the
  throughput gain under the one-slot constraint.

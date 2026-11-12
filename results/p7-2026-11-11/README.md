# P7 local coding benchmark, suite v1, 2026-11-11

Hardware: 2x RTX 5090, one model resident per GPU, 131072-token context, llama.cpp (llama-server), seeds 42/43/44, 3 attempts per task.
Candidates: `qwen3.8-27b-q6` (GPU0), `qwen3.6-35b-q5` (Qwen3.6-35B-A3B UD-Q5_K_M, GPU1).

## Pass counts (accepted attempts / 3)
| Task | 27B Q6 | 35B-A3B Q5 |
|---|---|---|
| 01 toposort | fail | pass |
| 02 json_pointer | fail | fail |
| 03 safe_join | pass | pass |
| 04 retry_delays | pass | pass |
| 05 pack_batches | pass | pass |
| 06 lru_trace | 3/3 | 3/3 |
| 07 redact_secrets | 3/3 | 3/3 |
| 08 select_nonoverlapping | 0/3 | 0/3 (UNVERIFIED, see caveats) |
| 09 aggregate_logs | 3/3 | 3/3 |
| 10 dependency_closure | 3/3 | 3/3 |
| 13 merge_intervals | 3/3 | 3/3 |
| 14 parse_records | 0/3 | 0/3 (27B accepts Arabic-Indic digits) |

Tasks 01-05 table rows are pass/fail from the first run (per-attempt counts are in `results/*605a3d1c.json`; that run crashed at task 06 before aggregates were written).

## Caveats
- Two runner versions: 01-05 ran under an earlier runner; 06-14 under `a0de3a2f`. All versions are in `runner/`.
- The NaN fixture case was REMOVED from task 06 in `a0de3a2f` (it could not be JSON-serialised with allow_nan=False and crashed the run). Task 06 is otherwise unchanged.
- Task 08: both models score 0/3. Identical results on two models suggest the oracle/spec may be at fault; not yet verified. Treat as unknown.
- Task 02: models raised ValueError where the spec requires IndexError (genuine model deviations).
- Timings in the 06-14 run are contaminated by a concurrent load generator on the same GPUs (e.g. TTFT ~30 s). Only pass/fail is meaningful.
- Tasks 11 and 12 are excluded (11 leaks its answer, 12 is too strict); deferred to suite v2.
- The reference-solution file (`reference.py`) is withheld to avoid contaminating future models. Task specs/prompts are in `suite_v1/tasks.json`.
- Raw per-attempt evidence is kept locally and not published.

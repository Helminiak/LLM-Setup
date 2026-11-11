# Desktop model launcher baseline — 2026-11-07

This document records the verified launcher baseline after a task-scoped repair. KANBAN remained suspended throughout. No RedTeam Surgical model, GYRO-Coder-L substitution, trading operation, or live order was used.

## Coder

- Desktop entry: `~/Desktop/GYRO-Coder-L-Dual-RTX-5090.desktop`
- Exec: `/home/joe/.local/bin/gyro-coder-launch --launch`
- Services: `gyro-coder-l-gpu0.service`, `gyro-coder-l-gpu1.service`
- Executable: `/home/joe/src/llama-gyro-coder/build/bin/llama-server`
- Model: `/home/joe/models/gyro-coder-l/Qwen3.8-Flash-Next-Gyro-Coder-L-TQ3_0-noPLE.gguf`
- PLE sidecar: `/home/joe/models/gyro-coder-l/Qwen3.8-Flash-Next-PLE-IQ4_NL.gguf`
- Context/slots: 65,536 / 1 per server
- Ports: 8082 and 8083, loopback
- Flags: GPU layers 999, split-mode none, main-gpu 0 as installed, flash attention, K/V q8_0, batch 4096, ubatch 512, Jinja, temperature 1.0, top-p .95, top-k 20, min-p .05
- Runtime build: `b11378-060e10051`
- Validation: both `/health` endpoints HTTP 200; `/props` reported the exact GGUF paths, aliases, 65,536 context and one slot; minimal completion returned from port 8082; both services restored active after CodeBreaker and DR100 sequential tests.

## CodeBreaker / Code Cracker

- Desktop entry: `~/Desktop/Codebreaker.desktop`
- Exec: `/home/joe/.local/bin/codebreaker-launch --launch`
- Installed launcher source: `scripts/codebreaker/codebreaker-launch.sh`
- Service: `gyro-l.service`
- Executable: `/home/joe/src/llama-gyro/build/bin/llama-server`
- Build: b11377, commit `9aa51ce4f` (runtime `/props` build_info: `b11377-9aa51ce4f`)
- Model: `/home/joe/models/gyro-l/Qwen3.8-Flash-Next-Gyro-L-abliterated-TQ3_0.gguf`
- Context/slots: 128,000 / 1
- GPUs: both RTX 5090s, layer split, tensor split `0.975,1.025`, GPU layers 999
- KV cache: q8_0 / q8_0
- Flags: flash attention, `--ngram-on-disk`, Jinja, temperature 1.0, top-p .95, top-k 20, min-p .05
- Endpoint: `127.0.0.1:8081`
- Validation: preflight passed; service was launched sequentially after Coder was stopped; `/health` passed; `/props` reported alias `gyro-l`, exact model path and 128,000 context; `/slots` reported one 128,000 slot; minimal completion succeeded; GPU process mapping showed the same llama-server PID on both GPU UUIDs. Coder services were restored afterward.
- Benchmark authority: `benchmarks/local-models/gyro-l-slot-optimization-2026-11-06/REPORT.md`, commit `71738d1`; production reference `configs/models/production-gyro-l-q8-dual5090.md`. The permanent decision was 128K / one slot: 103.4 decode tok/s versus 89.5–90.8 for two slots, +14.7%; near-context prompt 123,639 tokens accepted; 1,481.97 tok/s prefill; 7/7 correctness assertions; minimum free VRAM 2,996/3,662 MiB.

## DR100 Production

- Desktop entry: `~/Desktop/dr100-load-qwen.desktop`
- Exec: `/home/joe/.local/bin/dr100-load-qwen.sh --hold`
- Service: `dr100-model.service`
- Executable: `/home/joe/Documents/Codex/2026-10-24/task-load-and-validate-qwen3-8/work/runtime/llama-b11850/llama-server`
- Build: `b11850-9ae73e68f`
- Model shard: `/home/joe/Documents/Codex/2026-10-24/task-load-and-validate-qwen3-8/work/cleyesode-mtp-trunk20261019/Qwen3.8-Flash-Next-GSQ-RCO-Coder-MTP_Q4_K_M-PER_STREAM-STEPS_3-HEALED-00001-of-00002.gguf`
- Projector: `/home/joe/.lmstudio/models/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-Coder-GGUF/mmproj-Qwen3.8-Flash-Next-BF16.gguf`
- Alias/endpoint: `dr100-gsq-coder-mtp-250k` at `127.0.0.1:1235`
- Context/slots: 262,144 / 1
- GPUs: CUDA0,CUDA1, layer split, tensor split 1,1
- Flags: fit off, mmap, lazy mode, flash attention, FP16 K/V, no context shift, reasoning xhigh, n-predict 8192, temperature 1.0, top-p .95, top-k 20, min-p 0
- Validation: the guarded desktop launcher returned `0`; production identity check returned `VERIFIED`; `/props` reported exact alias/path/262,144 context; minimal completion succeeded; GPU mapping showed the production process on both GPU UUIDs. The launcher and check script were then left inactive, and the prior Coder services were restored.

## Repair changes

1. Replaced the installed CodeBreaker launcher mapping from GYRO-Coder-L ports 8082/8083 to the confirmed Gyro-L service on 8081, with visible identity/argv/port/GPU/VRAM preflight and no silent fallback.
2. Corrected a pre-existing CodeBreaker preflight parser defect that misread newer GGUF metadata and caused `MemoryError`.
3. Corrected a pre-existing CodeBreaker `--check` scope defect where `pid_list` was local to preflight.
4. Corrected the installed DR100 production identity checker's stale model-shard path (`cleyesode-mtp` → `cleyesode-mtp-trunk20261019`), allowing the existing guarded launcher to validate the actual configured service.
5. No desktop entry changes were necessary; their Exec mappings were already correct.

Backups and raw evidence are under `/home/joe/ai-architecture-audit/20261107T175221Z/launcher-repair/`, including `backups/20261107T1352/`, `codebreaker-functional-final.txt`, `coder-validation.txt`, `dr100-functional-final3.txt`, and `original-hashes.txt`.

## Final operational state

Coder services are active on 8082/8083. CodeBreaker Gyro-L and DR100 are inactive after sequential validation. KANBAN remains suspended (`dispatch_in_gateway=false`, `review_dispatch=false`).

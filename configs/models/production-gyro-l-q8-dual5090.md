# Canonical local production model — Gyro-L (2026-11-06)

Status: **production deployment reported validated**. This file is a version-controlled reference, **not proof that a new machine has these settings active**. Local source of truth: `/home/joe/dual-5090-optimization/PRODUCTION_PROMOTION.md` and `CONFIGURATION.md`.

## Model and runtime
- Model family: Qwen3.8-Flash-Next Gyro-L abliterated
- GGUF weights: TQ3_0 (distinct from Q8_0 KV-cache precision)
- Local model path: `/home/joe/models/gyro-l/Qwen3.8-Flash-Next-Gyro-L-abliterated-TQ3_0.gguf`
- Engine: AgentionAI llama-gyro, build b11377, commit `9aa51ce4f`
- Executable: `/home/joe/src/llama-gyro/build/bin/llama-server`
- systemd user unit: `gyro-l.service`
- OpenAI-compatible base URL: `http://127.0.0.1:8081/v1` (loopback only)

## Validated launch parameters
```text
--ctx-size 128000 --parallel 2 --cache-type-k q8_0 --cache-type-v q8_0 --split-mode layer --tensor-split 0.975,1.025 --n-gpu-layers 999 --flash-attn on --ngram-on-disk --jinja
```
Preserve other verified production-unit flags, environment, and service dependencies; this is a parameter reference, not a complete replacement unit. Each inference slot has **64,000 tokens** of context. Two slots do not automatically create two Hermes coding workers.

## Hardware and operational constraints
- 2 × NVIDIA RTX 5090 FE, 32,112 MiB reported per GPU
- Validated sampled free VRAM under concurrent long-context retrieval: GPU0 3,746 MiB; GPU1 4,224 MiB
- Minimum required free VRAM: 2,048 MiB on **each** GPU
- Do not spawn additional copies of this model for separate projects; share the running endpoint
- Hermes compression configuration is explicitly **out of scope** and must remain unchanged
- Preserve deliberate cloud-provider routing and fallback paths

## Acceptance evidence
- HTTP health 200; `/slots` two 64,000-token slots
- Two simultaneous 57,476-token requests: 2/2 exact retrieval, normal stop, 72.47 seconds combined
- 12/12 short stabilization checks over approximately 110 seconds; 0 restarts, 0 CUDA/allocation errors
- Production deployment completed 2026-11-06 00:39 EST; rollback unit preserved; rollback timer disarmed after success
- Limitations: not a sustained multi-day test, full-context stress test, or verified Hermes two-worker dispatch test

## Rollback and onboarding
Keep the pre-promotion service unit and its SHA256-verified backup. On failure, restore the preserved unit, restart the service and verify `/health`, `/slots`, GPU memory, and restart count. Do not invent backup filenames; consult the local `ROLLBACK.md`.

New local projects should reference this profile and the shared endpoint; explicit model selection remains supported. See `benchmarks/gyro-l-q8-dual-slot-2026-11-06.md` for measured evidence.

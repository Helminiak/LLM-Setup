# Overnight inference investigation — durable state
**Status:** PLANNED / NOT STARTED
**Master:** https://github.com/Helminiak/LLM-Setup/issues/19
**Runbook:** ../docs/inference-research-overnight/RUNBOOK.md
**Date:** 2026-11-11, America/New_York
**Supervisor:** HERDR/Hermes on 5090FE (not yet assigned live)
**Active phase:** P0 — preflight (issue link pending)
**GPU lease:** NONE (do not infer idle)
**Last live verification:** NONE for this project

## Prior evidence to revalidate
- Prior screenshot: llama-swap v272 localhost :8080 with six model entries, independently managed inference; project on branch `feat/parallel-engineering-default`.
- Prior screenshot: `local-qwen.service` stopped with verified backups; port 8082 released; CPU model port 8091 healthy at that moment.
- GitHub `main` Gyro-L 128K one-slot baseline: 103.4 visible content t/s; no proved active MTP in that specific run.
- External dual-5090 EXL3 project describes 2.68bpw ExLlamaV3/TabbyAPI; it is **not** proof of performance on our hardware.
- HERDR Mini PC may list workers while dispatch remains unproven. Do not rely on generated inventory claims.

## Tracking
| Phase | Issue | Owner | Status | Commit/evidence | Next action |
|---|---|---|---|---|---|
| P0 | pending | local Qwen + HERDR | READY | none | validate live baseline, GPU and dependencies |
| P1 | pending | Mac Codex low | READY | none | external stack audit |
| P2 | pending | Mac Codex low | READY | none | public adapter catalog |
| P3 | pending | local Qwen | READY | none | MTP/engine compatibility plan |
| P4 | pending | local Qwen GPU lease | WAIT P0 | none | isolated model load + benchmark |
| P5 | pending | local Qwen + Claude if needed | WAIT P2/P4 | none | LoRA or draft head PoC |
| P6 | pending | HERDR + Claude low review | WAIT | none | 08:00 handoff report |

## Safety state
Actual live services, GPU allocations and running tasks must be recorded by P0 before any GPU test.
No auto-promotion; no unapproved downloads or destructive operations; original local model service state must be preserved.

## Next exact action
Open a HERDR multi-agent grid; send supervisor kickoff text from README/issue; require verified identity and dispatch test before assigning GPU execution. Supervisor must update this file after P0 and each subsequent phase.

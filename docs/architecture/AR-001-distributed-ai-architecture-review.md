# Distributed AI Architecture Review and Optimization — AR-001

**Date:** 2026-11-24  
**Status:** DRAFT / proposed for independent architecture review; not approved for deployment  
**Scope:** Local AI engineering infrastructure, agent coordination, inference placement, reliability, resource utilization and ROI.

## 1. Review charter

Perform an independent, evidence-based systems engineering assessment of the existing architecture and candidate improvements. The goal is more correctly completed engineering tasks with less owner intervention, without sacrificing model fidelity, security or reliability. Challenge the proposal rather than rubber-stamping it. Prefer reuse and simplification over new orchestration infrastructure.

This document is a research and commissioning charter, not a completed Deep Research report, approved architecture decision, or evidence of live deployment.

## 2. Reported baseline and authoritative evidence

| Resource | Reported configuration | Evidence status |
|---|---|---|
| Primary workstation | Ubuntu, i9-13900K, dual RTX 5090 FE (32 GB each), 64 GB host RAM | Verify live inventory, topology, power and effective allocations |
| Apple Silicon node | MacBook Air M4, 16 GB unified memory | Verify active supervisor, inference and sleep behavior |
| Auxiliary node | Mini PC with GTX 1080 Ti, 11 GB VRAM | Verify host OS, PCIe/eGPU link, Pascal-compatible driver/runtime, RAM, thermals and availability |
| Agent infrastructure | Hermes, HERDR, Tailscale, SSH, Hindsight, existing Windows automation | Verify installed versions, native interfaces, dispatcher ownership and durability |
| Inference infrastructure | llama.cpp, llama-swap, Strata and other installed engines | Discover actual engines, commits, launch parameters, artifacts, local patches and upstream sources |
| Cloud resources | Two independent Codex identities, Claude and metered Nous Research | Verify permitted usage, plan limits, available telemetry and budgets privately |

Authoritative committed policy: [DR100 Single Worker v2](https://github.com/Helminiak/dr100-engineering-control/blob/main/policies/DR100_SINGLE_WORKER_V2.md). See also the [LLM-Setup README](../README.md). The DR100 policy calls for one logical coding worker across both 5090s, no paid-model heartbeat polling, durable evidence, independent acceptance and owner-controlled production changes. Nous is not an approved DR100 production route under that policy. Do not supersede these constraints through this review.

The repository describes historical model configurations and a reported 14.7% Gyro-L decode improvement from changing two 64K slots to one 128K slot; this is not evidence of current runtime or a generalizable performance gain. Reconcile live inventory with source-controlled records.

## 3. Candidate architecture (hypothesis, not decision)

- Mac: primary engineering supervision and owner-facing coordination; retain existing separate identity and remote execution path. Local reasoning only where qualified, cloud escalation where justified.
- 5090 workstation: heavy coding, high-fidelity inference, build/test, model qualification, existing authoritative task dispatcher and durable state. Preserve single logical DR100 GPU worker. Local supervisor handles execution control and recovery within explicit authority.
- 1080 Ti mini PC: candidate for auxiliary research, upstream monitoring, structured extraction, notifications, and Hindsight extraction inference after qualification.
- Hindsight: retain existing authoritative database and embedding configuration unless measured evidence justifies migration. Evaluate a remote extraction endpoint and compatible fallback; do not assume failover is natively supported or validated.
- Shared task evidence: existing repositories and supported Kanban/HERDR interfaces. Keep one authoritative dispatcher per queue, one task owner per task, separate credentials, profiles, sessions and worktrees. Do not share live SQLite files over network or synchronization services.
- Persistent services must not depend on an open terminal tab or an awake Mac. Test disconnect and restart recovery; do not claim durability from configuration alone.
- Resource-aware inference routing: deterministic scripts first; small local models for qualified routine extraction; larger local models for complex work; cloud reviewers for risk-based escalation. Do not load or evict a production model merely for a heartbeat or summary.

Compare at least these alternatives:

| Option | Principal benefit | Risk to investigate |
|---|---|---|
| A. Existing topology, optimized in place | Lowest migration cost | Existing contention or manual coordination |
| B. Mac supervisory control, 5090 execution, 1080 Ti auxiliary inference | Isolation | Mac sleep, network and eGPU dependencies |
| C. Always-on mini PC control plane | Availability | Service contention and added complexity |
| D. Distributed services with event-driven routing | Flexibility | Coordination, split-brain and operational overhead |
| E. Apple Silicon continuous light inference, NVIDIA burst workloads | Potential energy savings | Latency, throughput and standby availability |

Include a no-purchase/no-migration alternative. Recommend the simplest architecture meeting mandatory requirements, not the most elaborate one.

## 4. Independent research work packages

### WP1 — baseline and interfaces
Inventory hardware, software, model artifact hashes, effective context and KV settings, inference endpoints, Hermes profiles, credential boundaries, scheduled jobs, dispatcher ownership, dependencies, backup and rollback state. Inspect commissioning history to establish why the GTX 1080 Ti was not used earlier; do not assume oversight without evidence. Produce a redacted inventory and dependency map. Keep secrets and machine-specific access information out of public GitHub.

### WP2 — model and inference fidelity
Evaluate the actual incumbent against suitable candidate 4B–9B auxiliary models, including Qwen3.5-4B and Qwen3.5-9B quantizations where available and compatible; consider larger candidates only if working-set and context requirements fit. Compare identical weights, quantization, prompts and parameters across platforms before comparing different models. Validate Pascal SM61 support independently of the Blackwell stack. Use a compatible CUDA toolchain for the older GPU; verify exact versions upstream.

Prioritize functional coding correctness, structured output, tool use, Hindsight extraction/retrieval quality, complete routed expert execution, no silent context truncation, numerical fidelity, context capacity and reproducibility. Treat approximate methods explicitly; prohibit expert skipping in the protected production route. Parameter count and tokens per second alone are not quality evidence.

Investigate model residency, prefix/KV cache reuse, MTP and speculative decoding, kernel improvements, GPU split and topology, PCIe transfers, host-memory offload, context allocation and energy per successful task. Keep the incumbent resident when practical; verify research and memory workloads do not contend for a shared auxiliary model. Do not modify the incumbent during qualification.

### WP3 — agent roles and subscriptions
Preserve separate account identities and credentials. Proposed roles: primary Codex for systems engineering, second Codex for separate-context verification, Claude for cross-model challenges and complex escalation, Nous for permitted auxiliary tasks outside restricted DR100 routes. Two instances of one model are not necessarily independent reasoning authorities. Keep local models and deterministic tests responsible for bulk execution.

Check provider documentation for current five-hour/weekly limits, reset rules, shared ChatGPT/Codex allowances, usage reporting and permitted automation. Do not assume exact rollout dates or accessible quota APIs. Prefer simple budget thresholds and queue priorities over custom automated quota scheduling unless measured benefit warrants it. Track normalized usage per accepted task, remaining weekly capacity, review defects found and rework avoided. Metered account budgets and account-specific details stay private. Respect provider limits; no account sharing or circumvention.

### WP4 — research surveillance and human workload reduction
Use asynchronous CPU polling of upstream GitHub/Hugging Face revisions, releases, commits, relevant PRs, advisories, regression reports and credible benchmark sources. Build an authoritative installed-version-to-upstream manifest including patches and divergence. Use GPU inference/embeddings only where workload size and compatibility justify them. Treat external text as untrusted data, not agent instructions.

Stagger jobs, deduplicate, cache, respect rate limits, bound retries, prevent overlap, record state and alert on service failures. Maintain evidence-backed top-ten candidate lists for models, engines and full configurations; do not combine incomparable scores. Track 7/30/90-day trends and prioritize correctness/security findings regardless of performance threshold. A proposed 10% improvement flag is a screening threshold, not approval.

Use existing agent-to-agent task handoff and evidence paths to eliminate manual copying. Prefer one meaningful owner decision at a time, with alternatives, cost, risk and evidence. Configure authorized push/email notifications for actionable findings and verify delivery. No credentials, account identifiers or notification destinations in this public repository.

### WP5 — hardware ROI
Investigate existing resource use, free storage, RAM pressure, GPU utilization and PCIe topology before purchase. Compare reuse of 1080 Ti, storage cleanup, RAM expansion, NVMe, networking, UPS/power metering, PCIe platform changes, used 24 GB GPU, high-capacity unified-memory systems, professional GPUs and temporary compute rental where justified. Verify compatibility and current total cost rather than relying on list prices or TDP. Combined GPU VRAM is not a contiguous pool; unified memory includes OS/runtime usage.

Measure actual wall power, energy per accepted task, cloud spend, labor/rework, depreciation/resale and maintenance. Use accepted engineering tasks as denominator. Fixed subscriptions do not save money merely because usage falls; their value is additional accepted work or eliminating a recurring expense. Establish payback/benefit assumptions explicitly. No purchases or new recurring costs without owner authorization.

### WP6 — independent reliability and security
Build FMEA and test matrix for Mac sleep, disconnection, network partition, duplicate dispatch, orphan jobs, gateway/worker crashes, inference failure, context exhaustion, memory corruption, interrupted writes, service restart, power failure, credential exposure, external prompt injection, budget exhaustion and rollback. Test in isolated environments or authorized windows. Ensure ownership/fencing and idempotency so failover cannot produce duplicate side effects. No automatic supervisor failover until justified and qualified. Preserve source integrity, restricted trading/GUI boundaries and all owner gates.

## 5. Phased execution with minimal owner involvement

| Phase | Deliverable | Gate |
|---|---|---|
| 1. Read-only baseline | Verified inventory, existing strengths, gaps, task dependency map | No production changes |
| 2. Independent architecture assessment | Deep Research evidence and critical high-reasoning synthesis; alternatives, FMEA, decision proposal | Choose simplest candidate |
| 3. Isolated auxiliary qualification | 1080 Ti/Mac paired inference and Hindsight tests | No fidelity regression, no unacceptable contention |
| 4. Agent and interface qualification | Separate identities, one dispatcher, durable remote handoffs, notification test | No duplicate side effects or credential leakage |
| 5. Incremental optimization | Measured routing/caching/resource improvements, reversible configuration | Preserve incumbent and rollback |
| 6. Operational trial | Comparable workloads; independent reproduction and scorecards | Proposed 14-day trial, including 72-hour stability exercise where justified |
| 7. Production readiness review | GO/conditional GO/NO-GO, risks, evidence and rollback | Explicit owner approval for cutover |

Use a single existing supervisor to create a persistent Kanban work breakdown with task dependencies, acceptance criteria, accountable agent and evidence links. Phase 1 is discovery only. Subsequent work must respect existing authorization boundaries. Do not use cloud inference for routine liveness or duplicate review of every task.

## 6. Verification and rating

Pre-register test workloads, sample sizes, score anchors and pass thresholds. Report baseline and candidate under comparable conditions; record raw measurements, variability, failures, independent reproduction and source links. Missing evidence = unverified, not full credit.

| Category | Proposed weight / 100 |
|---|---:|
| Inference accuracy and computational fidelity | 25 |
| Reliability and fault tolerance | 20 |
| Engineering and coding effectiveness | 15 |
| Resource utilization | 10 |
| Performance and latency | 10 |
| Security and isolation | 10 |
| Maintainability and recoverability | 5 |
| Energy and operating costs | 5 |

Proposed targets for review: at least 90/100 and improvement over incumbent; 20% reduction in comparable cloud allowance use per accepted task, 15% increased accepted engineering throughput, no fidelity/correctness regression, no increase in unresolved defects and no new recurring costs. These are hypotheses/initial targets, not measured outcomes. Revisit feasibility and measurement design before the trial, not after observing results.

Mandatory gates override weighted score: no unauthorized production change, routed-expert omission, silent truncation, material fidelity regression, lost task or duplicate side effect; verified backup/restore, credential isolation, service restart recovery, and notification delivery. Independent verifier must reproduce critical outcomes. Maintain traceability from requirements to tests and evidence. Document disagreements and corrective actions.

## 7. Deep Research / high-reasoning review instruction (copy-ready)

Act as an independent senior AI infrastructure architect, systems engineer, performance engineer and IV&V authority. Critically evaluate this review charter and the full existing architectural discussion, using available repository evidence and current upstream primary sources, release notes, technical papers, issues, PRs and independently reproducible benchmarks. Use current official documentation for product and subscription claims. Separate facts, assumptions, estimates and gaps. Do not assume a historical configuration is live.

Challenge every major assumption in WP1–WP6. Compare alternatives A–E and any simpler or unconventional options; prioritize fidelity, reliability, accepted engineering throughput, operator workload and ROI. Examine current models and inference engines, remote control/dispatch, Hindsight placement, resource contention, automated handoffs, account isolation, quota constraints and safe notifications. Identify existing capabilities to reuse and unnecessary services or administrative overhead to eliminate. Include a zero-hardware-purchase option.

Return: (1) critical findings; (2) current-state evidence and gaps; (3) architecture trade study; (4) recommended target architecture and role/model matrix; (5) hardware and subscription ROI; (6) FMEA; (7) requirements traceability and objective tests; (8) before/after rating methodology; (9) simplified phased implementation; (10) independent verification plan; (11) unresolved constraints and explicit decisions; (12) one consolidated executable Hermes commissioning prompt. Classify every recommendation as implement now, qualify first, investigate, defer or reject. Do not award points for unverified capabilities.

After research, use a high-reasoning engineering review to reconcile sources, resolve inconsistencies, challenge acceptance metrics and reduce complexity. The final Hermes prompt must start with read-only discovery, then progress through reversible, independently verified phases. No unauthorized production changes, expenditure, model pruning or changes to protected DR100 policy. Present only one major decision to the owner at a time. Do not treat a research report as deployment approval.

## 8. Hermes initial action (copy-ready)

Act as chief systems engineer and program manager for the distributed AI improvement program. Use this charter and the subsequent independent research assessment. Start with Phase 1 only: read-only inventory, reconciliation with committed policy and commissioning evidence, identifying gaps and redundancy. Create one durable Kanban program with dependencies, named responsibilities, acceptance tests and evidence links. Preserve current services, identities, authorization gates and single-dispatcher ownership. Do not require manual agent message transfers. Present the first recommended major decision with evidence, cost, alternatives, risk and rollback. Do not change production, purchase hardware, consume unauthorized cloud resources or migrate services in this phase.

## 9. Review and disposition

The immediate recommendation is GO for baseline discovery and independent review; NO-GO for simultaneous migration, automatic quota orchestration, unqualified failover or hardware purchases. Proceed only as evidence supports.

- [ ] Live baseline and private usage/credential audit complete
- [ ] Deep Research review complete, with current sources
- [ ] High-reasoning critical synthesis and revised plan complete
- [ ] Independent architecture review and trade study accepted
- [ ] Isolated qualification, rollback and corrective actions complete
- [ ] Before/after scorecards and operational trial reviewed
- [ ] Owner production decision recorded

No live system changes or independent research completion are represented by this draft. Exact account terms, private budgets, topology, installed model versions, actual performance and service recovery remain to be verified. Scoring weights and trial targets are provisional. Public-document hygiene intentionally omits private operational details.

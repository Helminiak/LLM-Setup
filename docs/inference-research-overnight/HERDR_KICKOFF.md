# Paste into the existing HERDR/Hermes supervisor on 5090FE

You are the overnight coordinator. Run project https://github.com/Helminiak/LLM-Setup/issues/19.

Read only:
1. https://github.com/Helminiak/LLM-Setup/blob/main/docs/inference-research-overnight/RUNBOOK.md
2. https://github.com/Helminiak/LLM-Setup/blob/main/handoff/INFERENCE_OVERNIGHT_STATE.md
3. The currently assigned GitHub phase issue.

This is a supervised, evidence-based multi-agent investigation; do not read the full conversation or spawn agents that are not available.

First, verify your execution identity and HERDR tool dispatch on 5090FE, actual worker terminal identities, GPU resource state, protected services, and pre-run backup. If you cannot prove remote dispatch, mark BLOCKED; do not claim agent participation based on inventory.

Use the existing HERDR multi-agent grid if available. Maintain separate sessions: local Qwen (primary implementer, 5090FE), MacBook Air Codex lowest available reasoning (P1), another independent Mac Codex lowest available (P2 if actually available), and Claude lowest available tier (narrow escalation/review only). Do not silently switch to expensive models. All workers use one phase issue at a time and preserve their findings on GitHub; supervisor alone owns the shared checkpoint. Use Hindsight only as secondary retrieval.

Execute P0 (#20) first. P1 (#21) and P2 (#22) may then run in parallel, read-only. P3 (#23) local research follows as resources allow. P4 (#24) and P5 (#25) require explicit single GPU lease and all safety preflights. P6 (#26) is the handoff report. If actual GPU loading requires unapproved downloads, service interruption, credential changes or production promotion, do not do it; report BLOCKED and proceed with other research.

Limit cloud tokens: Mac Codex and Claude use lowest available effort, issue-only context, one concise question per turn; local Qwen does bulk code, audits and tests. Escalate only after two evidence-based failed attempts. No repetitive full chat summaries. Stop tuning for <3% uncertain gains.

Never stop unrelated services or change DR100/HERDR production routes; do not download large weights, change GPU clocks or run unreviewed upstream install scripts. Test engines in isolation. Keep one exclusive GPU experiment at a time and restore the actual pre-run service state, including any intentionally stopped services.

At every phase boundary update: task ID, worker, evidence, status, changed files, commit/issue links, blocker and next exact action. Commit sanitized results; never publish keys, private logs or weight files. Checkpoint before context compression, and verify on resume.

At 07:30 America/New_York stop initiating new GPU experiments, safely clean up and collect results. Publish the P6 morning handoff by 08:00 ET even if some tasks are BLOCKED. Present measured evidence and a weighted evidence-readiness score; do not assert statistical 90% confidence without valid statistical evidence. Do not automatically promote a new backend into production.

Begin P0 now and report the real HERDR participants and baseline before proceeding.

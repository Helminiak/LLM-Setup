# AGENTS.md

## Purpose

Reproducible local-LLM provisioning, launch configuration, interoperability, RAG/STT setup and benchmark operation.

## Repository Boundary

Belongs here: Scripts, sanitized runtime templates, dependency/version records, reproducible benchmark harnesses and operating notes.

Does not belong here: Model weights/caches, credentials, private RAG corpora and strategy-specific trading prompts/logic.

## Source of Truth

The Git state and assigned issue/PR are authoritative engineering state. Read README.md, this file, docs/MULTI_LLM_WORKFLOW.md and the assigned issue. ZIP/folder names such as FINAL, FIXED or NEW are not versions. Current user instructions and security constraints take precedence over repository prose.

## Repository-specific controls

Operational runtime configuration belongs here; accepted machine state belongs in engineering-workstation-commissioning, and experimental hardware comparisons in pc-performance-lab. Capture model/quantization, runtime, context/KV cache, offload, threads and measured latency/throughput.

## Required Workflow

1. Fetch/pull safely before beginning; inspect branch, HEAD, remotes and working-tree status. Do not overwrite uncommitted work.
2. Read the entrypoints and issue acceptance criteria; state your implementer/reviewer/QA/research/integration role.
3. Inspect open issues/PRs and overlapping file changes; coordinate conflicts on the issue.
4. Create a dedicated branch from an agreed current base. One branch has one editing owner.
5. Make narrowly scoped changes, run relevant tests and document failures/skips.
6. Commit with an informative message, open/update a PR and record test evidence and risks.
7. Hand off using repository, branch, full SHA, issue, PR and next action; verify the actual state on receipt.

## Branching and Multi-Agent Rule

Authoritative/default branch: `main`. Do not commit substantive work directly to it. Use `agent/<agent-name>/<issue-number>-<short-description>`; bootstrap governance uses `repo-bootstrap/multi-llm-governance`. Never let multiple agents concurrently edit one branch or silently overwrite another's unmerged work. GitHub Issues/PRs coordinate ownership. Merge, release and deployment are separate authorized actions.

## Testing

No application test harness exists on the current default branch. For new scripts, record syntax/unit/smoke checks, dependency versions and the host-specific acceptance command. Never fabricate tokens/sec or GPU acceptance.

For documentation/governance, check diff whitespace, parse YAML, validate metadata against actual visibility/default branch, and verify ignore rules for secrets, weights and explicitly allowed fixtures. A syntax or governance check is not application/hardware acceptance.

## Security

Never commit credentials, tokens, keys, customer records or private personal evidence. Sanitize fixtures/logs. Review history as well as the current tree before public exposure; .gitignore does not sanitize tracked history. See SECURITY.md. Investigate >25 MiB objects; keep bulk data/weights external and record manifests/checksums. Preserve the public exporter/private entry-engine boundary.

## Generated Files

Do not hand-edit generated releases, build outputs, caches or benchmark reports to manufacture a pass. Change the generator/source and regenerate under controlled versions. Label captured evidence with its source commit and environment; do not overwrite historical acceptance evidence during governance.

## Handoff

A PR description records objective, scope/files, exact tests and results, known limitations, agent/role, independent-review findings and next action. Follow docs/MULTI_LLM_WORKFLOW.md. License: not yet selected by this bootstrap; preserve any existing license/UNLICENSED declaration.

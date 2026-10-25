# DR100 — SOL Included-Allowance + Nous Metered Failover (Pilot Runbook)
**Prepared:** 2026-10-25. **Status:** PROPOSAL / NOT APPLIED TO 5090FE. **Owner contract:** [DR100 engineering-control Issue #29](https://github.com/Helminiak/dr100-engineering-control/issues/29). **Scope:** existing Hermes/Codex SOL supervisor profile only; `qwen-worker` and the production resident model are unchanged.

## Objective and non-negotiable boundaries
Keep GPT-6.1 SOL on the owner's existing ChatGPT/Codex OAuth included allowance as the **first-choice exception supervisor**. On a recognized quota/rate-limit error, continue the same bounded supervisor turn through a verified, prepaid **Nous Portal** model without starting another dispatcher, another RTX 5090 model, or a replacement Kanban queue. Hermes Kanban continues to own priority/dependencies; Qwen implements; a separate Sonnet-tier reviewer profile reviews when required. Cloud reviewing and one local worker can overlap after capacity/claim tests. Do not burn paid tokens on heartbeat/status/scheduling.

**DO NOT merge current DR100 policy PR #28 or modify live Kanban/model/server configuration solely because this runbook exists.** Reviewer profile qualification comes first. No changes to Bookmap/JAR/trading/Windows permissions. Existing owner-approved same-model restart and bounded offline Bookmap recovery remain separate tasks; this fallback does not implement them.

## Verified upstream capability (not evidence it is installed)
- [Hermes fallback providers](https://hermes-agent.nousresearch.com/docs/user-guide/features/fallback-providers): `hermes fallback` and top-level `fallback_providers`; `provider: nous` supported. Triggers include quota HTTP 429 after retries, provider/auth failures and invalid responses. A provider-reported reset time benches the primary until that reset. Fallback is turn-scoped, with reset-aware suppression of doomed primary retries. A mid-session switch invalidates prompt cache, so favor a fresh SOL context with a compact issue/SHA handoff at task boundaries.
- [Hermes profiles](https://hermes-agent.nousresearch.com/docs/user-guide/profiles): independent profile home and model config. A fallback for SOL must be written **in the actual SOL profile**, not Qwen's or the global default accidentally. Identify that profile empirically.
- [Hermes Kanban](https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban): one worker per profile (`max_in_progress_per_profile: 1`), overall cap allowing remote reviewers, native same-card review, priority order. Do not configure speculative values without inspecting the installed schema.
- [OpenAI usage guidance](https://help.openai.com/en/articles/20001516-managing-usage-with-gpt-6-astra-in-work-and-codex): Plus may have both five-hour and weekly included limits; Pro $100 currently removes the five-hour Work/Codex limit but not all limits.
- [OpenAI Pro tiers](https://help.openai.com/en/articles/9793128-about-chatgpt-pro-tiers): $100/month Pro 100, $200 Pro 200. Upgrade is **not** authorized by this file.

## Phase A — read-only baseline; preserve active sessions
At a local terminal, run:
```bash
hermes --version
hermes profile list
hermes portal info
hermes gateway status
hermes kanban boards list
hermes kanban diagnostics --json
hermes kanban assignees --json
pgrep -af llama-server || true
```
Identify exact existing SOL profile name; do not assume it is `default` or `hermes-supervisor`. Inspect `hermes -p <SOL_PROFILE> fallback list` and existing credential/provider mapping without printing secrets. Observe remaining ChatGPT Work/Codex allowance and reset times in ChatGPT Settings > Usage or Codex `/status`. Record aggregate counts only. Do not duplicate or refresh a healthy running SOL session.

## Phase B — reviewer first (no active policy/dispatcher changes)
List the existing `senior-reviewer` or equivalent profile and its model/Nous auth. Verify a **currently selectable** Nous Sonnet model, real posted per-token prices, credit balance and reviewer tool capability. Execute ONE tiny reviewer test on an offline, immutable SHA-pinned historic PR. Record actual provider/model, usage, cost, review result and receipt. Do not assume published vendor API prices are Nous prices. No Opus automatic use or payment auto-refill; no full repo or conversation uploads.

## Phase C — targeted SOL fallback pilot at safe context boundary
Use the same active SOL profile only; preserve existing Codex primary `model` and credentials. Prefer the interactive fallback manager:
```bash
hermes -p <SOL_PROFILE> fallback list
hermes -p <SOL_PROFILE> fallback
hermes -p <SOL_PROFILE> fallback list
```
Select `Nous Portal` and a verified economical model in the profile-scoped interactive picker. If the installed build supports the documented YAML schema, the intended **addition under the SOL profile's config only** is:
```yaml
# ~/.hermes/profiles/<SOL_PROFILE>/config.yaml  (example path only)
fallback_providers:
  - provider: nous
    model: <exact-verified-nous-model-id>
fallback:
  min_switch_reset_seconds: 120
```
Do not copy this placeholder verbatim; the exact model slug and actual profile directory must be proven. Do not overwrite existing `model:`, Kanban, credentials, token settings, dispatcher, Qwen or model-server configuration. Copy and secure the old config; use official Hermes commands when possible; reread effective config. If Hermes already has fallback entries, inspect and preserve required existing order.

**Evidence:** one normally successful SOL request stays on the Codex primary, one deliberately selected inexpensive Nous model works in an isolated reviewer test, and the SOL fallback is listed. Do not deliberately exhaust a live subscription or fabricate a primary 429. Classify **AUTO-FAILOVER PARTIAL** until a naturally occurring recognized limit demonstrably switches SOL to Nous and later returns to Codex after actual reset. Confirm same Kanban task and no duplicate work; record provider, model, input/output usage, retry cause, reset observation and real billing. Never publish credential material or complete private conversations.

## Phase D — spending and recovery guards
- **Subscription baseline:** Plus $20/month versus Pro 100 $100/month = **$80/month incremental**; Pro 100 has no five-hour Work/Codex restriction but included allowances still apply. Prefer Plus + real metered overflow until utilization justifies the higher fixed tier.
- **Nous credit:** $22 reported owner balance is a snapshot, not a new monthly allowance. Verify fresh balance before a paid test. Default Sonnet reviewer; Opus disabled until separately justified/authorized. Suggested targets: $0.25 normal review, $0.75 alert/escalation, $1.00 max per-task only if metering actually enforces it. If real hard ceilings cannot be enforced, do not claim unattended spend-safe; cap number of paid task dispatches and manually reconcile balance.
- **Fallback:** provider-reported reset times are preferred to guesses. A weekly-limit failure should not loop repeatedly on Codex while primary allowance remains exhausted. Some errors may not trigger automatic fallback; save the actual failure and stop, rather than invent a workaround.
- **Context:** switching providers invalidates prompt caching and may require a full-context paid reread. Start fresh cloud supervisor task contexts with a compact evidence packet; avoid repeatedly switching a 100K+ token session.
- **Current model crash:** separate systemd-supervised llama-server recovery with rate limits, exact approved launcher/weights, no duplicate processes, readiness checks, preserved crash logs, and owner notifications. Native dispatcher recovery should not restart the model itself blindly.
- **Windows Bookmap:** only established offline Replay/SIM environment and approved helper, no live trading connection, session-0 blind input, autonomous credential/permission expansion, or source/JAR rewrite.

## Break-even measurement — review after 7–14 operating days
Capture for each 24h window: (i) SOL included-quota errors (5-hour/weekly), (ii) actual Nous overflow spend excluding separately useful independent reviews, (iii) review spend, (iv) useful tasks accepted, (v) time blocked for quota, and (vi) failed automatic failovers. Separate incremental overflow spend from Sonnet reviews that would be purchased under either subscription.

Upgrade to Pro 100 **only if** measured excess paid overflow costs plus value of avoidable blockage consistently justify $80/month, or the operational requirement demands continuous GPT-6.1 SOL access rather than economical substitutability. Neither the subscription change nor external purchase is delegated.

## Final acceptance receipt for Issue #29
`VERSION | SOL PROFILE | PRIMARY/CODEX AUTH (masked) | FALLBACK/NOUS AUTH (masked) | REVIEWER PROFILE/MODEL | KNOWN COSTS | LIVE RUNTIME UNCHANGED | PILOT REVIEW RESULT | NEXT CHECKPOINT | GITHUB COMMIT/SHA`.
Record `NOT QUALIFIED` if an actual outage/quota failover has not yet been observed. Avoid new daemon/framework/policy expansion.

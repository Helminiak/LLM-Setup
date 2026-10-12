# DR100 local worker recovery — October 12, 2026

## Ground truth

Authoritative private evidence:
- [First load attempt: API authentication failed](https://github.com/Helminiak/knowledge-base/blob/main/reports/lmstudio/20261012T191353832511Z.json)
- [Second attempt: launcher stopped at parallel-capacity check](https://github.com/Helminiak/knowledge-base/blob/main/reports/lmstudio/20261012T192930587374Z.json)

Both observed runs successfully loaded Qwen3.8 Coder390 Q6_K at **80,000 configured context**, with `lms load --gpu max`. The second reported RTX 5090 total 32,607 MiB, used 30,362 MiB, free 1,750 MiB; ~54.5 GiB system RAM available. The advertised maximum **262,144** is distinct from the loaded context **80,000**.

The second run stopped because the launcher rejected `parallel=4`. This is LM Studio's default *capacity* for concurrent requests, not evidence that four requests were active. When testing serially, the setting is a nonblocking warning. Source: https://lmstudio.ai/docs/app/advanced/parallel-requests.

The first run returned HTTP 401 from the LM Studio local API; GitHub upload was successful. New launcher keeps API authentication enabled, prompts securely for a local token if needed, and stores it locally under restrictive permissions, never in GitHub.

## Versioned changes

- 1.0.3: [previous script](../scripts/dr100-hermes-start-v1.0.3.sh) — rejected configured parallel capacity 4 before testing.
- 1.0.4: [recovery script](../scripts/dr100-hermes-start-v1.0.4.sh) — continue with serial authenticated tests; emit explicit parallel-capacity warning; 512-token allowance for reasoning-model smoke output.
- Model profile remains: [RTX5090 profile](../profiles/rtx5090-dr100-qwen.json). **No DR100 issue, Hermes routing, WP002 review HOLD, or release gate was modified.**

## Execute on Ubuntu

```bash
curl -fLsS https://raw.githubusercontent.com/Helminiak/LLM-Setup/main/scripts/dr100-hermes-start-v1.0.4.sh -o ~/Downloads/dr100-hermes-start-v1.0.4.sh && bash ~/Downloads/dr100-hermes-start-v1.0.4.sh --setup-only
```

The setup-only run performs model/API checks and a bounded reasoning test but **does not** start Hermes. After the report shows PASS, run without `--setup-only` to launch the existing Hermes configuration. LM Studio may prompt for a new local API token (Developer > Server Settings > Manage Tokens). Do not paste tokens or terminal output back as shell commands.

Reports save locally under `~/.local/state/dr100-lmstudio/reports/` and are uploaded to private `Helminiak/knowledge-base:reports/lmstudio/` when local `gh` authentication allows it. New successful runs are deduplicated in the fingerprinted local benchmark ledger; no repeated full benchmark for identical configuration. A transport PASS does not prove coding quality or Hermes delegation stability.

## Remaining acceptance tests

- Authenticated LM Studio /v1/models responds and short inference returns usable content.
- No GPU OOM while testing.
- Hermes independently resolves the loaded **80,000-token context** and handles compaction.
- Hermes local worker invokes actual tools, completes a bounded task, and accurately updates Kanban/GitHub evidence.
- WP002 remains CHANGES_REQUESTED/HOLD until independent review.

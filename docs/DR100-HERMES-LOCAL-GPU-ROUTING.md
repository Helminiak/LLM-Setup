> **DR100 LEGACY REFERENCE (2026-10-24):** Superseded for active DR100 routing by [DR100 single-worker v2.0](https://github.com/Helminiak/dr100-engineering-control/blob/main/policies/DR100_SINGLE_WORKER_V2.md). The Coder390 Q6_K LM Studio :1234 and 80K settings below are retained for reproducibility/rollback, not the current default. One GSQ-RCO Coder + MTP model on both 5090s at llama.cpp :1235, one `qwen-worker` session at a time. Do not invoke historical load, route-apply or queue-import steps to restore current service.

# DR100: Make the RTX 5090 do actual Hermes work

**Revision:** 2026-10-12. **Scope:** config/audit only, no DR100 source changes and no automatic cloud worker fallback.

## Evidence-based starting point

- Local Qwen Coder390 Q6_K at contextLength=80,000, Flash Attention and GPU KV offload enabled. Latest [LM Studio local PASS report](https://github.com/Helminiak/knowledge-base/blob/main/reports/lmstudio/20261012T193411462196Z.json): 30,450 MiB GPU RAM used, 1,662 MiB free after tests, one WP002-style short inference 412 tokens in 4.26 seconds (~96.7 output tokens/s end-to-end, not continuous long-run throughput).
- Screenshot of interactive Hermes dated 2026-10-12 shows status **gpt-6.1-sol** and **ctx --**. This confirms the main interactive conversation is labeled with a cloud model; it does **not** demonstrate local delegation. A model loaded in LM Studio can occupy VRAM while receiving no worker calls.
- Configuration is not independently inspected on the workstation yet. First obtain a sanitized, current **routing audit**, then authorize changes.

## Intended topology

```text
GPT-6.1 SOL / existing Hermes parent conversation (planning/review/decisions)
      |
      | delegate_task, bounded and auditable
      v
Hermes leaf worker: provider=lmstudio
      | model=Qwen3.8-27B Coder390 Q6_K (installed)
      | LM_API_KEY from secure, local token file
      v
LM Studio localhost:1234/v1 -> RTX 5090
      |
      +--> returns result to cloud supervisor
```

The local child must get tool access and be able to act on bounded tasks; assigning a local model does not automatically create tasks. Cloud parent continues as configured. If the child fails, surface failure **instead of** silently doing its work on the cloud. WP002 HOLD/CHANGES_REQUESTED and all repository gates remain unchanged.

## Stage A: Audit, no changes

From an **Ubuntu shell, not Hermes chat**, run:

```bash
curl -fLsS https://raw.githubusercontent.com/Helminiak/LLM-Setup/main/scripts/dr100-hermes-gpu-route.sh -o ~/Downloads/dr100-hermes-gpu-route.sh && bash ~/Downloads/dr100-hermes-gpu-route.sh --audit
```

Read-only findings and hardware snapshot are saved under `~/.local/state/dr100-lmstudio/routing-reports/`. The helper uploads sanitized routing facts to private `Helminiak/knowledge-base:reports/lmstudio/routing/` if `gh` works; it does **not** upload credentials, full config files, prompts, or conversation history.

Inspect this report to check the **actual** parent provider/model, delegation provider/model, conflicting `delegation.base_url`, compression model, parallel worker cap, and local API credential availability.

## Stage B: Explicit apply (ONLY after reviewing Stage A)

Exit Hermes gracefully first; from a Bash terminal:

```bash
bash ~/Downloads/dr100-hermes-gpu-route.sh --apply
```

This makes a mode-0600 rollback copy of `~/.hermes/config.yaml`, keeps `model.provider/default/base_url` unchanged, removes any old `delegation.base_url` direct-endpoint override and old `delegation.api_key`, and sets:

```yaml
delegation:
  provider: lmstudio
  model: qwen3.8-27b-coder390-efficientthink-opus5.5-gpt6astra-grok4.7-dsv4pro-k3-sft-rloo-ninfer@q6_k
  max_concurrent_children: 1
  max_spawn_depth: 1
  fallback_providers: []
```

If the CLI rejects any field, the helper tries to restore the backup, prints a failure, and uploads a sanitized failure report. **It does not modify the main model or the DR100 GitHub repository.**

Setting `max_concurrent_children: 1` limits actual simultaneous child work, regardless of LM Studio's four available parallel request *slots*.

## Stage C: Start with secret-safe LM Studio token environment

```bash
curl -fLsS https://raw.githubusercontent.com/Helminiak/LLM-Setup/main/scripts/dr100-hermes-cloud-supervisor-local-worker.sh -o ~/Downloads/dr100-hermes-cloud-supervisor-local-worker.sh && bash ~/Downloads/dr100-hermes-cloud-supervisor-local-worker.sh
```

This refuses to start if the local child route is not configured. It reads `~/.config/dr100-lmstudio/api-token` (requires 0600 or 0400) into the **Hermes process environment as `LM_API_KEY`**, without printing or committing the secret, and runs the already validated [v1.0.5 LM Studio startup script](../scripts/dr100-hermes-start-v1.0.5.sh). The main GPT cloud provider is unchanged. Local bearer token remains strictly local. Existing `~/.hermes/.env` also remains supported if already configured.

## Stage D: Prove actual GPU execution

In Hermes, explicitly request a *single* `delegate_task` with a read-only task:
> Delegate to one local leaf worker. Read the current repository's README and report its first heading plus the Git branch. Do not edit any file, do not create a commit, and report any model/tool failure instead of substituting the supervisor.

Simultaneously, in a second Ubuntu terminal sample:

```bash
nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used,memory.free,power.draw --format=csv -l 1
```

The local child must make an observable inference request; compare LM Studio's Developer server request log with the child run. The GPU snapshot alone cannot prove that Hermes made the request (other GPU processes also create utilization). Verify tool call correctness, completion result, and whether the cloud parent received it. **Do not permit automatic edits or GitHub approvals in this first test.**

If this succeeds, progress to a bounded engineering package with acceptance tests and GitHub evidence. Increase local child concurrency to 2 only after measuring VRAM headroom, latencies, errors, and completion quality. More memory allocation or more configured parallel slots is not necessarily higher useful throughput.

## What NOT to optimize prematurely

- Do not switch the Hermes supervisor to a local model when the desired architecture is frontier cloud planning + local children.
- Do not CPU-offload a 23.8 GB Q6 model merely because 55 GiB host RAM is available: DDR5 is much slower than RTX 5090 GDDR7 for inference; CPU offload is a capacity option.
- Do not set 262,144-token active context just because it is a model maximum. The current 80,000 allocation already consumes substantial GPU RAM and needs long-context validation before enlargement.
- Do not point Hermes's separate compression summarizer at an 80K local model unless it can accommodate the full main model context; Hermes warns that under-sized summarizers can lose conversation history.

References: [Hermes subagent delegation](https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation), [Hermes configuration](https://hermes-agent.nousresearch.com/docs/user-guide/configuration), [Hermes LM Studio provider](https://hermes-agent.nousresearch.com/docs/integrations/providers), [LM Studio Hermes integration](https://lmstudio.ai/docs/integrations/hermes).

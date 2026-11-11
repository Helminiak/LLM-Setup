# Hermes Worker and Model Inventory

Audit timestamp: 2026-11-07T14:35:24-05:00 (UTC evidence files in `evidence/`). Read-only collection only; no configuration, service, model, permission, repository, or Kanban state was changed. KANBAN remained suspended (`dispatch_in_gateway=false`, `review_dispatch=false`).

## Executive status

- Hermes gateway: active at capture.
- Hindsight: active and healthy on loopback `127.0.0.1:8888`; PostgreSQL backend is recorded in the previous architecture audit.
- CodeBreaker/Gyro-L: active on both RTX 5090s, PID 2651059, port 8081, one 128K slot.
- GYRO-Coder-L: inactive at capture; profiles still point to 8082/8083, which were unavailable.
- DR100 Production: inactive at capture; port 1235 unavailable.
- No Kanban worker was running; Kanban dispatch was disabled.
- This audit verifies configuration and selected runtime facts. It does not prove every configured tool permission is effective.

## Worker matrix

| Worker/profile | Role | Model/provider | Context configured | Effective context | Output/concurrency | Permissions/status |
|---|---|---|---:|---:|---|---|
| `hermes-supervisor` | SOL supervisor/orchestrator | `gpt-6.1-sol` / openai-codex | Provider limit unavailable in local config; local compression threshold 0.75 | Cloud effective limit unavailable; no local inference route selected | `agent.max_turns` 150 in main config; Kanban max 1 in profile; child max 1 | Local terminal profile, smart approvals, delegation/toolsets configured, Hindsight MCP; **active supervisor session; Kanban dispatch disabled** |
| `qwen-worker` | Local implementation worker | `gyro-coder-l-gpu0` / custom `127.0.0.1:8082/v1` | 65,536 in worker contract/config family | **Unavailable**: 8082 was not listening at capture | Output limit not explicitly found; concurrency intended 1 | Smart approvals; local terminal/file/toolsets; Hindsight MCP; Kanban profile dispatch empty/disabled; configured but endpoint unavailable |
| `qwen-worker-2` | Historical/retired local worker | `gyro-coder-l-gpu0` / custom 8082 | 65,536 family | **Unavailable**: 8082 unavailable | Output/concurrency not explicit; profile is not in dispatch allowlist | Smart approvals; local tools and delegation known; Kanban disabled; **historical/retired, do not dispatch** |
| `qwen-windows-worker` | Windows/GUI worker | `gyro-coder-l-gpu1` / custom 8083 | 65,536 family | **Unavailable**: 8083 unavailable | Output/concurrency not explicit | Smart approvals; CUA foreground/background toolsets; local terminal; Kanban disabled; **configured but Windows admission not verified** |
| `codex-worker` | Cloud execution worker | `gpt-6.1-sol` / openai-codex app-server | Provider effective context unavailable | Unavailable without a paid/authenticated request | Tool/profile limits not exposed; Kanban dispatch empty | Approval/tool settings configured; cloud endpoint; delegation toolset present; inactive/not running in process inventory |
| `reviewer-economy` | Economy review | `gpt-6.1-sol` / openai-codex | Unavailable | Unavailable | Unavailable | Local terminal cwd `/home/joe/.hermes/dr100-learning`; approval details partially configured; inactive; review dispatch disabled |
| `senior-reviewer` | Senior technical review | `claude-sonnet-5-5[1m]` / Claude direct SDK | Nominal model name indicates 1M, serving limit unverified | Unavailable; no live request made | Unavailable | Local terminal cwd `/home/joe/.hermes/dr100-learning`; inactive; no effective review dispatch |
| `gyro-coder-supervisor` | Local GYRO coding supervisor | `gyro-coder-l-gpu0` / openai-compatible 8082 | 65,536 | Unavailable: 8082 inactive | Compression threshold 0.75; output not explicit | Local terminal, smart approvals, delegation and Hindsight MCP; inactive/unavailable endpoint |
| `gyro-coder-gpu1` | Local GPU1 coding profile | `gyro-coder-l-gpu1` / openai-compatible 8083 | 65,536 | Unavailable: 8083 inactive | Unavailable | Approval mode appears `off` in config; this is a **configuration risk**; inactive |
| `gyro-worker-1` | Historical GYRO worker | `gyro-coder-l-gpu0` / 8082 | 65,536 | Unavailable | Unavailable | Hindsight MCP; inactive |
| `gyro-worker-2` | Historical GYRO worker | `gyro-coder-l-gpu0` / 8082 | 65,536 | Unavailable | Unavailable | Hindsight MCP; inactive |
| `gyro-local-worker` | Historical local GYRO worker | `gyro-coder-l-gpu0` / 8082 | 65,536 | Unavailable | Unavailable | Inactive |
| `cache-sol-audit` | Cache/audit profile | Not established from selected config evidence | Unavailable | Unavailable | Unavailable | Historical/cache directory; no active process evidence |

## Model matrix

| Model | Quantization/shards | Loader/build | Context total/slot | Slots | GPU allocation/VRAM | Endpoint/workers | Status |
|---|---|---|---:|---:|---|---|---|
| Qwen3.8-Flash-Next Gyro-L abliterated TQ3_0 (CodeBreaker) | TQ3_0; one GGUF, 74,860,724,096 bytes; SHA benchmark `26d61444239c...` | `/home/joe/src/llama-gyro/build/bin/llama-server`, b11377 commit `9aa51ce4f` | 128,000 / 128,000 | 1 | Layer split; tensor `0.975,1.025`; PID 2651059; ~29.1/28.4 GiB used | `127.0.0.1:8081`; CodeBreaker launcher; no Hermes worker profile currently points here | **CURRENT / ACTIVE**; health 200; 124,842-token retrieval passed |
| Qwen3.8-Flash-Next Gyro-Coder-L TQ3_0 noPLE | TQ3_0 plus PLE sidecar IQ4_NL; one main GGUF plus sidecar | `/home/joe/src/llama-gyro-coder/build/bin/llama-server`, runtime b11378-060e10051 | 65,536 / 65,536 | 1 per server | Two separate services intended for GPU0/GPU1; `split-mode none`, `main-gpu 0`; live services inactive at capture | 8082/8083; qwen-worker, gyro profiles | **CONFIGURED / INACTIVE**; endpoint unavailable at audit capture |
| Qwen3.8-Flash-Next GSQ-RCO Coder MTP | Q4_K_M; two shards, shard 1 ~29.61 GB, shard 2 ~29.79 GB; projector BF16 | `/home/joe/Documents/Codex/.../llama-b11850/llama-server`, b11850 | 262,144 / 262,144 | 1 | CUDA0/CUDA1, layer split, tensor 1,1; service inactive | 1235; DR100 launcher/qwen historical route | **CONFIGURED / INACTIVE**; no endpoint |
| Qwen3.8 Cyber RedTeam Surgical | Q6_K; one GGUF plus mmproj | LM Studio model directory; active loader not observed | Historical 8K/other LM Studio settings; current effective unavailable | Unavailable | Not loaded | No active endpoint observed | **HISTORICAL / INACTIVE**; do not treat as CodeBreaker |
| Qwen3.8-Flash-Next GSQ-RCO IQ3_XXS | Two shards | No active loader | Unavailable | Unavailable | Installed bakeoff only | None observed | **INSTALLED / EXPERIMENTAL** |
| Qwen3.8-Flash-Next GSQ-RCO Q2_0 | Two shards plus MTP sidecars nearby | No active loader | Unavailable | Unavailable | Installed bakeoff only | None observed | **INSTALLED / EXPERIMENTAL** |
| Qwen3.8-Flash-Next UD-Q2_K_XL | Three shards | No active loader | Unavailable | Unavailable | Installed bakeoff only | None observed | **INSTALLED / EXPERIMENTAL** |
| Qwen3.8-27B UD-Q6_K | One GGUF | No active loader | Unavailable | Unavailable | Installed bakeoff only | None observed | **INSTALLED / EXPERIMENTAL** |
| Qwen3.6-35B-A3B variants | Q8_0, UD-Q4_K_XL, UD-Q5_K_M, UD-Q6_K; one file each | No active loader | Unavailable | Unavailable | Installed bakeoff only | None observed | **INSTALLED / EXPERIMENTAL** |
| `flint-Q4_K_M.gguf` | Q4_K_M; one GGUF | No active loader | Unavailable | Unavailable | LM Studio directory only | None observed | **INSTALLED / UNVERIFIED** |
| Strata MTP assets | `mtp-q2_0.gguf` plus binary expert/runtime assets | Strata installation; no active model server | Unavailable | Unavailable | No active GPU process | No endpoint observed | **INSTALLED / UNVERIFIED** |

Model file paths, sizes and timestamps are in `evidence/model-files.txt`. Large model SHA-256 values were not recomputed during this read-only audit to avoid a long full-disk/hash operation; benchmark-published hashes are labeled as benchmark evidence, not fresh hashes.

## Current service state

- `gyro-l.service`: active at capture; PID 2651059; port 8081; one 128K slot.
- `gyro-coder-l-gpu0.service`: inactive at capture; configured launcher points to GPU0 service script.
- `gyro-coder-l-gpu1.service`: inactive at capture; configured launcher points to GPU1 service script.
- `dr100-model.service`: inactive and recovery-only; port 1235 refused.
- `hindsight.service`: active on loopback 8888; health database connected.
- `hermes-gateway.service`: active; `Restart=always`, but Kanban dispatcher gate is false.

## Context consistency findings

1. CodeBreaker is correctly one 128K slot. It is not split into two 64K slots.
2. GYRO-Coder-L profiles specify 65,536, matching their configured service family, but the services were inactive at capture; effective inference was unavailable.
3. DR100 is configured for 262,144 and one slot, but no runtime endpoint was available.
4. Hermes supervisor local provider entries reference 65,536 GYRO-Coder-L endpoints while its primary model is cloud `gpt-6.1-sol`; this is a deliberate mixed profile but can confuse routing.
5. `qwen-worker` and `qwen-worker-2` both point to 8082, not independent GPU endpoints. This conflicts with any intended two-GPU/two-worker interpretation and requires approval before correction.
6. `qwen-windows-worker` points to 8083 but is not in the dispatch allowlist and has no effective endpoint at capture.
7. `gyro-coder-gpu1` has `approvals.mode: off` in its profile evidence. This is inconsistent with the intended smart-approval policy and should be reviewed, but was not changed.
8. Several historical GYRO profiles remain installed with no active process or clear current role.
9. Hindsight MCP routes are loopback-only and configured in multiple profiles; live access was not tested per worker to avoid side effects.
10. No unintended active cloud fallback was proven. Cloud profiles exist, but no paid request was issued.

## Permission interpretation

Configured local terminal access is not proof of effective filesystem or remote access. The OS user is in `sudo` and `lxd` groups, but no sudo/root command was run. SSH configuration exists from the architecture audit, but no remote login or write test was performed. GitHub CLI/auth presence is not proof of repository write permission; no write operation was attempted. MCP configuration references Hindsight, but per-worker tool authorization was not invoked. No worker permission was changed.

## Recommended corrections requiring approval

- Decide whether `qwen-worker-2` is retired (as the current policy indicates) or should point to a distinct approved endpoint; do not silently change it.
- Review and likely disable/remove stale GYRO profiles after confirming no historical recovery dependency.
- Review `gyro-coder-gpu1` approval mode `off`.
- Reconcile the mixed Hermes supervisor cloud primary/local provider entries and document intended routing.
- Keep CodeBreaker, Coder and DR100 mutually exclusive where they require both RTX 5090s; no concurrent assumption is supported by current VRAM/service evidence.

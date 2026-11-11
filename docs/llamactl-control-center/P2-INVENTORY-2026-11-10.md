# Llamactl P2 — read-only local model inventory and cache reconciliation

**Date:** 2026-11-10 · **Host:** 5090FE · **Phase issue:** #13 · **Mode:** read-only, no downloads, no relocations

## 1. Roots confirmed from live state (no whole-OS scan)

| root id | path scanned | realpath target | evidence |
|---|---|---|---|
| `home_models` | `/home/joe/models` | `/mnt/llm/models` | directory is a symlink; `/mnt/llm` is a separate mount |
| `mnt_llm` | `/mnt/llm` | `/mnt/llm` | mount table; claimed 0 artifacts (all bytes claimed through `home_models`) |
| `lmstudio_models` | `/home/joe/.lmstudio/models` | itself | LM Studio model directory (ISTA-DASLab, lmstudio-community, mradermacher) |
| `hf_hub_cache` | `/home/joe/.cache/huggingface/hub` | `/mnt/llm/.cache/huggingface/hub` | HF hub layout (`refs/`, `snapshots/`, `blobs/` symlink layout) |

`/mnt/llm` **does** contain the model weights (the P0 note "no GGUF under /mnt/llm" was wrong — `~/models` is a symlink to `/mnt/llm/models`). Service args were used to classify state, not as scan roots: `local-qwen.service` (`:8082`) and `hindsight-extract-llm.service` (`:8091`).

## 2. Method (bounded, read-only)

`scripts/llamactl-control-center/inventory.py` — stdlib only, `--max-depth` per root, GGUF **header only** (never the tensor blob), arrays summarized, identity = `head_sha256_1MiB`. Each physical file (`realpath`) is claimed exactly once by rank (split shard > GGUF > HF snapshot > HF blob > other root), which collapses symlink aliases, model→blob links and symlinked roots. `--output` refuses to write inside a scanned root. Schema: [p2-inventory-schema.md](p2-inventory-schema.md).

## 3. Exact counts (manifest `e2e2262fc20f…`, three identical stable scans)

```
artifacts 21   gguf_artifacts 19   gguf_files 23
gguf_split_sets 3 (incomplete 0)   hf_snapshot_dirs 2   safetensors_dirs 0
runnable_llms 14   sidecar_or_projector_only 4
duplicate_pairs 0   symlink_aliases_collapsed 16   cross_root_aliases_collapsed 4
warnings 0   total_bytes 612092837436 (570.1 GiB)
states {"incomplete": 5, "running": 2, "unconfigured": 12, "unsupported": 2}
per-root GiB {'home_models': 524.8, 'lmstudio_models': 44.8, 'hf_hub_cache': 0.52}
```

## 4. Inventory (21 logical artifacts)

| root | location (relative) | name | kind | quant | GiB | state | backend | dependency |
|---|---|---|---|---|---|---|---|---|
| hf_hub_cache | models--cross-encoder--ms-marco-MiniLM-L-6-v2/snapshots/233902d25c440f23af6f7d6e94d2946bac0bee0a | cross-encoder/ms-marco-MiniLM-L-6-v2 | hf_snapshot | - | 0.08 | unsupported | onnx | - |
| hf_hub_cache | models--intfloat--multilingual-e5-small/snapshots/614241f622f53c4eeff9890bdc4f31cfecc418b3 | intfloat/multilingual-e5-small | hf_snapshot | - | 0.44 | unsupported | onnx | - |
| home_models | Qwen3-4B-Q4_K_M.gguf | Qwen3 4B Instruct Awq | gguf | Q4_K_M | 2.33 | running | llama_cpp | - |
| home_models | bakeoff/flash-iq3/Qwen3.8-Flash-Next-GSQ-RCO-IQ3_XXS.gguf | Qwen3.8-Flash-Next GSQ-RCO | gguf_split_set | IQ3_XXS | 70.63 | running | llama_cpp | - |
| home_models | bakeoff/flash-sidecar/mtp-ggml-Q8_0.gguf | Qwen3.8-Flash-Next | gguf | Q8_0 | 3.85 | incomplete | none | module export: 34 tensors against declared block_count 49; load with the base model |
| home_models | bakeoff/flash-sidecar/mtp-shared-Q8_0.gguf | Ckpt_Q38 | gguf | Q8_0 | 2.60 | incomplete | none | module export: 32 tensors against declared block_count 49; load with the base model |
| home_models | bakeoff/flash-unsloth/Qwen3.8-Flash-Next-UD-Q2_K_XL.gguf | Qwen3.8 Flash Next | gguf_split_set | Q2_K | 73.45 | unconfigured | llama_cpp | - |
| home_models | bakeoff/flash/Qwen3.8-Flash-Next-GSQ-RCO-Q2_0.gguf | Qwen3.8-Flash-Next GSQ-RCO | gguf_split_set | Q2_0 | 61.86 | unconfigured | llama_cpp | - |
| home_models | bakeoff/q27b/Qwen3.8-27B-UD-Q6_K.gguf | Qwen3.8-27B | gguf | Q6_K | 20.47 | unconfigured | llama_cpp | - |
| home_models | bakeoff/q35a3b-mtp/Qwen3.6-35B-A3B-Q8_0.gguf | Qwen3.6-35B-A3B | gguf | Q8_0 | 35.21 | unconfigured | llama_cpp | - |
| home_models | bakeoff/q35a3b-mtp/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf | Qwen3.6-35B-A3B | gguf | Q4_K | 21.28 | unconfigured | llama_cpp | - |
| home_models | bakeoff/q35a3b-mtp/Qwen3.6-35B-A3B-UD-Q5_K_M.gguf | Qwen3.6-35B-A3B | gguf | Q5_K_M | 25.23 | unconfigured | llama_cpp | - |
| home_models | bakeoff/q35a3b-mtp/Qwen3.6-35B-A3B-UD-Q6_K.gguf | Qwen3.6-35B-A3B | gguf | Q6_K | 27.95 | unconfigured | llama_cpp | - |
| home_models | bakeoff/q35a3b/Qwen3.6-35B-A3B-UD-Q5_K_M.gguf | Qwen3.6-35B-A3B | gguf | Q5_K_M | 24.64 | unconfigured | llama_cpp | - |
| home_models | gyro-coder-l/Qwen3.8-Flash-Next-Gyro-Coder-L-TQ3_0-noPLE.gguf | Qwen3.8-Flash-Next Gyro-Coder-L | gguf | TQ3_0 | 27.54 | unconfigured | llama_cpp | - |
| home_models | gyro-coder-l/Qwen3.8-Flash-Next-PLE-IQ4_NL.gguf | Qwen3.8 Flash Next | gguf | IQ4_NL | 26.82 | incomplete | llama_cpp | missing tokenizer/vocab absent from GGUF metadata |
| home_models | gyro-l/Qwen3.8-Flash-Next-Gyro-L-abliterated-TQ3_0.gguf | Qwen3.8-Flash-Next Gyro-L abliterated | gguf | TQ3_0 | 100.88 | unconfigured | llama_cpp | - |
| lmstudio_models | ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-Coder-GGUF/mmproj-Qwen3.8-Flash-Next-BF16.gguf | Qwen3.8-Flash-Next GSQ-RCO (mmproj) | gguf | BF16 | 0.85 | incomplete | none | - |
| lmstudio_models | lmstudio-community/flint-GGUF/flint-Q4_K_M.gguf | Recursive Flint | gguf | Q4_K_M | 22.51 | unconfigured | llama_cpp | - |
| lmstudio_models | mradermacher/Qwen3.8-cyber-RedTeam-Surgical-Abliterated-GGUF/Qwen3.8-cyber-RedTeam-Surgical-Abliterated.Q6_K.gguf | Qwen3.8 Cyber RedTeam Surgical Abliterated | gguf | Q6_K | 20.57 | unconfigured | llama_cpp | - |
| lmstudio_models | mradermacher/Qwen3.8-cyber-RedTeam-Surgical-Abliterated-GGUF/Qwen3.8-cyber-RedTeam-Surgical-Abliterated.mmproj-f16.gguf | Qwen3.8 Cyber RedTeam Surgical Abliterated | gguf | f16 | 0.86 | incomplete | none | - |

Dependency findings: 2 mmproj-only files (not runnable LLMs), 2 speculative/MTP module exports (34 and 32 tensors against `block_count` 49 — load with the base model, never standalone), 1 GGUF with no tokenizer/vocab, 2 HF ONNX-only embedding/reranker snapshots (no llama.cpp/vLLM/MLX path on this host), 3 GGUF split sets complete with contiguous shard indices.

## 5. Discrepancy report — Llamactl cache vs local inventory

| Fact | Evidence |
|---|---|
| Llamactl Models tab / `GET /api/v1/models` shows **2 rows** — `cross-encoder/ms-marco-MiniLM-L-6-v2`, `intfloat/multilingual-e5-small` | API count `2`; operator visually confirmed the same 2 rows after successful login (2026-11-10) |
| Both are Llamactl-managed HF **download-cache** entries, i.e. the same bytes as `hf_hub_cache` artifacts in this inventory | identical `models--…/snapshots/<rev>` locations, 0.52 GiB |
| The local inference library (19 GGUF artifacts, 14 runnable LLMs, 570 GiB) is **absent** from that cache | inventory vs API; `GET /api/v1/instances` = `[]` — Llamactl has never launched anything |
| The 2 currently running models are **external services**, not Llamactl instances | `local-qwen.service` → 75838385029 GiB IQ3_XXS split set (`:8082`, `/health` 200); `hindsight-extract-llm.service` → Qwen3-4B Q4 (`:8091`, `/health` 200) |

Conclusion: the Models tab is a **download cache view**, not a local library index. Fixing it is not a display bug to patch in P2; it is an integration decision (section 6).

## 6. Supported API/index integration (established before any UI change)

Enumerated from `~/.local/opt/llamactl/v0.23.0/llamactl` and the served dashboard bundle (`assets/index-BfM6bn_m.js`):

- Model routes present: `/api/v1/models` (GET), `/api/v1/models/download` (POST), `/api/v1/models/jobs/{id}`, `/api/v1/llama-cpp/{node}/models`, `/api/v1/llama-cpp/{node}/models/{model}/load|unload`. **No** `/models/scan`, `/models/index` or `/models/import` route exists in v0.23.0.
- The UI builds its base as `{document.baseURI}api/v1`; literal client paths are `/api/v1/instances`, `/api/v1/instances/{name}/proxy/`, `/api/v1/auth/oidc/login|logout`.
- llama.cpp **router/library mode** options exist in the instance schema and are surfaced in the UI: `models_dir`, `models_preset`, `models_max`, `models_autoload` / `no_models_autoload`, plus a `Model Presets (preset.ini)` editor; the binary contains `Adding --models-preset %s to command for instance %s`.
- Env knobs honored by the binary: `HUGGINGFACE_HUB_CACHE`, `LLAMACTL_INSTANCES_DIR`, `LLAMACTL_LLAMACPP_COMMAND|ARGS|ENV` (so the Models tab cache can be pointed at the existing HF cache without moving weights).

Therefore P2 ships the inventory as an **external read-only artifact**; no UI or config change was made. Making the GGUF library selectable is a P4/P5 design decision with two supported paths (per-instance `models_dir`/`preset.ini`, or pointing `HUGGINGFACE_HUB_CACHE` at the existing cache) — both change Control Center configuration, so they need an explicit owner decision.

## 7. Gate evidence

- `python3 scripts/llamactl-control-center/test_inventory.py` → `Ran 15 tests … OK` (fixtures: GGUF single, split set with missing shard, projector-only, module export, bare-key tokenizer HF GGUF, overlapping roots, HF snapshot with `onnx/` weights + tokenizer exclusion, blob alias).
- Determinism: 3 stable scans → identical sha256 `e2e2262fc20fab16fef4a47840153e7fef9db88f962e81a1690edef93979ff80`.
- No file modification: `find -printf '%p|%s|%m|%y'` snapshot before/after over all four roots (143 entries) → byte-identical diff.
- No duplicate misclassification: 0 duplicate pairs (quantization variants kept distinct); 16 aliases and 4 cross-root aliases collapsed.
- Missing-dependency detection exercised: 5 `incomplete` artifacts with explicit reasons.
- Machine-specific manifests stay outside the repo (`~/.hermes/profiles/hermes-supervisor/cache/scratch/llamactl-p2/`) and are ignored by `scripts/llamactl-control-center/.gitignore`.

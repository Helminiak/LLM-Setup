# DR100 RTX 5090: local-model candidates and measured-baseline policy (2026-10-12)

**Primary objective:** restore reliable Hermes delegation, tool calls, and GitHub evidence publication before changing model architecture. The RTX 5090 (32 GB VRAM) is dedicated to AI. RAM is 64 GiB DDR5, nominally specified as DDR5-6800; actual negotiated speed is not yet independently measured.

| Candidate | GGUF example | Why compare | Qualification needed |
|---|---:|---|---|
| **Existing** community Qwen3.8 27B Coder390 Q6_K MTP | 23.8 GB | Installed and already used for DR100 coding; default recovery baseline | Independently verify tool calls, compression, and source/test correctness |
| [Unsloth Qwen3.5-27B Q6_K](https://huggingface.co/unsloth/Qwen3.5-27B-GGUF/tree/main) | 22.5 GB | Official Qwen backbone with comparable precision and footprint | Benchmark same coding tasks and context |
| [Unsloth Qwen3.5-35B-A3B Q4_K_M](https://huggingface.co/unsloth/Qwen3.5-35B-A3B-GGUF/tree/main) | 22.0 GB | MoE architecture (~3B active) may improve inference throughput | Tool calling, quality, VRAM and memory-bandwidth tests |
| [Official Qwen3-Coder-30B-A3B-Instruct](https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct) | GGUF-dependent | Coding/agent specialization; prospective alternative | Confirm compatible quantized checkpoint and llama.cpp/LM Studio support |
| Existing Qwen3.8 Coder390 Q8_0 | 29.7 GB | Quantization control | Earlier 200K load consumed 31.3 GiB VRAM; limited headroom |

**RAM tradeoff:** Dual-channel DDR5-6800 theoretical bandwidth: 6.8 billion transfers/s × 8 bytes × 2 channels = **108.8 GB/s**; actual throughput and clock can be materially lower, especially with four DIMMs. RTX 5090 VRAM is about **1,792 GB/s**. Thus CPU-offloaded layers or CPU-resident KV cache increase *capacity*, not usually inference *speed*. Reserve some GPU VRAM for KV cache, graph and transient inference buffers. A 200K configured context is not the same as 200K populated tokens.

**Controlled recovery baseline:** local Q6_K; 80,000 context; --gpu max first; if full load fails or leaves less than 1024 MiB free, try 95%, 90%, 85%, 80% GPU offload while keeping context and checkpoint constant. Parallel predictions 1. Record actual GPU memory, DDR/system available, contextLength versus maxContextLength, LM Studio driver/version, requested GPU ratio, REST-visible advanced configuration, and bounded smoke/engineering-task API latency. Changes in model, offload, driver, profile SHA, or backend invalidate prior performance fingerprint. Repeated identical successful test suites are reused from the local ledger; a basic API reachability check is still necessary at every startup.

**Do not conflate load success with engineering correctness.** Dedicated Hermes delegation/tool-execution acceptance and DR100 gate review remain separate and must not be auto-approved or deployed.

**Automation design:** versioned declarative profile is [profiles/rtx5090-dr100-qwen.json](../profiles/rtx5090-dr100-qwen.json). The local `dr100-hermes-start.sh` reads it from GitHub on each start and caches the last valid copy for offline use. Results are saved under `~/.local/state/dr100-lmstudio/reports/`. When `gh` is authenticated, the sanitized JSON report is uploaded to private `Helminiak/knowledge-base:reports/lmstudio/`; no prompts, tool traces, tokens or credentials are uploaded. The script never edits Hermes configuration or DR100 gate/worker assignments.

**Unsupported advanced LM Studio configuration:** the documented CLI supports `--gpu`, `--context-length` and `--estimate-only`. It does not apply all GUI settings. Query `GET /api/v1/models` for actual flash attention, eval batch, GPU KV offload and parallelism, but **do not claim** physical batch, CPU threads, KV quantization, MTP or unified KV cache were applied programmatically.

Official documentation: https://lmstudio.ai/docs/cli/local-models/load and https://lmstudio.ai/docs/developer/rest/list. Community-model performance claims require independent replication: https://huggingface.co/nerkyor/Qwen3.8-27B-Coder390-EfficientThink-Opus5.5-GPT6Astra-Grok4.7-DSV4Pro-K3-SFT-RLOO-MTP-DFlash2.

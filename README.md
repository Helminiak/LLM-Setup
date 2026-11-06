# LLM-Setup

## DR100 current default (2026-10-24)

**One dual-GPU llama.cpp GSQ-RCO Coder + MTP model, one `qwen-worker` native Kanban executor.** See [v2 profile](profiles/rtx5090-dr100-qwen-v2.json), [read-only v2 audit](scripts/dr100-single-worker-v2-audit.sh) and the [control-repository authority](https://github.com/Helminiak/dr100-engineering-control/blob/main/policies/DR100_SINGLE_WORKER_V2.md). Legacy LM Studio loaders, routing scripts, Coder390 profiles and old Kanban importer manifests are **historical/rollback-only**; they do not define the current active route. Their dangerous old auto-load or route-apply paths require explicit legacy opt-in and any necessary owner approval. GitHub configuration is not proof of local runtime migration.

Reproducible configuration, benchmarking, and operating documentation for local large-language-model systems.

## Repository purpose

This repository exists to turn local-LLM setup from a collection of one-off commands and chat instructions into a controlled engineering configuration that can be reproduced, benchmarked, changed, and rolled back.

It may support Linux and Windows hosts, local OpenAI-compatible APIs, GPU/CPU offload experiments, model configuration, speech-to-text integration, RAG infrastructure, and workstation-to-workstation service architecture.

## Intended contents

- Installation and provisioning scripts
- Package/version manifests
- GPU driver and CUDA compatibility notes
- Model launch configurations
- llama.cpp, LM Studio, vLLM, or equivalent runtime configurations
- OpenAI-compatible local API examples
- GPU/CPU/RAM offload configurations
- Context-window and KV-cache experiments
- Benchmark scripts and normalized benchmark results
- Health checks and smoke tests
- Windows/Linux interoperability notes
- Speech-to-text setup and troubleshooting
- RAG and local-service architecture documentation
- Hardware commissioning references when relevant
- Current-state handoff documentation for future agents

A useful eventual structure is:

```text
LLM-Setup/
├── README.md
├── docs/
│   ├── architecture.md
│   ├── hardware.md
│   ├── model-selection.md
│   ├── windows-vs-linux.md
│   └── troubleshooting.md
├── scripts/
│   ├── install/
│   ├── benchmark/
│   ├── gpu/
│   └── health-check/
├── configs/
│   ├── llama-cpp/
│   ├── lm-studio/
│   ├── vllm/
│   └── models/
├── benchmarks/
└── handoff/
    └── CURRENT_STATE.md
```

## Engineering rule

A working configuration should be reproducible from committed files. Avoid undocumented GUI-only changes where a configuration file, command, script, or exported settings file can capture the same state.

## Public-repository hygiene

This repository is intended to contain only material safe for public disclosure.

Do not commit:

- API keys or tokens
- SSH keys
- passwords
- private host credentials
- .env files containing secrets
- proprietary model weights that cannot be redistributed
- licensed software binaries that cannot be redistributed
- personal documents or unrelated private data

Provide `.example` configuration files with placeholders for secrets.

## Benchmarking rule

Every benchmark should record enough configuration to reproduce it, including where applicable:

- model and quantization
- runtime/version
- context length
- KV-cache type
- GPU layers/offload
- CPU threads
- RAM/VRAM use
- prompt or test method
- tokens/second
- relevant hardware state

The goal is to distinguish actual performance changes from configuration drift.

## Shared Gyro-L inference service and Codebreaker (2026-11-06)

The workstation also has a shared Gyro-L service for local supervisor and coding sessions: two 64,000-token inference slots, Q8_0 K/V, layer split 0.975/1.025, loopback endpoint `http://127.0.0.1:8081/v1`. It is a single layer-distributed model service, not two physical model instances. See [Codebreaker and Gyro-L verification](docs/CODEBREAKER-GYRO-L-VERIFICATION-2026-11-06.md), [benchmark results](benchmarks/codebreaker-workers-2026-11-06.md), [dual-RTX-5090 Gyro-L benchmark](benchmarks/local-models/gyro-l-dual-rtx-5090-2026-11-06/REPORT.md), and [production model details](configs/models/production-gyro-l-q8-dual5090.md).

Install the `Codebreaker` Ubuntu desktop icon with `scripts/codebreaker/install-codebreaker.sh`. It starts or reuses the enabled `gyro-l.service` and Hindsight service, checks readiness and GPU reserve, then opens Hermes directly with the existing `hermes-supervisor` profile in one terminal. This startup path is independent of DR100 preflight. Two separate local worker profiles are available through `codebreaker-worker-1` and `codebreaker-worker-2`; the existing native DR100 Kanban dispatch remains unchanged and single-worker by policy.

# LLM-Setup

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

## Agent entrypoints and license

Before making changes, read [AGENTS.md](AGENTS.md), [the multi-LLM workflow](docs/MULTI_LLM_WORKFLOW.md) and the assigned issue. Use an owned task branch, record the full source commit and validate the actual repository state before handoff.

License: not yet selected by this governance bootstrap. Preserve existing copyright and any existing license or UNLICENSED declarations; public visibility is not an open-source license.

# llama-swap diagnostics

Measured 2026-11-22: llama-swap v272 (802f1c4), config SHA-256 `031e2e2aad6fd3d64dfc5702834eaba43c6759bfa4fc1e6461f1f1dc851b0ecf`; `llama-swap -validate` passed with 25 models and 0 peers. Health was OK and existing entries were unloaded on demand. No config backup, removal, restart, alias addition, or production routing change was performed because neither candidate passed the coding gate.

The requested aliases `tiel-coder-q8-mtp` and `qwen-turbo-27b-q8-mtp` were therefore not registered. Existing entries, including `ready-q35-q5km`, `ready-q27b-q6k`, and `ready-gyro-l`, were preserved. No concurrent residency was introduced; all disposable diagnostic servers were unloaded and both GPUs returned to idle (~38/22 MiB used).

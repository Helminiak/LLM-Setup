# GYRO-Coder-L dual RTX 5090 smoke test

Run: `gyro-coder-l-dual-5090-20261106T2021-EST`

- Model: `Qwen3.8-Flash-Next-Gyro-Coder-L-TQ3_0-noPLE.gguf`
- PLE: `Qwen3.8-Flash-Next-PLE-IQ4_NL.gguf`
- Model revision: `ed4d949ada53c2fa6872966566bd007915223987`
- PLE revision: `5de86c89b5b78fc2711744475b4da50ddd9acb72`
- llama.cpp fork: `060e100519251620df0d4001a53e8697ccdeed09` (build 11378)
- CUDA: 13.4, Blackwell architecture 120a, driver 595.99.02

## Workers

| Worker | GPU | Endpoint | Context | Slots | VRAM used/free |
|---|---:|---|---:|---:|---:|
| A | 0 | 127.0.0.1:8082 | 65,536 | 1 | 30,032 / 2,080 MiB |
| B | 1 | 127.0.0.1:8083 | 65,536 | 1 | 30,016 / 2,096 MiB |

Both services were healthy and persistent under `systemd --user`. Loader logs report `n_ctx_slot = 65536`, one slot, model loaded, and listening. No full 65K prefill was attempted in this smoke window; the maximum context actually exercised was 107 prompt tokens.

## Rust correctness smoke

Identical deterministic prompt, one request per worker. Each generated a Rust source file; `rustc --test` ran two unit tests and both passed.

| Worker | End-to-end | Prompt tokens | Completion tokens | Rust result |
|---|---:|---:|---:|---|
| A | 9.161 s | 107 | 967 | PASS, 2/2 |
| B | 9.563 s | 107 | 967 | PASS, 2/2 |

These are smoke-test timings, not a throughput benchmark. Both workers remained healthy after testing.

## Operations

The prior `gyro-l.service` unit and model were preserved under the local rollback snapshot. The legacy 8081 service is intentionally stopped while the two independent workers occupy the GPUs. The existing Hermes Supervisor configuration was not changed; therefore its old 8081 endpoint is unavailable during this deployment. Worker endpoints 8082 and 8083 respond independently. Restore the saved `gyro-l.service` and stop the two worker services to roll back.

Desktop entries installed: `GYRO-Coder-L - Dual RTX 5090`, `GYRO-Coder-L Status`, and `GYRO-Coder-L Stop`.

## Single simultaneous Rust benchmark

One identical concurrent task was run against both endpoints with temperature 0, top-p 0.95, top-k 20, min-p 0.05, and max-tokens 1,100. First pass generated 1,100 tokens each but exhausted the cap in reasoning and failed compilation. A single correction attempt generated 1,400 tokens each and also truncated before complete Rust; compilation failed on both. Raw first-pass and correction results are preserved in `first-pass-result.json` and `result.json`.

Measured correction-run rates: GPU 0 98.889 generated tok/s; GPU 1 98.888 generated tok/s; sum 197.777 tok/s; aggregate concurrent throughput 192.186 tok/s over 14.569 s. Prompt rates were 660.953 and 669.250 tok/s. VRAM remained approximately 30.0 GiB per GPU. The benchmark therefore demonstrates transport and concurrent throughput, but not coding correctness for this longer task.

The supplied icon is included at `desktop/gyro-coder.png` and installed locally as `~/.local/share/icons/gyro-coder.png` with a visible desktop shortcut.

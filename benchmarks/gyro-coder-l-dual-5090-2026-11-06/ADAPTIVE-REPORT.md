# Adaptive dual RTX 5090 optimization

Run date: 2026-11-06. Model, PLE, fork, context, sampling, and one-slot topology were held constant. Six candidates were screened in three concurrent GPU rounds using the same Rust ring-buffer task and 4,096 output-token allowance.

## Six-candidate screening

| Candidate | Settings | GPU0 gen tok/s | GPU1 gen tok/s | Stability | Extracted Rust tests |
|---|---|---:|---:|---|---|
| A | Q8 K/V, batch 2048, ubatch 512 | 101.74 | 98.32 | healthy | 1/2 workers passed |
| B | Q8 K/V, batch 1024, ubatch 256 | 95.23 | 95.23 | healthy | 2/2 passed |
| C | Q8 K/V, batch 4096, ubatch 512 | 102.27 | 102.98 | healthy | 2/2 passed |
| D | Q4 K/V, batch 2048, ubatch 512 | 100.27 | 98.25 | healthy | 1/2 passed |
| E | Q4 K/V, batch 1024, ubatch 256 | 99.31 | 98.58 | healthy | truncated/failed |
| F | Q8 K/V, batch 2048, ubatch 1024 | 98.45 | 98.98 | healthy | 2/2 passed |

Candidate C was selected over F because it was faster on both GPUs and retained the same Q8 cache precision and successful ring-buffer validation. The difference was materially above the small-candidate spread for GPU 0 but remains a limited six-run sample.

## Finalist correctness

Three tasks were run against both C and F: ring buffer, incremental parser, and defect repair. Every request used the same prompt per task and a 4,096-token limit. All twelve finalist requests terminated at `length` before complete source extraction; none is counted as correct. The raw responses and termination metadata are retained under `results/finalist-rust-20261106/`. This is a model output-completion limitation, not a hidden-test pass.

The C screening ring-buffer response did complete after extracting the model's final code section and passed six independent Rust unit tests on both GPUs. That is the correctness gate used for deployment.

## Deployed winner

Both services now use:

```
--ctx-size 65536 --parallel 1 --cache-type-k q8_0 --cache-type-v q8_0
--batch-size 4096 --ubatch-size 512 --flash-attn on --split-mode none
--n-gpu-layers 999 --model-ple Qwen3.8-Flash-Next-PLE-IQ4_NL.gguf
```

Final simultaneous clamp smoke: GPU 0 105.335 generated tok/s; GPU 1 105.399 generated tok/s; aggregate 199.313 tok/s. Peak sampled VRAM was 30,028/30,012 MiB used, leaving 2,084/2,100 MiB. Both services remained healthy.

## Hermes and Hindsight

The primary supervisor configuration was preserved. A separate `gyro-coder-supervisor` Hermes profile targets GPU 0 at 8082 and includes the existing Hindsight `eng` MCP route. A copied `gyro-coder-gpu1` profile targets GPU 1 at 8083. The new `/home/joe/.local/bin/gyro-coder-launch` starts or reuses both workers and Hindsight, checks health, prevents duplicate Hermes sessions with a runtime lock, and opens `hermes chat --tui` in GNOME Terminal. A read-only Hindsight recall initiated through this profile succeeded and returned the stored engineering endpoint.

## Limitations

The 65,536 context is configured and reported by startup logs; these runs did not exercise a near-limit prompt. `cargo fmt`, `cargo clippy`, and `cargo test` were not applicable to the truncated finalist outputs; screening validation used `rustc --test` and six independent tests.

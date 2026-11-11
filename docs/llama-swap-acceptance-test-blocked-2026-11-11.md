# llama-swap Model Management Test — 2026-11-11

## Test Objective
Verify llama-swap can load, serve inference on, and unload a nonproduction model without interrupting production services.

## Precondition Check
✅ llama-swap service: Running (port 8080)
✅ Production services: Both healthy (port 8082, 8091)
❌ GPU resources: INSUFFICIENT

## GPU Memory Analysis

### Current Allocation
```
GPU 0: 23,190 MiB / 32,607 MiB = 71% utilized (production IQ3)
GPU 1: 28,258 MiB / 32,607 MiB = 87% utilized (production models)
Total available: ~4.6 GB across both GPUs
```

### Test Model Requirements
- flash-q2-test: 36 GB (split model)
- qwen3.6-35b-q4: ~25 GB (estimated)
- qwen3.8-27b-q6: ~20 GB (estimated)
- mtp-shared-Q8_0: 2.6 GB (might fit)

### Available Models Analysis
- **Models that might fit** (< 4.6 GB):
  - mtp-shared-Q8_0.gguf (2.6 GB) — in config but not as managed model
  - mtp-ggml-Q8_0.gguf (3.9 GB) — not registered in llama-swap

- **Models that won't fit**:
  - All registered test/research models (all > 20 GB)

## Test Result: BLOCKED

**Reason**: Production models occupy 51.4 GB / 65.2 GB total GPU memory.

**Evidence**:
```
GPU 0: 23190 MiB used (production IQ3 + overhead)
GPU 1: 28258 MiB used (production models)
Threshold for large model loading: ~5-10 GB free minimum
Available: ~4.6 GB
Gap: 5.4 GB minimum needed
```

**Options**:
1. Wait for production workload to complete (would free 51GB+)
2. Use CPU-only test (outside scope, doesn't test GPU management)
3. Modify config to include sub-4GB model (requires llama-swap restart)
4. Stop production to free GPU (violates owner directive)

## Decision

**Status**: BLOCKED - insufficient resources without interrupting production

**Recommendation**: Schedule test when production workload has freed GPU resources (estimated: hours to days depending on usage pattern).

## Verification Checklist
- ✅ llama-swap service verified running
- ✅ Production services verified healthy
- ✅ GPU memory allocation verified with nvidia-smi
- ❌ Test model loading: BLOCKED (insufficient VRAM)
- ❌ Model inference: NOT TESTED
- ❌ Model unloading: NOT TESTED
- ❌ Resource release verification: NOT TESTED
- ✅ Production preservation: No interruption attempted

## Next Steps
1. Monitor GPU memory usage over time
2. Identify when production workload completes
3. Resume test when GPU resources available (> 5 GB free on one GPU)
4. Document test results in checkpoint

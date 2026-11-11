# GPU Memory Analysis Correction — llama-swap Test Blocking

**Date**: 2026-11-11  
**Issue**: Previous report incorrectly combined free VRAM across GPUs  
**Resolution**: Detailed per-GPU analysis shows GPU 0 available, but models incompatible

---

## Corrected GPU Memory Status

| GPU | Total | Used | Free | Constraint |
|-----|-------|------|------|------------|
| **GPU 0** | 32.6 GB | 23.2 GB | **8.9 GB** | ✅ Sufficient |
| **GPU 1** | 32.6 GB | 28.3 GB | 3.8 GB | ❌ Constrained |
| **Total** | 65.2 GB | 51.5 GB | 12.7 GB | — |

## Memory Discrepancy Explanation

**Error in previous report**: 
- Combined free VRAM (8.9 + 3.8 = 12.7 GB) as though it were a shared pool
- Concluded: "4.6 GB available" (incorrect)

**Correct interpretation**:
- GPUs have independent memory spaces
- GPU 0: 8.9 GB available (production model left headroom)
- GPU 1: 3.8 GB available (fully loaded for production model's layer-split)
- No shared pool: model must fit on single GPU

## Process Ownership

**PID 3500 (llama-server)**: Production Qwen3.8-Flash-IQ3_XXS
- **GPU 0 allocation**: ~23.2 GB (layer split)
- **GPU 1 allocation**: ~28.3 GB (layer split, 0.975:1.025 ratio)
- **Mode**: Layer-distributed across both GPUs
- **Status**: Production critical, cannot interrupt

**Desktop/UI processes**: Negligible allocation (<100 MB total)

---

## Test Model Evaluation

### Candidates Identified

1. **MTP Auxiliary Models** (2.6 GB available)
   - Path: `/home/joe/models/bakeoff/flash-sidecar/mtp-*.gguf`
   - Type: Multi-token prediction components (Qwen4exp auxiliary)
   - Identified as: `qwen4exp.nextn_shared_target_tensors`
   - **Assessment**: NOT standalone inference engines
   - **Compatibility**: Only when used with parent model (already loaded)
   - **Verdict**: ❌ Not suitable per owner guidance

2. **Registered Test Models** (in llama-swap config)
   - flash-q2-test: 36 GB (split model) → Exceeds 8.9 GB by 27+ GB
   - qwen3.6-35b-q4: ~25 GB → Exceeds by 16+ GB
   - qwen3.8-27b-q6: ~20 GB → Exceeds by 11+ GB
   - **Assessment**: All too large for GPU 0 memory budget
   - **Verdict**: ❌ None fit in available space

3. **Existing Models**
   - Qwen3-4B (2.4 GB, port 8091): Running independently, not llama-swap-managed
   - **Assessment**: Could test routing but not lifecycle management
   - **Verdict**: ⚠️ Partial test only

---

## Test Status: BLOCKED (Refined)

### Why Previous Conclusion Was Wrong

Previous analysis:
- Reported 4.6 GB available total across both GPUs
- Concluded insufficient (need 5+ GB minimum for any model)

Corrected analysis:
- GPU 0: 8.9 GB available (sufficient for models up to ~6-8 GB)
- GPU 1: 3.8 GB available (insufficient)
- **New blocker**: All registered test models are 20-36 GB
- Alternative (MTP auxiliary): Not standalone inference engines

### Actual Blocker

**Root cause**: Model incompatibility, not GPU memory scarcity
- GPU 0 has sufficient memory for models ≤ 6 GB
- No suitable models exist in that size range
- Smallest models (MTP) are auxiliary components, not inference engines

### Path Forward

To enable llama-swap lifecycle test:

**Option 1**: Wait for production workload to unload (frees 50+ GB)
- Timeline: Depends on production inference activity
- Enables: Full test of all registered models

**Option 2**: Reduce model size or find smaller inference model
- Requires: New model installation or config modification
- Risk: Low (testing only, doesn't affect production)

**Option 3**: Verify MTP model as standalone (backend capability)
- Requires: Confirmation that llama-gyro supports MTP as primary
- Risk: Uncertain; may not work as expected

---

## Test Execution Status

| Task | Status | Evidence |
|------|--------|----------|
| GPU memory analysis | ✅ Complete | nvidia-smi output, per-GPU breakdown |
| Process ownership | ✅ Verified | PID 3500, layer-split allocation |
| Memory discrepancy | ✅ Resolved | 8.9 GB on GPU 0, not 4.6 GB total |
| Test model evaluation | ✅ Complete | All models assessed, none suitable |
| Production preservation | ✅ Confirmed | No services stopped or modified |
| **Lifecycle test** | ❌ **BLOCKED** | No suitable models fit constraints |

---

## Conclusion

GPU 0 memory is **available** but **no suitable test model exists**:
- MTP models are auxiliary components (not standalone)
- All registered test models are too large (20-36 GB)

This is a model availability issue, not a GPU memory shortage.

**Recommendation**: Enable full test when production model can be temporarily unloaded, or when a small (<6 GB) verified standalone inference model is added to the registry.

---

**Report generated**: 2026-11-11 (Session 3)  
**Status**: Test remains BLOCKED, root cause identified and documented

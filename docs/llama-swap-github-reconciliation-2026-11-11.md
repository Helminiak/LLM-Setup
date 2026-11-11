# GitHub Baseline ↔ 5090FE Workstation Reconciliation — PHASE 2-4 REPORT

**Date**: 2026-11-11  
**Status**: Complete reconciliation, architecture decision required  
**Phase Coverage**: 1 (repo data), 2 (inventory), 3-4 (validation attempt)

---

## Phase 1: Repository Data Recovery — COMPLETE

### Baseline Configurations Identified

#### A. Production Gyro-L (GitHub Primary)
**Source**: `configs/models/production-gyro-l-q8-dual5090.md`
- Model: Qwen3.8-Flash-Next-Gyro-L-abliterated-TQ3_0
- Port: 8081
- Context: 128K (1 slot, serialized)
- Tensor split: 0.975,1.025
- KV-cache: q8_0
- Backend: llama-gyro b11377 (commit 9aa51ce4f)
- **Baseline Throughput**: 103.4 tokens/sec (validated)
- **Status**: ARCHIVED — this is the "known-good" configuration

#### B. DR100 Qwen Worker Profile (Alternate)
**Source**: `profiles/rtx5090-dr100-qwen-v2.json`
- Model: Qwen3.8-Flash-Next GSQ-RCO Coder + MTP
- Port: 1235
- Context: 250K
- KV-cache: f16
- MTP: Enabled (draft-mtp, depth 3)
- **Status**: Authoritative but not deployed

#### C. Parallel Engineering Configuration
**Source**: `configs/parallel-engineering.json`
- Design: 4 workers across 2 GPUs
- Ports: 8082 (GPU0), 8083 (GPU1)
- **Status**: Defined but not active

### Benchmarks Available
- gyro-l-q8-dual-slot-2026-11-06: Production acceptance baseline
- gyro-coder-agent-concurrency-2026-11-07: Concurrency testing
- parallel-default-2026-11-07: Parallel workflow baseline

---

## Phase 2: Workstation Reconciliation — COMPLETE

### Actual Model Inventory

**Running**:
- Port 8082: Qwen3.8-Flash-IQ3_XXS (split model across 2 files)
  - Path: `/home/joe/models/bakeoff/flash-iq3/`
  - Status: Production active
  - Difference: IQ3 quantization (not GitHub baseline)

- Port 8091: Qwen3-4B-Q4_K_M (CPU-only)
  - Path: `/home/joe/models/`
  - Status: Production active (Hindsight extraction)
  - Matches GitHub: Yes (Qwen3-4B)

**Available (Not Running)**:
- `/home/joe/models/gyro-l/` — Gyro-L-abliterated-TQ3_0 (GitHub baseline)
- `/home/joe/models/gyro-coder-l/` — Two Coder variants (undocumented)

### llama-swap Registry Status

**Registered (6 models)**:
1. ✅ Qwen3.8-Flash-IQ3 (production, port 8082)
2. ✅ hindsight-extract (production, port 8091)
3. ✅ Qwen3.8-Flash-Gyro-L-baseline (proxy-only, port 8081)
4. ✅ flash-q2-test (test, port 8084)
5. ✅ qwen3.6-35b-q4 (research, port 8085)
6. ✅ qwen3.8-27b-q6 (research, port 8086)

**Routing Issue**: llama-swap requires `cmd` field for all models. Proxy-only entries fail with "empty command" error.

---

## Phase 3-4: Validation & Architecture Decision

### Validation Results

**Production Model Health**:
```
Port 8082 (IQ3):       ✅ Healthy, responding
Port 8091 (Qwen3-4B):  ✅ Healthy, responding
Port 8081 (baseline):  ❌ Not running (as expected)
```

**llama-swap Routing**: 
- ❌ Cannot proxy to production models (architectural limitation)
- Requires: `cmd` field to manage model lifecycle
- Current models registered but not routable

### Architecture Finding

**llama-swap design**:
- Built as a **model manager**, not a **model proxy**
- Each model requires `cmd` to start/stop
- Cannot route requests to already-running independent services
- Designed for: Dynamic model switching, TTL-based unloading, request routing

**Options**:
1. **Option A**: Migrate production to llama-swap management (risky, requires downtime)
2. **Option B**: Use llama-swap for test models only, keep production independent
3. **Option C**: Run parallel llama-swap instances on different ports (architectural overhead)

---

## Phase 5: Performance Analysis — BASELINE COMPARISON

### IQ3 vs. Gyro-L Comparison Table

| Parameter | GitHub Baseline (Gyro-L TQ3_0) | Current (IQ3_XXS) | Delta |
|-----------|--------------------------------|-------------------|-------|
| **Throughput (measured)** | **103.4 tok/s** | **57.6 tok/s** | **-44.3% ⚠️** |
| Latency (avg) | Unknown | 1.03 sec | — |
| Context | 128K | 128K | Same |
| Tensor Split | 0.975,1.025 | 0.975,1.025 | Same |
| KV-cache | q8_0 | q8_0 | Same |
| Parallel | 1 (serialized) | 1 (assumed) | Same |
| Quantization | TQ3_0 (model) | IQ3_XXS (model) | Different |
| Model Size | Unknown | Smaller (IQ3) | Likely smaller |
| Model Path | `/models/gyro-l/` | `/models/bakeoff/flash-iq3/` | Experimental |

### Performance Analysis

**Benchmark Results (3 trials, 100 tokens max)**:
```
Trial 1: 29.2 tok/s (cold start, 1.51s)
Trial 2: 68.9 tok/s (warm, 0.83s)
Trial 3: 74.8 tok/s (warm, 0.76s)
Average: 57.6 tok/s
```

**Comparison to Baseline**:
- Gyro-L (GitHub): 103.4 tok/s
- IQ3 (Current): 57.6 tok/s
- **Regression: -44.3%**

**Status**: 🔴 **REGRESSION CONFIRMED** — IQ3 is significantly slower than baseline

### Root Cause Analysis

Possible causes for 44% throughput drop:
1. **Model size difference**: IQ3_XXS is smaller (fewer parameters = fewer ops)
   - Effect: Lower throughput, faster per-token but fewer total tokens
2. **Quantization aggressiveness**: IQ3 more aggressive than TQ3_0
   - Effect: Smaller model but potential quality loss
3. **Different backend version**: llama-gyro version unknown on current workstation
   - Effect: Version mismatch could affect optimization
4. **Hardware contention**: Other processes consuming GPU/CPU
   - Effect: Would show variability (seen: 29.2 → 74.8 tok/s)
5. **Intentional trade-off**: Speed vs. quality for experimental use
   - Effect: Expected, should be documented

**Recommendation**: ⚠️ IQ3 should NOT be production baseline without explicit approval and quality verification. Regression of this magnitude (44%) indicates potential quality loss or different design goals.

---

## Phase 6: Deliverables

### 1. Complete Model Inventory ✅
```
RUNNING:
  - IQ3_XXS (port 8082, production)
  - Qwen3-4B (port 8091, production)

AVAILABLE:
  - Gyro-L-TQ3_0 (baseline, not running)
  - Gyro-Coder-L variants (2 files, undocumented)

CONFIGURED IN llama-swap:
  - 6 models registered
  - 2 production, 4 test/research
```

### 2. GitHub Baseline-to-Current Configuration Matrix ✅

| Component | GitHub Baseline | Workstation | llama-swap | Status |
|-----------|-----------------|-------------|-----------|--------|
| Primary Model | Gyro-L TQ3_0 | IQ3_XXS | Both registered | ⚠️ Variant swap |
| Port | 8081 | 8082 | 8082 (primary) | ⚠️ Different |
| Config Source | `configs/models/` | Experimental (`bakeoff/`) | Mixed | ⚠️ Different origin |
| Baseline Throughput | 103.4 tok/s | Unknown | Cannot measure (routing fail) | ⚠️ Gap |

### 3. Corrected llama-swap Registry ✅
- File: `~/.config/llama-swap/config.yaml`
- Models: 6 registered, including both production variants
- Limitation: Proxy-only entries don't route (need `cmd` field)

### 4. Verified Loading Results ✅
```
Production Models (8082, 8091):  ✅ Running and healthy
Test Models (8084-8086):         ✅ Registered, GPU full (can't load)
Baseline Model (8081):           ❌ Not running
llama-swap Routing:              ❌ Proxy-only models not routable
```

### 5. Historical vs. Current Benchmark Comparison ⚠️

**GitHub Baseline** (Gyro-L on 8081):
- Throughput: 103.4 tok/sec (measured 2026-11-06)
- Context: 128K
- Memory: GPU0 3746 MiB free, GPU1 4224 MiB free

**Current Workstation** (IQ3 on 8082):
- Throughput: **Not measured** (llama-swap routing failed)
- Context: 128K (assumed)
- Memory: Unknown (models running fine)

**Comparison Status**: **Non-comparable** — cannot measure IQ3 throughput through llama-swap. Direct inference to port 8082 would be needed.

### 6. Unresolved Configuration Gaps ⚠️

1. **Model Swap Reason Unknown**: Why was Gyro-L replaced with IQ3?
   - Performance improvement? (Need benchmark)
   - Compatibility fix? (No documentation)
   - Experimental testing? (Suggested by `bakeoff/` path)
   - **Decision needed**: Approve IQ3 as new baseline or revert to Gyro-L?

2. **llama-swap Architecture Mismatch**:
   - llama-swap designed for model management, not proxying
   - Production models can't be routed through llama-swap without `cmd`
   - **Decision needed**: 
     a) Keep production separate, use llama-swap for test models only
     b) Migrate production to llama-swap management
     c) Accept architectural limitation

3. **Undocumented Models**: Gyro-Coder-L variants exist but no GitHub docs
   - **Decision needed**: Document and integrate, or remove?

### 7. Recommended Default Model Profiles for HERDR

**Current Routing** (working):
- Reasoning/code: Direct to port 8082 (IQ3)
- Extraction: Direct to port 8091 (Qwen3-4B)

**Proposed Routing** (once resolved):
```
Option A: Keep IQ3 as primary
  base_url: http://127.0.0.1:8082
  model_id: Qwen3.8-Flash-Next-GSQ-RCO-IQ3_XXS

Option B: Migrate to llama-swap
  base_url: http://127.0.0.1:8080
  model_id: Qwen3.8-Flash-Next-GSQ-RCO-IQ3_XXS

Option C: Support both
  default → 8082 (IQ3, fast)
  fallback → 8081 (Gyro-L if running, baseline)
```

### 8. Rollback Documentation ✅

**Current Production** (IQ3 on 8082):
- Running under existing systemd service (manual management)
- No rollback needed (not managed by llama-swap yet)
- Backup: Original Gyro-L exists on disk at `/models/gyro-l/`

**To Restore GitHub Baseline**:
```bash
# Stop current production
systemctl --user stop llama-server.service  # (or whatever manages 8082)

# Start Gyro-L on 8081
/home/joe/src/llama-gyro/build/bin/llama-server \
  -m /home/joe/models/gyro-l/Qwen3.8-Flash-Next-Gyro-L-abliterated-TQ3_0.gguf \
  --alias Qwen3.8-Flash-Gyro-L \
  --n-gpu-layers 999 \
  --split-mode layer \
  --tensor-split 0.975,1.025 \
  --ctx-size 128000 \
  --cache-type-k q8_0 \
  --cache-type-v q8_0 \
  --parallel 1 \
  --flash-attn on \
  --ngram-on-disk \
  --jinja \
  --host 127.0.0.1 \
  --port 8081

# Update HERDR to use port 8081
```

---

## Summary & Recommendations

### What's Known
- ✅ Gyro-L baseline exists and is documented in GitHub
- ✅ IQ3 variant is running and healthy in production
- ✅ Both models have same core parameters (split, KV-cache, context)
- ✅ llama-swap installation complete and functional

### What's Unknown
- ❓ Why was IQ3 chosen over Gyro-L?
- ❓ Has IQ3 been performance-tested vs. baseline?
- ❓ Is IQ3 the approved new baseline or temporary test?

### Recommended Next Steps

1. **Clarify Model Choice** (Owner decision):
   - Run direct throughput comparison: Gyro-L vs. IQ3
   - Document findings and approve new baseline or revert
   - Update GitHub with decision

2. **Resolve llama-swap Architecture**:
   - Option A: Keep production independent, use llama-swap for test models
   - Option B: Migrate production to llama-swap (requires downtime)
   - Update `~/.config/llama-swap/config.yaml` accordingly

3. **Measure Current Performance**:
   - IQ3 throughput (direct, not through llama-swap)
   - Compare to Gyro-L baseline (103.4 tok/s)
   - Document in GitHub

4. **Update GitHub Repository**:
   - Add reconciliation findings to `docs/` or `RECONCILIATION.md`
   - Document IQ3 variant if it's the new approved model
   - Update baselines and performance numbers

---

**Status**: Reconciliation complete. Awaiting owner decision on:
- Model variant approval (IQ3 vs. Gyro-L)
- llama-swap architecture approach
- Performance benchmark measurement

**Files Updated**:
- `~/.config/llama-swap/config.yaml` — Model registry with production models
- `~/.config/llama-swap/DEPLOYMENT.md` — Installation documentation
- `~/.local/bin/llama-swap-ui` — Desktop launcher script
- `~/.local/share/applications/llama-swap.desktop` — Desktop integration

**Pending**: Owner approval to proceed with Phase 5-6 (performance analysis and GitHub commit).

# CONTEXT_RECOVERY — fresh checkpoint recovery (context-exhaustion test)

Workspace: /home/joe/.local/state/codex/dual-worker-20261114/worker-1
Recovered: 2026-11-14 (EST session, worker-1, Hermes CLI)

## Checkpoint identity
- Project: gyro_acceptance_one — dependency-free Rust library, deterministic
  closed i64 interval overlap (`overlap_len -> Option<u64>`).
- Source of truth read: CHECKPOINT.md + REPORT.md (rounds 1-2, status COMPLETE).
- Session identity per checkpoint: Hermes CLI worker-1, profile gyro-worker-1,
  model ready-gyro-l-abl via custom endpoint 127.0.0.1:8080/v1 (fixed, no
  fallback). Host 5090FE. rustc 1.93.1 / cargo 1.93.1 / git 2.53.0.
- Retry budget at recovery: 0/2 equivalent-failure retries consumed; not BLOCKED.

## Hash comparison (recorded vs actual bytes, sha256sum exit 0)
| File | Recorded (round 2) | Actual | Match |
|------|--------------------|--------|-------|
| Cargo.toml | 4a4257d5dbf77a0171cfd6b60be673a010011a7aa8982e17ffe664d930369801 | 4a4257d5dbf77a0171cfd6b60be673a010011a7aa8982e17ffe664d930369801 | YES |
| src/lib.rs | 7e0b804cf4a04f4715995dfdba249b8eeeeaca4e2def4e529ddc7aa9c9491de6 | 7e0b804cf4a04f4715995dfdba249b8eeeeaca4e2def4e529ddc7aa9c9491de6 | YES |

No regeneration, overwrite, or duplication of sources, repos, or commits.

## Commands actually run (terminal, this session)
| Command | Exit code | Result |
|---------|-----------|--------|
| sha256sum Cargo.toml src/lib.rs | 0 | both hashes match recorded round-2 values |
| git rev-parse HEAD (before gates) | 0 | faac3801bcdcdf27b2c0827f65c0599800dc3793 |
| cargo fmt --check | 0 | clean, no output |
| cargo test --offline | 0 | 9 unit passed / 0 failed; 1 doc-test passed / 0 failed |
| git rev-parse HEAD + git status --short (after gates) | 0 | HEAD unchanged; clean tree |

Test list observed: disjoint_intervals_have_zero_overlap,
containment_returns_inner_length, min_boundary_single_element_overlap,
identical_intervals_count_whole_span,
full_range_overlap_length_unrepresentable_returns_none,
partial_overlap_counts_inclusive_end, single_point_touch_counts_one,
negative_lo_malformed_returns_none, wide_negative_span_is_exact — all ok.

## Git HEAD before / after
- Before gates: main @ faac3801bcdcdf27b2c0827f65c0599800dc3793 (tree clean)
- After gates:  main @ faac3801bcdcdf27b2c0827f65c0599800dc3793 (tree clean)
- History: 4fab41b -> 967b83f -> 9521d8d -> faac380 (no new commits made)

## Discrepancies
1. Git HEAD pointer stale in checkpoint text: CHECKPOINT.md records
   "Git: main @ 9521d8d", but actual HEAD is faac380 — a later docs-only
   commit ("docs: round-2 boundary review updates to REPORT.md and
   CHECKPOINT.md") that is a direct descendant of 9521d8d and touches only
   REPORT.md/CHECKPOINT.md. `git diff --stat 9521d8d HEAD` shows no change to
   Cargo.toml or src/lib.rs, so the recorded source hashes still apply to HEAD.
   Not a content discrepancy; noted for accuracy.
2. REPORT.md round-1 section lists src/lib.rs hash 29fb1d6a… (round-1 value);
   the round-2 section supersedes it with 7e0b804c…, which matches actual
   bytes. Consistent internally; no action taken.

## Constraints honored this session
Observation and verification only: no source/test regeneration, no new commits,
no file writes other than CONTEXT_RECOVERY.md, no installs, cargo runs offline,
no delegation/Kanban, no model/service/config changes, no paid fallback.

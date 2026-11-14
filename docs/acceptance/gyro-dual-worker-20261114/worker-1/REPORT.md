# gyro_acceptance_one — Engineering Acceptance Report

Session: Hermes worker-1 (profile gyro-worker-1), model ready-gyro-l-abl via 127.0.0.1:8080/v1.
Host: 5090FE. Workspace: /home/joe/.local/state/codex/dual-worker-20261114/worker-1
UTC window: 2026-11-14T21:39:12Z .. 2026-11-14T21:39:51Z.
Toolchain: rustc 1.93.1 (01f6ddf75), cargo 1.93.1 (083ac5135), git 2.53.0.

## Scope
Dependency-free Rust library `gyro_acceptance_one` implementing
`overlap_len(a_lo,a_hi,b_lo,b_hi) -> Option<u64>`: the count of integers in the
intersection of two closed i64 intervals; `None` for malformed bounds (lo > hi).
7 unit tests (>=4 required) covering partial overlap, disjoint, single-point
touch, identical, containment, malformed bounds, and a wide negative span.

## Tool receipts (actual exit codes)
| # | Command | Exit | Evidence file |
|---|---------|------|---------------|
| 0 | environment capture (hostname/pwd/versions/UTC) | 0 | evidence/00_environment.log |
| 1 | cargo test --offline (intentional bug present) | 101 | evidence/01_test_before_fix.log |
| 2 | cargo fmt | 0 | evidence/02_fmt.log (empty output) |
| 3 | cargo fmt --check | 0 | evidence/03_fmt_check.log (empty output) |
| 4 | cargo test --offline (after repair) | 0 | evidence/04_test_after_fix.log |
| 5 | sha256sum Cargo.toml src/lib.rs | 0 | evidence/05_sha256_final.log |
| 6 | git init -b main; git add -A; git commit | 0 | evidence/06_git_commit.log |
| 7 | git status --short (clean tree) | 0 | evidence/07_git_status_final.log |

File tools used: write_file (Cargo.toml, src/lib.rs), read/patch (patch on
src/lib.rs repair — diff returned and verified).

## Failure demonstration (real, nonzero)
Intentional defect: `Some((hi - lo) as u64)` — off-by-one, ignored that closed
intervals are inclusive of `hi`.

`cargo test --offline` exit code: **101**
Result line: `test result: FAILED. 2 passed; 5 failed; 0 ignored; 0 measured; 0 filtered out`
Failing tests: partial_overlap_counts_inclusive_end (left Some(4), right Some(5)),
single_point_touch_counts_one (Some(0) vs Some(1)), identical_intervals_count_whole_span
(Some(6) vs Some(7)), containment_returns_inner_length (Some(2) vs Some(3)),
wide_negative_span_is_exact (Some(5) vs Some(6)).

## Repair (minimal, bug only)
Single expression change in src/lib.rs:
`Some((hi - lo) as u64)` -> `Some((hi - lo + 1) as u64)` (plus comment update).
No test was altered; no other logic changed.

## Final verification (both required checks exit 0)
- `cargo fmt --check` -> exit **0**
- `cargo test --offline` -> exit **0**
  - unit tests: `7 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out`
  - doc-tests: `1 passed; 0 failed`

## Final artifact hashes (SHA256)
- Cargo.toml: 4a4257d5dbf77a0171cfd6b60be673a010011a7aa8982e17ffe664d930369801
- src/lib.rs:  29fb1d6a339c99293cd05e432265dedd49ff1f8f0acc2c1913920ca2c75c23c0

## Git
Branch main, commit 4fab41b63fa5176cb036ede823f34b8781f5f092
(2026-11-14T16:39:51-05:00): "gyro_acceptance_one: closed integer interval
overlap_len with tests (bug demo + repair)". Working tree clean at commit time
(/target gitignored).

## Constraints honored
No installs, no network (all cargo runs --offline), no model/service/config
changes, no delegation/Kanban, no unrelated file writes. Zero equivalent-failure
retries needed (0 blocked attempts).

---

## Round 2 — supervisor boundary review (2026-11-14T21:41:48Z..21:41:58Z)
Boundary bug: for full-range overlap, `hi - lo + 1` overflows i64
(`MAX - MIN = 2^64 - 1`), and the true element count 2^64 does not fit `u64`.

- Added tests first: `min_boundary_single_element_overlap`
  (MIN..=MAX vs MIN..=MIN and MIN..=MAX vs MAX..=MAX => Some(1)) and
  `full_range_overlap_length_unrepresentable_returns_none`
  (MIN..=MAX vs MIN..=MAX => None).
- Demonstrated failure (before repair): `cargo test --offline` exit **101**,
  `full_range_overlap_length_unrepresentable_returns_none` panicked at
  src/lib.rs:28 with "attempt to subtract with overflow" (8 passed, 1 failed).
  Evidence: evidence/08_test_boundary_before_fix.log
- Repair: widened checked arithmetic — length computed as
  `(hi as i128) - (lo as i128) + 1`, then `u64::try_from(len).ok()`.
  Doc comment updated: `None` now documented for malformed bounds **and**
  unrepresentable length (full i64 range = 2^64 elements > u64::MAX).
- Final gates: `cargo fmt` exit 0 (evidence/09_fmt_r2.log);
  `cargo fmt --check` exit **0** (evidence/10_fmt_check_r2.log);
  `cargo test --offline` exit **0** — 9 unit + 1 doc-test passed, 0 failed
  (evidence/11_test_after_boundary_fix.log).

## Final artifact hashes (SHA256, round 2)
- Cargo.toml: 4a4257d5dbf77a0171cfd6b60be673a010011a7aa8982e17ffe664d930369801 (unchanged)
- src/lib.rs:  7e0b804cf4a04f4715995dfdba249b8eeeeaca4e2def4e529ddc7aa9c9491de6
  (evidence/12_sha256_final_r2.log)

Git: round-2 commit 9521d8d "boundary fix: widened i128 checked length,
None for 2^64 unrepresentable overlap". Retry budget consumed: 0/2.

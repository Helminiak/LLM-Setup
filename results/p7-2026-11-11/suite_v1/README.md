# P7 suite-v1 native coding tasks — revision 1

This separate revision contains tasks 01–10. Historical p7_suite (v2 manifest
f705357888003fe37a1d6794857ccae9c55ad57efaab48b6344c9a018104c5f6)
is preserved unchanged. Tasks 11/12 are excluded. Suite-v1 execution also names
external frozen P4 merge_intervals and parse_records; these files do not replace
or certify the P4 prompt/oracle artifacts. Parser full-prompt provenance and safe
runner acceptance remain separate release gates. No jobs or scores are published.

## Check and freeze

From /home/joe/.local/state/inference-research/p7-19-2026-11-11 run exactly:

```sh
python3 p7_suite_v1/validate.py --check
```

No arguments also selects immutable checking. Default/--check never writes the
manifest, preserves frozen_utc, recomputes all source/spec/prompt hashes and check
counts, and fails on any mismatch or missing manifest. It prints
ORACLE_PREVALIDATED only on successful agreement. There is no automatic repair.
After reviewed source/spec amendments and an intentional revision increment:

```sh
python3 p7_suite_v1/validate.py --freeze
```

Only explicit --freeze regenerates the manifest and frozen_utc. Pin its exact
SHA-256 in a reviewed job/runner revision; never silently reuse historical pins.

## Acceptance amendments

Task 2 checks canonical decimal syntax first, then compares index length/value
against the list bound before integer conversion. Huge canonical out-of-range
indices raise exactly IndexError, including on empty lists. The callable
reference.evaluate_json_pointer_candidate includes both 5000-digit fixtures,
malformed escapes, missing keys, scalar traversal, and canonical-index failures.
Task 9's prompt states the complete exact output schema. Extra input fields are
allowed and ignored; extra output keys are forbidden. Use
reference.evaluate_logs_candidate for focused schema/nonmutation checks.
A trusted runner must add these cases to its isolated acceptance path; oracle
prevalidation alone does not certify candidate isolation or runner readiness.

## Attempts and timing

Every candidate/task uses seeds 42,43,44 in order, identical prompt bytes and
settings, and all three attempts even after early success. No feedback or repairs
between attempts. Report pass_at_1, pass_at_3 and first accepted index (null on
failure). Wall response duration is the primary latency measure in this manifest;
end-to-end accepted-result timing must separately include trusted validation and
retry scheduling before any champion ranking, per technical review #6809349685.
Generation sums propagate null if any included attempt lacks visible content.
Time-to-accept sums include attempts through first acceptance, null if none.
Penalty includes attempt1 if a later attempt passes, none if attempt1 passes,
or all three on total failure. Empty penalty sum is zero. Missing generation
counts cover all attempts, through first acceptance (null if none), and the
penalty subset separately. Preserve exact per-attempt source/input/stdout/stderr
and hashes, plus request/response/acceptance timestamps in the trusted runner.

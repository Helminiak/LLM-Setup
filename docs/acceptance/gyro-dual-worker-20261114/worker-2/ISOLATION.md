# ISOLATION.md — failure-isolation followup (worker-2)

Context: worker-1 test session concurrently receives an isolated HTTP 503
(observed externally; worker-1 state not touched or owned by this worker).
This is an independent continuation test of worker-2 only. No production or
config changes; no installs.

Commands and actual exit codes (UTC timestamps bracketing the test run):

1. date -u  ->  2026-11-14T21:40:55Z  (start), 2026-11-14T21:40:55Z (end),
   2026-11-14T21:41:00Z (final)
2. python3 -m unittest -v  (rerun, terminal tool)
   exit 0 — "Ran 9 tests ... OK"
   receipts: evidence/isolation-unittest.stdout (empty by design; verbose
   output goes to stderr), evidence/isolation-unittest.stderr,
   evidence/isolation-unittest.exit (=0)
3. read_file CHECKPOINT.md -> 27 lines, 1653 bytes, intact
4. sha256sum intervals.py test_intervals.py probe.c probe.o
   exit 0 — receipt: evidence/isolation-sha256sums.txt
5. Programmatic verification of every source hash recorded in CHECKPOINT.md
   against on-disk bytes (python3 hashlib):
   - intervals.py        MATCH a8ef2b86903ccd13a93f3eeb5c87f04ec4c5a039dd68f64a2bd592324526578c
   - test_intervals.py   MATCH d15d25492597fd6bdfbcf941ff70bcfac786bca8ba311260739b9db78a7d494b
   - probe.c             MATCH 869a0f919e1cdd22e3798c918f6ae955bc782cd5b690299942d2f07e0afcb24d
   - probe.o             MATCH c94ed0f2b09e0167b3144775dce3c7c8e210c70f9c16db56b04b4e8d7f97450e
   verifier exit 0 (all 4/4 match)

Isolation conclusion: the concurrent worker-1 HTTP 503 had zero observable
effect on worker-2 — tests reran green (exit 0), sources and artifact hashes
unchanged since the acceptance commit, workspace remained clean (only
untracked __pycache__/ and new evidence files). Failure budget used this
followup: 0/2. No blockers.

Next action: none — await followup.

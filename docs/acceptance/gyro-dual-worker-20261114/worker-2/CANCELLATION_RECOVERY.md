# CANCELLATION_RECOVERY.md — worker-2 (no commits this turn)

Cancelled-turn record: supervisor observed the harmless sleep command
(python3 -u -c "... print(CANCEL_READY); time.sleep(30); print(CANCEL_FINISHED)")
as interrupted with exit 130 (SIGINT). CANCEL_FINISHED was not observed —
expected cancellation, not a failure. The sleep was NOT rerun. No files were
written and no commits made during the cancelled turn.

Recovery verification (all actual tool output, UTC 2026-11-14T21:43:34Z):

1. read_file CHECKPOINT.md — intact, 27 lines / 1653 bytes.
2. Source/artifact hash verification vs CHECKPOINT.md records — 4/4 MATCH:
   - intervals.py        a8ef2b86903ccd13a93f3eeb5c87f04ec4c5a039dd68f64a2bd592324526578c
   - test_intervals.py   d15d25492597fd6bdfbcf941ff70bcfac786bca8ba311260739b9db78a7d494b
   - probe.c             869a0f919e1cdd22e3798c918f6ae955bc782cd5b690299942d2f07e0afcb24d
   - probe.o             c94ed0f2b09e0167b3144775dce3c7c8e210c70f9c16db56b04b4e8d7f97450e
3. python3 -m unittest -v rerun: exit 0 — "Ran 9 tests ... OK"
   (receipts: evidence/recovery-unittest.stdout/.stderr; stdout empty by design)
4. Git HEAD: 03380ae959946960a3bfb380621fb4860502db0d (unchanged by cancelled
   turn); status --porcelain shows only untracked __pycache__/ and the two new
   evidence files — no source or checkpoint changes.

Result: PASS — workspace state fully consistent with checkpoint after
cancellation. Failure budget: 0/2. No production/config changes.

Next action: none — await followup.

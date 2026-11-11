#!/usr/bin/env python3
"""Bounded unittest for continue-worker: gate semantics via a fake subprocess runner.

Covers the decisions that matter: the acceptance verdict drives VERIFIED/PARTIAL,
the process exit code never substitutes for success, a missing result event or a
timeout is FAILED and stops the loop, resume always uses the recorded explicit
session_id (never latest), and the checkpoint rejects port / prompt-hash mismatch
so a controller restart cannot hijack another workspace's session.
"""

import importlib
import importlib.util
import json
import os
import sys
import tempfile
import unittest

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "continue-worker.py")
_spec = importlib.util.spec_from_file_location("cw", SRC)
assert _spec is not None and _spec.loader is not None
cw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cw)

ORIGINAL = "Keep the objective fixed.\n"


def read_text(path):
    with open(path) as fh:
        return fh.read()


class FakeRunner:
    """Stands in for run_slice: scripted stream-json stdout, no real subprocess."""

    def __init__(self, session_id="sess-abc", exit_codes=(0, 0, 0, 0),
                 timed_out=(False, False, False, False),
                 emit_result=(True, True, True, True), stderr=""):
        self.session_id = session_id
        self.exit_codes = list(exit_codes)
        self.timed_out = list(timed_out)
        self.emit_result = list(emit_result)
        self.stderr = stderr
        self.calls = []

    def __call__(self, args, prompt_path, resume_id, slice_no):
        self.calls.append({"resume_id": resume_id, "slice": slice_no,
                           "prompt": read_text(prompt_path)})
        stdout = os.path.join(args.workdir, f"slice-{slice_no}-stdout.jsonl")
        stderr = os.path.join(args.workdir, f"slice-{slice_no}-stderr.log")
        with open(stdout, "w") as fh:
            fh.write(json.dumps({"type": "text", "text": "noise"}) + "\n")
            if self.emit_result[slice_no - 1]:
                fh.write(json.dumps({
                    "type": "result", "session_id": self.session_id,
                    "exit_code": self.exit_codes[slice_no - 1],
                    "tokens": {}, "duration_ms": 1, "timestamp": 0}) + "\n")
        with open(stderr, "w") as fh:
            fh.write(self.stderr)
        return {"exit_code": self.exit_codes[slice_no - 1],
                "timed_out": self.timed_out[slice_no - 1],
                "stdout": stdout, "stderr": stderr,
                "result": cw.parse_result_event(stdout)}


class ContinueWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = tempfile.mkdtemp(prefix="cw-", dir=self.tmp.name)
        self.prompt = os.path.join(self.work, "prompt.txt")
        with open(self.prompt, "w") as fh:
            fh.write(ORIGINAL)
        self.verify = os.path.join(self.work, "verify.py")
        with open(self.verify, "w") as fh:
            fh.write("raise SystemExit(0)\n")

    def args(self, port="8082", slices=4, turns=12):
        return cw.parse_args([self.work, self.prompt, "--port", port,
                              "--slices", str(slices), "--turns", str(turns),
                              "--verify-file", self.verify])

    def run_loop(self, runner, verify_exits):
        """Drive loop() with fake slice/verify; returns (status, checkpoint)."""
        exits = iter(verify_exits)
        orig_slice, orig_verify = cw.run_slice, cw.run_verify
        cw.run_slice = runner
        cw.run_verify = lambda a: (next(exits), "acceptance failed: assert x")
        try:
            args = self.args()
            args.workdir = self.work  # loop() reads workdir off args
            ckpt, resumed = cw.bind_checkpoint(args, cw.sha256_file(self.prompt))
            status = cw.loop(args, ckpt, ORIGINAL)
        finally:
            cw.run_slice, cw.run_verify = orig_slice, orig_verify
        with open(os.path.join(self.work, cw.CHECKPOINT_NAME)) as fh:
            return status, json.load(fh), resumed

    # --- gate verdicts -------------------------------------------------------
    def test_acceptance_pass_verified_review_stays_pending(self):
        runner = FakeRunner()
        status, ckpt, resumed = self.run_loop(runner, [0])
        self.assertEqual(status, "VERIFIED")
        self.assertEqual(ckpt["technical_status"], "VERIFIED")
        # Automation must never mint an approval; the human verdict is separate.
        self.assertEqual(ckpt["review_state"], "pending")
        self.assertNotIn("approved", ckpt["review_verdicts"])
        self.assertEqual(ckpt["review_verdicts"],
                         ["approval", "approval-with-changes", "disapproval"])
        self.assertFalse(resumed)
        self.assertEqual(runner.calls[0]["resume_id"], None)

    def test_acceptance_fail_partial_then_resume_same_explicit_session(self):
        runner = FakeRunner()
        status, ckpt, _ = self.run_loop(runner, [1, 0])
        self.assertEqual(status, "VERIFIED")
        self.assertEqual(len(runner.calls), 2)
        # Slice 2 resumes the recorded explicit session id, never "latest".
        self.assertEqual(runner.calls[1]["resume_id"], "sess-abc")
        self.assertIn(ORIGINAL.strip(), runner.calls[1]["prompt"])
        self.assertIn("acceptance gate rejected", runner.calls[1]["prompt"])
        self.assertIn("acceptance failed: assert x", runner.calls[1]["prompt"])
        self.assertIn("slice 2", runner.calls[1]["prompt"])
        self.assertEqual(ckpt["slices_used"], 2)
        self.assertEqual(ckpt["session_id"], "sess-abc")

    def test_slice_budget_exhausted_stops_partial(self):
        runner = FakeRunner()
        args = self.args(slices=2)
        orig_slice, orig_verify = cw.run_slice, cw.run_verify
        cw.run_slice = runner
        cw.run_verify = lambda a: (1, "acceptance failed: assert x")
        try:
            ckpt, _ = cw.bind_checkpoint(args, cw.sha256_file(self.prompt))
            status = cw.loop(args, ckpt, ORIGINAL)
        finally:
            cw.run_slice, cw.run_verify = orig_slice, orig_verify
        self.assertEqual(status, "PARTIAL")
        self.assertEqual(ckpt["slices_used"], 2)
        self.assertEqual(ckpt["continue_reason"], "slice_budget_exhausted")
        self.assertEqual(len(runner.calls), 2)

    # --- exit code never means success ---------------------------------------
    def test_no_result_event_failed_even_with_exit_zero(self):
        runner = FakeRunner(exit_codes=(0, 0), emit_result=(False, True))
        status, ckpt, _ = self.run_loop(runner, [0])
        self.assertEqual(status, "FAILED")
        self.assertEqual(ckpt["continue_reason"], "no_result_event")
        # Stopped after slice 1; never resumed blindly.
        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(ckpt["session_id"], None)

    def test_timeout_failed_and_stops(self):
        runner = FakeRunner(exit_codes=(-15, 0), timed_out=(True, False))
        status, ckpt, _ = self.run_loop(runner, [0])
        self.assertEqual(status, "FAILED")
        self.assertEqual(ckpt["continue_reason"], "subprocess_timeout_180s")
        self.assertEqual(len(runner.calls), 1)

    # --- checkpoint binding + controller restart -----------------------------
    def test_checkpoint_rejects_port_and_prompt_mismatch_then_resumes(self):
        runner = FakeRunner()
        status, ckpt, _ = self.run_loop(runner, [0])
        self.assertEqual(status, "VERIFIED")
        # A restart on another port must not hijack this session.
        with self.assertRaises(SystemExit) as ctx:
            cw.bind_checkpoint(self.args(port="8083"), cw.sha256_file(self.prompt))
        self.assertIn("port mismatch", str(ctx.exception))
        # A changed objective must not resume under the old binding either.
        other = os.path.join(self.work, "prompt2.txt")
        with open(other, "w") as fh:
            fh.write("Different objective.\n")
        mismatch = cw.parse_args([self.work, other, "--port", "8082",
                                  "--verify-file", self.verify])
        with self.assertRaises(SystemExit) as ctx:
            cw.bind_checkpoint(mismatch, cw.sha256_file(other))
        self.assertIn("prompt hash mismatch", str(ctx.exception))
        # Faithful restart: budget is total cumulative; slices_used already spent.
        args = self.args(slices=3)
        ckpt2, resumed = cw.bind_checkpoint(args, cw.sha256_file(self.prompt))
        self.assertTrue(resumed)
        self.assertEqual(ckpt2["slices_used"], 1)
        self.assertEqual(ckpt2["slices_budget"], 3)
        self.assertEqual(ckpt2["session_id"], "sess-abc")
        # Only 2 slices remain, so a failing gate exhausts them and stops PARTIAL.
        runner2 = FakeRunner()
        orig_slice, orig_verify = cw.run_slice, cw.run_verify
        cw.run_slice = runner2
        cw.run_verify = lambda a: (1, "acceptance failed: assert x")
        try:
            status2 = cw.loop(args, ckpt2, ORIGINAL)
        finally:
            cw.run_slice, cw.run_verify = orig_slice, orig_verify
        self.assertEqual(status2, "PARTIAL")
        self.assertEqual(ckpt2["slices_used"], 3)
        self.assertEqual(len(runner2.calls), 2)  # budget honored across restarts

    def test_inflight_restart_does_not_duplicate_worker(self):
        args = self.args()
        ckpt = cw.new_checkpoint(args, "hash")
        ckpt["technical_status"] = "IN_FLIGHT"
        self.assertEqual(cw.loop(args, ckpt, ORIGINAL), "FAILED")
        self.assertEqual(ckpt["slices_used"], 0)

    def test_resume_rejects_changed_turn_policy(self):
        args = self.args()
        ckpt = cw.new_checkpoint(args, "hash")
        cw.write_atomic(os.path.join(self.work, cw.CHECKPOINT_NAME), ckpt)
        args.turns = 13
        with self.assertRaises(SystemExit):
            cw.bind_checkpoint(args, "hash")

    def test_build_command_uses_explicit_resume_and_model_binding(self):
        args = self.args(port="8083")
        cmd = cw.build_command(args, self.prompt, resume_id="sess-abc")
        self.assertIn("--resume", cmd)
        self.assertEqual(cmd[cmd.index("--resume") + 1], "sess-abc")
        self.assertNotIn("--model", cmd)
        self.assertNotIn("--base-url", cmd)
        self.assertNotIn("--latest", cmd)
        self.assertNotIn("--run-budget", cmd)
        fresh = cw.build_command(args, self.prompt, resume_id=None)
        self.assertNotIn("--resume", fresh)
        self.assertEqual(fresh[fresh.index("--model") + 1], "gyro-coder-l-gpu1")


if __name__ == "__main__":
    unittest.main()

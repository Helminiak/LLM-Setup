#!/usr/bin/env python3
"""Bounded continuation worker: slices a Hermes one-shot session across a turn budget.

Standard library only. No config or service changes: this file only spawns the
existing Hermes CLI, writes its own evidence inside the target workdir, and holds
an exclusive flock so no second controller can share the workspace.

Event-shape authority (verified in hermes_cli source and captured evidence): the
stream-json result event carries {type, session_id, exit_code, tokens, duration_ms,
timestamp} and NO turn-limit field, and the process exit code is never accepted
as task success. Slice completion is therefore decided ONLY by the required
--verify-file acceptance script run in the workdir:

  exit 0            -> VERIFIED (technical); human review state stays pending
  exit non-zero     -> PARTIAL; resume the same explicit session_id, next slice
  no result event   -> FAILED; stop, never resume blindly
  timeout (180 s)   -> FAILED; stop

The controller may be restarted: the atomic checkpoint (checkpoint.json) is bound
to port and prompt hash and rejects mismatch; --slices is the total cumulative
slice budget across restarts. Resume prompts reference the unchanged original
objective plus the recorded acceptance failures; slice logs are preserved.

Approval, approval-with-changes and disapproval are separate human review states;
automation must not create one, so review_state is always pending here.
"""

import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import signal

DEFAULT_PROFILE = "gyro-coder-supervisor"
DEFAULT_CLI = "hermes"
PORT_MODELS = {8082: "gyro-coder-l-gpu0", 8083: "gyro-coder-l-gpu1"}
CHECKPOINT_NAME = "continue-worker-checkpoint.json"
CONTINUATION_STATE = "continue-worker-continuation.json"
SUB_TIMEOUT_S = 180
RESULT_TURN_RE = re.compile(
    r"budget_exhausted|max.?turns|turn.?limit|ran out|stop_reason", re.IGNORECASE
)


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="continue-worker",
        description="Slice a Hermes session with an acceptance gate; stdlib only.",
    )
    p.add_argument("workdir", help="workspace to run the agent in and checkpoint in")
    p.add_argument("prompt_file", help="file with the original objective")
    p.add_argument("--port", type=int, required=True, choices=sorted(PORT_MODELS),
                   help="loopback endpoint; selects the matching single-slot model")
    p.add_argument("--slices", type=int, default=4,
                   help="TOTAL cumulative slices across controller restarts")
    p.add_argument("--turns", type=int, default=12, help="per-slice --max-turns bound")
    p.add_argument("--verify-file", required=True,
                   help="Python acceptance script executed in workdir after each slice")
    p.add_argument("--profile", default=DEFAULT_PROFILE)
    p.add_argument("--cli", default=DEFAULT_CLI, help="path to the hermes executable")
    args = p.parse_args(argv)
    if args.slices < 1:
        p.error("--slices must be >= 1")
    if args.turns < 1:
        p.error("--turns must be >= 1")
    return args


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_command(args, prompt_path, resume_id=None):
    cmd = [
        args.cli, "-p", args.profile, "chat", "--cli",
        "--provider", "custom",
        "--base-url", f"http://127.0.0.1:{args.port}/v1",
        "--model", PORT_MODELS[args.port],
        "--reasoning", "none",
        "--in", str(args.workdir),
        "--query-file", str(prompt_path),
        "--oneshot", "--max-turns", str(args.turns),
        "--format", "stream-json",
    ]
    if resume_id is not None:
        # Gateway resumes retain launch policy; do not send creation overrides.
        cmd = [args.cli, "-p", args.profile, "chat", "--cli", "--in", str(args.workdir),
               "--query-file", str(prompt_path), "--oneshot", "--format", "stream-json",
               "--resume", resume_id]
    return cmd


def parse_result_event(stdout_path):
    """Return the stream-json result event, or None. Last one wins if repeated."""
    found = None
    try:
        with open(stdout_path, "r", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(event, dict) and event.get("type") == "result":
                    found = event
    except FileNotFoundError:
        return None
    return found


def read_stderr_tail(path, limit=2000):
    try:
        with open(path, "r", errors="replace") as fh:
            return fh.read()[-limit:]
    except FileNotFoundError:
        return ""


def continuation_prompt(original, slice_no, failures, prior_exit):
    """Continuation prompt: unchanged original objective plus acceptance failures."""
    return (
        "Continuing the same session after slice "
        f"{slice_no}. The original objective is unchanged and must be re-satisfied:\n"
        f"{original}\nAcceptance failures: {failures!r}\n"
        f"The acceptance gate rejected the work after slice {slice_no} "
        f"(verify exit {prior_exit}; see verify.log tail).\n"
        "Fix the remaining acceptance failures in this workspace. Do not claim "
        "completion without re-running acceptance; keep evidence in files.\n"
    )


def new_checkpoint(args, prompt_hash):
    return {
        "schema": "dr100.contain-worker.v1",
        "workdir": str(args.workdir),
        "port": args.port,
        "model": PORT_MODELS[args.port],
        "prompt_hash": prompt_hash,
        "profile": args.profile,
        "turns_per_slice": args.turns,
        "slices_budget": args.slices,
        "slices_used": 0,
        "session_id": None,
        "technical_status": "UNTESTED",
        "review_state": "pending",
        "review_verdicts": ["approval", "approval-with-changes", "disapproval"],
        "continue_reason": None,
        "error": None,
        "failures": [],
        "updated_at": None,
        "events": [],
    }


def bind_checkpoint(args, prompt_hash):
    """Load the atomic checkpoint and reject port/prompt mismatch; else fresh."""
    path = os.path.join(args.workdir, CHECKPOINT_NAME)
    if not os.path.exists(path):
        return new_checkpoint(args, prompt_hash), False
    try:
        with open(path, "r", errors="replace") as fh:
            ckpt = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"refusing to bind unreadable checkpoint {path}: {exc}")
    if ckpt.get("port") != args.port:
        raise SystemExit(
            f"checkpoint port mismatch: checkpoint={ckpt.get('port')} arg={args.port}; "
            "refusing to resume another workspace's session"
        )
    if ckpt.get("prompt_hash") != prompt_hash:
        raise SystemExit(
            "checkpoint prompt hash mismatch; objective changed since the checkpoint "
            f"({ckpt.get('prompt_hash')} != {prompt_hash}); refusing"
        )
    if ckpt.get("profile") != args.profile:
        raise SystemExit("checkpoint profile mismatch; refusing")
    ckpt["slices_budget"] = args.slices
    if ckpt.get("turns_per_slice") != args.turns:
        raise SystemExit("checkpoint turns mismatch; resume preserves launch policy")
    return ckpt, True


def write_atomic(path, payload):
    payload["updated_at"] = time.time()
    directory = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".ckpt.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(payload, fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def acquire_flock(workdir):
    """Exclusive per-workspace lock; returns an open fd held by the caller."""
    lock_path = os.path.join(workdir, "continue-worker.lock")
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        raise SystemExit(f"workspace {workdir} is already owned by a continue-worker")
    return fd


def run_slice(args, prompt_path, resume_id, slice_no):
    """Run one hermes slice; returns dict(result event or None, exit_code, timeout)."""
    stdout_path = os.path.join(args.workdir, f"slice-{slice_no}-stdout.jsonl")
    stderr_path = os.path.join(args.workdir, f"slice-{slice_no}-stderr.log")
    cmd = build_command(args, prompt_path, resume_id)
    with open(stdout_path, "w") as out, open(stderr_path, "w") as err:
        proc = subprocess.Popen(cmd, stdout=out, stderr=err, start_new_session=True)
        timed_out = False
        try:
            proc.wait(timeout=SUB_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
    return {
        "exit_code": proc.returncode,
        "timed_out": timed_out,
        "stdout": stdout_path,
        "stderr": stderr_path,
        "result": parse_result_event(stdout_path),
    }


def run_verify(args):
    """Acceptance gate in the workdir; returns exit code, -1 if the run blew up."""
    try:
        proc = subprocess.run(
            [sys.executable, args.verify_file],
            cwd=args.workdir, capture_output=True, text=True, timeout=SUB_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return -1, "acceptance script timed out"
    except OSError as exc:
        return -1, f"acceptance script unrunnable: {exc}"
    log_path = os.path.join(args.workdir, "verify.log")
    with open(log_path, "w") as log:
        log.write(proc.stdout or "")
        log.write("\n-- stderr --\n")
        log.write(proc.stderr or "")
    return proc.returncode, (proc.stderr or proc.stdout or "")[-2000:]


def loop(args, ckpt, prompt_original):
    """Slice loop; returns the final technical status."""
    if ckpt["technical_status"] in ("FAILED", "IN_FLIGHT"):
        return "FAILED"
    if ckpt["technical_status"] == "VERIFIED":
        code, _ = run_verify(args)
        if code == 0:
            return "VERIFIED"
        ckpt["technical_status"] = "PARTIAL"
    while ckpt["slices_used"] < ckpt["slices_budget"]:
        slice_no = ckpt["slices_used"] + 1
        if ckpt["session_id"] is None:
            prompt_path = args.prompt_file
        else:
            prompt_text = continuation_prompt(
                prompt_original, slice_no, ckpt["failures"],
                ckpt.get("last_verify_exit"))
            prompt_path = os.path.join(args.workdir, f"prompt-slice-{slice_no}.txt")
            with open(prompt_path, "w") as fh:
                fh.write(prompt_text)
            write_atomic(os.path.join(args.workdir, CONTINUATION_STATE),
                         {"slice": slice_no, "prompt": prompt_text})

        ckpt["technical_status"] = "IN_FLIGHT"
        write_atomic(os.path.join(args.workdir, CHECKPOINT_NAME), ckpt)
        slice_res = run_slice(args, prompt_path, ckpt["session_id"], slice_no)
        ckpt["slices_used"] = slice_no
        event = slice_res["result"]

        if slice_res["timed_out"]:
            ckpt["technical_status"] = "FAILED"
            ckpt["continue_reason"] = "subprocess_timeout_180s"
            ckpt["error"] = "hermes slice exceeded the 180 s bound and was terminated"
            write_atomic(os.path.join(args.workdir, CHECKPOINT_NAME), ckpt)
            return "FAILED"
        if event is None or not event.get("session_id"):
            ckpt["technical_status"] = "FAILED"
            ckpt["continue_reason"] = "no_result_event"
            ckpt["error"] = ("stream-json result event with session_id missing; "
                             "exit code is never substituted for success: "
                             + read_stderr_tail(slice_res["stderr"]))
            write_atomic(os.path.join(args.workdir, CHECKPOINT_NAME), ckpt)
            return "FAILED"

        ckpt["session_id"] = event["session_id"]
        if event.get("error") or slice_res["exit_code"] not in (0, 1):
            ckpt["technical_status"] = "FAILED"
            ckpt["error"] = event.get("error") or "CLI failure"
            write_atomic(os.path.join(args.workdir, CHECKPOINT_NAME), ckpt)
            return "FAILED"
        if RESULT_TURN_RE.search(json.dumps(event)):
            ckpt["events"].append({"slice": slice_no, "observed": "turn_limit_hint"})

        verify_exit, verify_tail = run_verify(args)
        ckpt["last_verify_exit"] = verify_exit
        ckpt["events"].append({"slice": slice_no, "verify_exit": verify_exit,
                               "hermes_exit": slice_res["exit_code"]})
        if verify_exit == 0:
            ckpt["technical_status"] = "VERIFIED"
            ckpt["review_state"] = "pending"  # automation must not create an approval
            ckpt["continue_reason"] = None
            ckpt["failures"] = []
            write_atomic(os.path.join(args.workdir, CHECKPOINT_NAME), ckpt)
            return "VERIFIED"
        if verify_exit < 0:
            ckpt["technical_status"] = "FAILED"
            ckpt["continue_reason"] = "acceptance_unrunnable"
            ckpt["error"] = verify_tail
            write_atomic(os.path.join(args.workdir, CHECKPOINT_NAME), ckpt)
            return "FAILED"

        ckpt["technical_status"] = "PARTIAL"
        ckpt["continue_reason"] = "acceptance_rejected_resume_same_session"
        ckpt["failures"] = [verify_tail]
        write_atomic(os.path.join(args.workdir, CHECKPOINT_NAME), ckpt)

    ckpt["technical_status"] = "PARTIAL"
    ckpt["continue_reason"] = "slice_budget_exhausted"
    write_atomic(os.path.join(args.workdir, CHECKPOINT_NAME), ckpt)
    return "PARTIAL"


def main(argv=None):
    args = parse_args(argv)
    workdir = os.path.abspath(args.workdir)
    if not os.path.isdir(workdir):
        raise SystemExit(f"workdir does not exist: {workdir}")
    if not os.path.isfile(args.prompt_file):
        raise SystemExit(f"prompt file not found: {args.prompt_file}")
    if not os.path.isfile(args.verify_file):
        raise SystemExit(f"verify file not found: {args.verify_file}")
    args.workdir = workdir
    args.prompt_file = os.path.abspath(args.prompt_file)
    args.verify_file = os.path.abspath(args.verify_file)
    with open(args.prompt_file, "r", errors="replace") as f:
        prompt_original = f.read()
    prompt_hash = sha256_file(args.prompt_file) + ":" + sha256_file(args.verify_file)

    lock_fd = acquire_flock(workdir)
    try:
        ckpt, resumed = bind_checkpoint(args, prompt_hash)
        status = loop(args, ckpt, prompt_original)
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)

    print(json.dumps({
        "technical_status": status,
        "review_state": "pending",
        "slices_used": ckpt["slices_used"],
        "slices_budget": ckpt["slices_budget"],
        "session_id": ckpt["session_id"],
        "continue_reason": ckpt["continue_reason"],
        "checkpoint": os.path.join(workdir, CHECKPOINT_NAME),
        "resumed_controller": resumed,
    }, indent=2))
    return 0 if status == "VERIFIED" else 1


if __name__ == "__main__":
    sys.exit(main())

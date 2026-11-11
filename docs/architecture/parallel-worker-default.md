# Dedicated parallel engineering default

Source of truth: `configs/parallel-engineering.json`, implemented by `scripts/codebreaker/parallel_engineering.py` plus the PR #8 continuation controller. This is separate from production Kanban; `max_in_progress=1` remains unchanged. No model reload, duplicate service, provider fallback, or extra Supervisor profile is installed.

## Topology and activation

One Codex SOL supervisor, medium reasoning. Four persistent logical identities: w1/w2 use gyro-coder-l-gpu0 on 8082; w3/w4 use gyro-coder-l-gpu1 on 8083. Each model service retains one 65,536-token slot. Loopback proxies on 18082/18083 hold a FIFO gate for each full streamed inference response; they release it before tools execute. Four agent lifecycles can be active while only two generations execute. The three shared tool queues build/test/analysis admit one command each, with initial thread limits 8/6/6. These are environment workload hints, not hard CPU quotas; no affinity is applied. Only builds take the per-build-workspace lock; analysis and tests can overlap independent builds.

```
scripts/codebreaker/install-parallel.sh
sol-engineering                         # sole Codex SOL supervisor, medium
sol-engineering status
sol-engineering run /absolute/manifest.json
sol-engineering cpu build --cwd /absolute/worktree -- cmake --build build --parallel 8
sol-engineering cpu test --cwd /absolute/worktree -- python3 -m unittest discover
sol-engineering cpu analysis --cwd /absolute/worktree -- python3 audit.py
```

Installation backs up existing invocation/config links, then installs `~/.local/bin/sol-engineering` and `~/.config/sol-engineering/default.json` references to this checkout. Existing Codex configuration already selects gpt-6.1-sol and medium; the dedicated invocation supplies both explicitly using supported CLI overrides ([official configuration reference](https://learn.chatgpt.com/docs/config-file/config-sample)). It reuses the existing Codex identity and the existing Hermes worker profile. The primary `hermes-supervisor` profile is not edited. New terminals, controller restarts and reboots retain the configuration and logical registry. Models remain subject to existing service startup policies; no new systemd unit is created. The controller reports degraded when resource/endpoint gates fail.

## Tasks and scheduling

Manifest JSON contains `tasks` with id, worker, workspace, prompt_file, verify_file and depends_on; `cpu_jobs` contain id, queue, cwd, command array and depends_on. All paths should be absolute. Use separate Git worktrees or isolated repositories for edits, and keep acceptance scripts outside worker workspaces. Worker IDs and task IDs are distinct; each active worker owns one lifecycle and one explicit session. New tasks may reuse a logical identity after the preceding task is dispositioned. No workers may share a mutable workspace. Queue length is bounded at 32. Missing dependencies, cycles, duplicate IDs/workers/workspaces fail before dispatch. Ready DAG nodes dispatch without waiting for blocked nodes; futures notify completion. Dependents require approved engineering deliverables, or completed CPU jobs. A ready task waiting for human review is not accepted and cannot unblock dependents.

Inference preflight requires healthy existing endpoints, one slot each, at least 1,024 MiB free VRAM/GPU, and 8 GiB MemAvailable. CPU tasks use bounded subprocess groups, preserve stdout/stderr/status, and share OS scheduling. Cache reuse is requested with `cache_prompt=true`; actual cached token counts, prompt/decode timings, exact rendered-template tokens, queue wait and HTTP statuses are logged. No cache effectiveness is inferred from configuration alone. Existing KV cache types Q8_0/Q8_0 and batch/ubatch 4096/512 are preserved.

## Adaptive context

Routine tasks receive the smallest relevant source/interface/history bundle selected by SOL, with at least 12,000 tokens reserved for generation and tools. The capacity is 65,536; the 48,000–52,000 initial target belongs only to the explicitly requested stress test. Required material must never be silently truncated. Tokenize the actual template, record high-water marks, and checkpoint/compact before overflow. Acceptance criteria and source hashes persist across compaction.

## Checkpoint, recovery and review

Private state is under `~/.local/state/sol-parallel/`: controller.json, events.jsonl, telemetry.jsonl, tasks and CPU logs. Each isolated workspace retains PR #8 atomic continuation checkpoints, explicit session ID, objective/acceptance hashes, slice history, acceptance errors and implementation digest. Twelve turns are a segment limit, not task lifetime. Session policy is retained on native resumes. Repeated unchanged implementation stops for diagnosis after two nonproductive repeats. CPU commands and inference have deadlines; only controller-owned process groups may be terminated. Gateway work that outlives a viewer is a recovery concern: do not assume killing a CLI cancelled its gateway session. Inspect the explicit session before recovery, and never terminate the shared gateway/model runtime.

A restart skips completed work; in-flight controller records become recovery_required instead of launching duplicates. Failed/in-flight continuation checkpoints stop for inspection. Preserve partial source, checkpoints and logs. Do not erase checkpoints to make a run look fresh. Context near the limit uses existing Hermes compaction plus durable acceptance and objective state; any lost required context is a failure, not permission to silently omit it.

SOL reviews source/diff, acceptance criteria, test logs, limitations and checkpoint history. Tests yield pending_review. Exact dispositions:

```
sol-engineering review TASK_ID APPROVED
sol-engineering review TASK_ID 'APPROVED WITH CHANGES' --feedback-file /absolute/feedback.txt
sol-engineering review TASK_ID 'DISAPPROVED — REWORK REQUIRED' --feedback-file /absolute/feedback.txt
```

Changes/rework preserve the originating worker/session and implementation, append feedback, reset technical continuation to PARTIAL, and make it ready for correction on the next manifest dispatch. SOL must review the corrected deliverable again. These commands record the supervisor's actual decision; they never manufacture automatic approval. Production deployment, trading and release holds still apply.

## Reproducible acceptance

Run `python3 -m unittest discover -s scripts/codebreaker -p 'test_*.py'`. `scripts/codebreaker/acceptance/prepare.py` builds four independent meaningful Python utility tasks from unique real standard-library/controller sources, sizes each against the actual Hermes chat template, and creates a timestamped isolated manifest with unique task IDs. It refuses to overwrite an existing run ID; use `--run-id NAME` for an explicit new experiment. First run `python3 scripts/codebreaker/acceptance/calibrate.py` to capture a private request template through an intentional HTTP rejection with no inference. Then run `python3 scripts/codebreaker/acceptance/prepare.py`; the captured system/tool context stays private. The committed verification describes the exact tested revision and results. Run the integrated manifest only once per explicitly authorized acceptance experiment; review corrections continue the same tasks rather than restarting the benchmark. Historical benchmarks remain intact. The prior 106.06-second clamp run used shorter prompts and simpler tasks, so it is not a controlled speedup baseline.

### Tested recovery refinement

The stress test exposed two harness defects: reinjecting the entire original 50K bundle on continuation produced rejected 102K–105K requests; executing an external acceptance file without adding the worker directory to Python's import path imported task namespace directories instead of modules. Both are fixed. Large continuations now retain a concise objective and a hashed reference to the complete original source file; acceptance runs explicitly import the isolated workspace. Failed checkpoint snapshots and all source/history are retained. After a settled harness failure, `sol-engineering recover TASK_ID` independently reruns acceptance and records recovery evidence before returning the task to pending review. This command refuses running tasks. It does not turn test success into approval.

On controller restart, approved/pending-review tasks revalidate acceptance without launching a worker. Objective/acceptance hash changes fail closed. The final request admission guard refuses oversized initial prompts (12K reserve) and later conversations (4K reserve) rather than silently truncating; generation is bounded to remaining capacity. The full stress test was not restarted after this repair. The guard has a deterministic streaming-HTTP regression test; real same-session correction runs demonstrate bounded, smaller continuations. Do not infer arbitrary semantic preservation from compaction alone: the tested guarantee is preserved objective/source files, hashes, implementation, session affinity and passing independent acceptance for these four tasks.

New task dispatches include the shared CPU execution and review policy in a durable dispatch prompt. Existing task checkpoints keep their original prompt binding. Initial thread limits are environment/workload controls for cooperating tools, not CPU affinity or hard cgroup quotas. Uncooperative commands can exceed thread hints and require explicit workload tuning. No new background service is installed.

See [stress-test results](../../benchmarks/parallel-default-2026-11-07/REPORT.md), [machine-readable metrics](../../benchmarks/parallel-default-2026-11-07/metrics.json), and [SOL review history](../../benchmarks/parallel-default-2026-11-07/review.json).

The checked-in `acceptance/report.py` aggregates the original named acceptance packet; its fixed historical paths intentionally refer to this test, not every future controller task. Native event/telemetry and task records remain available for later independent measurements.

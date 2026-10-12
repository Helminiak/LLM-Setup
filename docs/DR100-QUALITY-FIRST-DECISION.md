# DR100 Decision: Correctness before throughput (2026-10-12)

**Decision status:** Engineering policy documented; no model/provider settings changed. This does not clear any DR100 gate or WP002 HOLD.

## Goal and priorities

1. **Correct implementation against explicit requirements and acceptance tests.**
2. **Reproducible evidence:** source commit, test commands/results, logs, model/driver/context/quantization/config fingerprint, and reviewer findings preserved in GitHub.
3. **Recoverability:** one controlled work package at a time, limited retries, explicit blockers and rollback.
4. **Resource/cost efficiency:** use local RTX 5090 for bounded coding/analysis first when it meets the quality bar; escalate to a capable alternative for difficult or failing work.
5. **Speed/GPU utilization** are secondary metrics, never release criteria.

## Model routing principles

- **Local candidate:** Installed Qwen Coder390 Q6_K, 80K context, maximum GPU offload; latest LM Studio authentication and transport benchmark passed. The benchmark measured only response generation (not code correctness). Do not infer correctness from 96.7 token/s or high VRAM use.
- **Cloud alternative:** GPT-6.1 SOL, or another manually approved model from already configured Hermes providers. This can be a separate reviewer or escalation worker.
- **Choice of topology remains open** until a controlled tool-use/repository edit test: (A) cloud planner with delegated local coder, or (B) local first with independent cloud review. The interactive Hermes `/model` picker changes the **current session's main provider**, not child delegation assignments. Switching should not silently modify engineering policy or a release gate.
- **Automatic provider fallback handles transport/API errors** (429/5xx/401/etc.) but is **not** a substitute for reviewing failed tests or wrong code. A coding-quality failure should trigger a recorded corrective iteration or explicit independent review, not an unrecorded model swap.
- **No unrestricted retry loops**: on a repeated failed unit test or a repeated identical unproductive patch, stop, preserve work and test evidence, and request alternative review or owner direction.
- **CPU RAM offload** is an option for fitting a model that demonstrably improves correctness, but is not by itself a quality gain. Document context/precision tradeoff and test on the same work packages.

## Minimum real acceptance evaluation

Select one small, representative DR100 issue or Bookmap exporter task with an executable test. Freeze baseline and references. Have the local candidate read files, propose and implement a bounded change, run the **real test suite**, and publish a summary including changed-file list, exact commands, exit codes, counts of tests passed/failed, and limitation notes. Repeat with an alternate model only on the same frozen input/acceptance criteria (no cherry-picked easy cases). Use independent review to catch fabricated test claims, unsafe changes, regressions and missing cases.

Scoring rubric: requirements met (45%), tests/regression impact (30%), tool-use/evidence integrity (15%), maintainability/review findings (10%). These percentages are initial evaluation weights, **not measured model scores**. Do not auto-merge or alter protected gates based on score alone.

## Existing measurable baseline

LM Studio report: [80K Q6_K PASS 20261012T193411462196Z](https://github.com/Helminiak/knowledge-base/blob/main/reports/lmstudio/20261012T193411462196Z.json). Tests were API smoke/engineering text output, **not** actual code edits or test suite executions. GPU about 30 GiB allocated with 1.6 GiB free; additional allocation is not a goal.

## References

- Hermes model picker: https://hermes-agent.nousresearch.com/docs/reference/cli-commands
- Hermes provider and LM Studio integration: https://hermes-agent.nousresearch.com/docs/integrations/providers
- Hermes automatic fallback semantics: https://hermes-agent.nousresearch.com/docs/user-guide/features/fallback-providers

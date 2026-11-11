# Llamactl Control Center — durable worker checkpoint

**Status:** NOT_STARTED (plan published; no implementation performed by this GitHub task)
**Active phase:** P0 — audit/recovery
**Execution owner:** Local worker on 5090FE
**Last updated:** 2026-11-10
**Master issue:** https://github.com/Helminiak/LLM-Setup/issues/10
**Runbook:** [README](../docs/llamactl-control-center/README.md)

## Prior observations (UNVERIFIED until locally rechecked)
- Llamactl v0.23.0 web dashboard was accessible at `127.0.0.1:19090`.
- The Models view showed two validation-cache entries rather than expected local GGUF inventory.
- Earlier Claude repair reported launcher wrapper/icon fixed, but GUI window visibility unverified.
- Earlier report said Llamactl registered zero instances; independent llama-server processes existed on ports 8082/8091 at that time.
- Model files may exist under `/mnt/llm`, `~/models`, and other configured locations. Do not infer an authoritative inventory from these clues.

## Verified current system facts
None yet.

## Phase checkpoint
- Current issue: https://github.com/Helminiak/LLM-Setup/issues/11
- Goal: Establish read-only baseline and previous work inventory.
- Done: None.
- Acceptance: UNVERIFIED.
- Blocking decision: None.
- Next exact action: Read P0 issue; verify local identity, service/API health, working tree, live inference processes, storage mounts and launcher paths.

## Files/commits changed
Planning files only; local runtime and model weights untouched.

## Evidence references
Add concise test evidence or GitHub issue comment links here; do not paste raw secrets or private paths.

## Claude escalations
None.

## Resumption procedure
1. Read runbook, this state file, and active issue only.
2. Revalidate live state before actions.
3. Continue from 'Next exact action'; update this file and the issue before compaction or stopping.

# DR100 incident — Hermes exits immediately after startup banner (2026-10-12)

**Disposition:** Launcher fault, correction committed; workstation retest pending.

## Observed event

User screencast (11 seconds, inspected locally; not uploaded because it contains desktop/session details) shows launcher `DR100 v1.0.4` printing **Result: PASS**, uploading its sanitized report and then printing "Starting existing Hermes without editing its configuration." Hermes starts, displays its banner with existing `hermes-supervisor` profile and `codex app-server` runtime, then immediately displays **Goodbye!** and returns to the Ubuntu shell. No LLM request, delegation, tool execution, or Kanban task was observed.

Sanitized device/configuration report: [20261012T193824813625Z](https://github.com/Helminiak/knowledge-base/blob/main/reports/lmstudio/20261012T193824813625Z.json). Identical model fingerprint reused from the prior PASS benchmark: Q6_K, active context 80,000 tokens, Flash Attention ON, KV offload ON, ~1,662 MiB GPU free, localhost authenticated API PASS. The report does **not** test Hermes's interactive stdin.

## Root cause

In [loader v1.0.4](../scripts/dr100-hermes-start-v1.0.4.sh), the entire Python program is invoked as:

```sh
python3 - "$@" <<'PY'
```

Within the Python block, successful verification led to `os.execvp("hermes", ["hermes"])`. `execvp` replaces the running Python process but **does not reset file descriptor 0** (stdin). This descriptor is still connected to the Bash heredoc feeding the Python program, already at end-of-file. Hermes is interactive and promptly exits after reading EOF. No model or Hermes configuration change is warranted.

## Correction

[Launcher v1.0.5](../scripts/dr100-hermes-start-v1.0.5.sh) removes Python-to-Hermes `execvp`. Python finishes model verification and returns exit status to Bash. Bash's `set -e` ensures failed verification blocks startup. Bash then handles `--setup-only`, requires a terminal and launches:

```sh
exec hermes </dev/tty
```

This reconnects Hermes's stdin explicitly to the controlling terminal. It uses the pre-existing Hermes profile and makes no modifications to Hermes configuration, model, Kanban, DR100 issue state, or cloud routing. Old launcher files remain as immutable version history.

## User run command

```bash
curl -fLsS https://raw.githubusercontent.com/Helminiak/LLM-Setup/main/scripts/dr100-hermes-start-v1.0.5.sh -o ~/Downloads/dr100-hermes-start-v1.0.5.sh && bash ~/Downloads/dr100-hermes-start-v1.0.5.sh
```

**Acceptance, still pending:** Hermes startup banner persists with a working prompt and responds to `/help`; no immediate "Goodbye!" on startup. Then perform controlled G2 local worker/tool test separately under existing DR100 authority; never infer G2 acceptance or WP002 release from launcher success.

## Root-cause boundary

The fault concerns CLI interactive standard input, **not** a GPU failure, a failed LM Studio load, a model context-size mismatch, or an inference exception. Additional Hermes delegation, compressor, idle-loop, and WP002 defects remain distinct and unverified.


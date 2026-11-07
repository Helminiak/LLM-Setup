# Existing Supervisor restoration

Use `python3 scripts/codebreaker/repair-supervisor.py` to back up and migrate stale inference routes in the existing `hermes-supervisor` profile to GYRO GPU 0 (8082). GPU 1 remains at 8083. Requires PyYAML. The script preserves the profile's skills, memory routing, review instructions, approval controls, and production Kanban configuration. Backups are private under `~/.local/state/sol-restoration/backup-*`; restore with `cp -p <backup>/config.yaml ~/.hermes/profiles/hermes-supervisor/config.yaml` at a safe session boundary. No running session is restarted.

The Codebreaker launcher checks both existing single-slot 65,536-context servers and Hindsight before opening the existing Supervisor. It never starts the retired combined `gyro-l` server. The 1,024 MiB free-memory check is a startup reserve, not a request for additional GPU slots. Four-worker verification uses four separate workspaces, with two queued callers per GPU. This proves concurrent agent execution, not four simultaneous inference slots or full-context capacity.

Run `python3 scripts/codebreaker/verify-four-workers.py` for a bounded real-agent coding test with independent clamp correctness checks. Private raw logs and summary live under `~/.local/state/sol-restoration/four-workers/`. Do not publish retrieved memory or raw profile/session data.

Hermes 0.23.0+508.g8153953 and Codex 0.162.1 were inspected using actual CLI help. Hermes's gateway rejects `--run-budget` despite advertising it; continuation must not depend on this flag. Existing `--max-turns 12` is a per-slice bound, not a task completion allowance. A zero process exit never substitutes for acceptance tests or SOL review.

The existing SOL persona and approval, approval-with-changes, and disapproval protocol remain authoritative. Automation must not create an approval. A verified technical result remains pending SOL review; changes/disapproval require correction under the existing escalation limits. No production Kanban concurrency or dispatcher changes are part of this workflow.

For an existing installation, back up the installed launcher with `cp -p ~/.local/bin/codebreaker-launch <private-backup>` and install the repository launcher with `install -m 0755 scripts/codebreaker/codebreaker-launch.sh ~/.local/bin/codebreaker-launch`. The installer is intended for new installations and refuses existing launchers or mismatched worker profiles. Use the explicit repair script for the existing Supervisor; do not run the installer as a migration command.

Checkpoint continuation:

```
python3 scripts/codebreaker/continue-worker.py /absolute/workspace /absolute/objective.txt \
  --port 8082 --turns 12 --slices 4 --verify-file /absolute/acceptance.py
```

Keep the acceptance script outside the agent workspace. Its exit status gates technical completion. The checkpoint binds the objective and acceptance script hashes, profile, port, and turn policy. Failed acceptance resumes the explicit saved session; it never resumes `latest`. Restart the same command with a higher cumulative `--slices` budget to continue a PARTIAL task. CLI errors, timeouts, and interrupted in-flight slices stop for inspection. A VERIFIED restart reruns acceptance without another model call. Review remains pending; SOL's established review protocol is unchanged. Resume omits model/turn creation overrides because the gateway retains them from launch.

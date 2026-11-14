# Dual-worker rollback (operator supervised)
1. Interrupt only maintenance-owned worker sessions with `hc interrupt <recorded terminal>`; verify they are idle. Preserve outputs and session IDs.
2. Confirm backend /slots idle and no live claims. Never interrupt production or unrelated work.
3. Restore backed-up gyro-worker-1/2 config.yaml files from before/files/home/joe/.hermes/profiles/. Do not restore/delete session databases or history.
4. If inference change fails, restore before/files/home/joe/.config/llama-swap/config.yaml to ~/.config/llama-swap/config.yaml. Use the supported llama-swap single-model unload/load controls only for ready-gyro-l-abl after idle/ownership checks; no shared service restart. Verify original /running identity, /props total_slots=1 and /slots n_ctx=131072. Configuration watcher may reload the backend automatically; observe before acting.
5. Leave kanban.dispatch_in_gateway=false. No board/runs/claims are modified by this maintenance; compare supported CLI show/runs snapshots. Keep gateway running.
Original hashes, listeners, process/service state and resident identity are in before/. Service units have not been modified.

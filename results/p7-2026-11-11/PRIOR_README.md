# P7 paired P4b residency runner

The runner supports a lease-owning mode and a client-only attach mode. The active P4b-protected holder remains authoritative for lease renewal, config, model residency, and cleanup. Client attach reads holder state and writes only a separate client result and evidence directory.

The runner executes the 12 frozen P7 tasks plus the already frozen P4 `merge_intervals` and `parse_records` tasks: 14 tasks, seeds 42/43/44, for each member of the P4b pair. Both candidates receive each task/seed concurrently through the llama-swap gateway, keeping the comparison under dual-residency contention. All three attempts run, even after an earlier pass. No prompt tuning or between-attempt feedback is sent.

## Frozen inputs and identity pins

- P7 suite files stay at `/home/joe/.local/state/inference-research/p7-19-2026-11-11/p7_suite/` and are read-only inputs. The runner pins the current v2 manifest SHA `f705357888003fe37a1d6794857ccae9c55ad57efaab48b6344c9a018104c5f6`, then verifies `tasks.json`, `reference.py`, `validate.py`, and `README.md` against the hashes declared in that manifest. Task prompt/spec checks use the v2 manifest entries.
- P4 task artifacts are read-only inputs: `p4_runner.py` `7120da691a71dbd1b90709f51a2416a54e2773d192b489fd1f72992e6ef738a1`, merge oracle `oracle_reference.py` `e05f5fe05b01c309fba5b7aacb2654e5694ba508baab622f5b50574e1d8f8886`, parser spec `heldout_parse_spec.txt` `c8e6b751b4268c9b8dad6fca683045796d71ba3e6cb75fcba26a43f29cc41730`, and parser oracle `heldout_parse_reference.py` `72071bd8461f0093cbb5e19e02b1976a4822661fdc9e4642607e39785a3e1911`.
- Exact P4 task prompt hashes: merge `4a17910b4513d9b7ee63b8104f09fa39838eb3875866d23d594bc7528a5b2bf1`; parse `a186adad033e8b260216c3dd6c6ba28403eb04f9bfac0618d2e2ed3c944bde6a`. The prefill prompt is also extracted from the pinned P4 runner and checked against `a1e01c6d58a6a6f83a20b208ea5f2059652b1b2ac37fabb4bfc25269841c337d`.
- Candidate SHA, path, route alias, GPU, and port are pinned to P4b: Qwen3.8-27B Q6 (`qwen3.8-27b-q6`, `c9c206812fbe4ac7b76a729e25928b63f2ae89d37f69da7a71c20aec763cd436`) on GPU 0 / UUID `GPU-4c61ea28-b74b-9144-cbab-76ed4b4721ae` / `:8086`; Qwen3.6-35B Q5 (`qwen3.6-35b-q5`, `c13ce26253ea334df472bd8fbd2d6da66d8a41195c17f6fcbf44c4d20ece0932`) on GPU 1 / UUID `GPU-395e0f7a-0ab8-9b1c-46a6-17ad4e293bc1` / `:8087`. Both use context 98,304.
- The P4b helper is pinned to `8284b9c1df0ae9638f8a446b91b3062586440945f56d54324cc8d537fc2d48a0`. The runner calls its `refuse_existing_claim()` while holding the shared lease lock. That helper is the only code path that may archive the existing released claim; a live, malformed, not-clean, or archive-conflict claim blocks the run.

## Lease, config, and residency safeguards

Preflight verifies the exact P7/P4/P4b hashes, both model file hashes, P4b config backup, active config hash, protected systemd services and listeners, candidate ports, GPU index-to-UUID mapping, and the per-GPU fit estimate. It checks the 1,024 MiB free-memory floor. The P4b config transformation is built in memory during preflight and its reviewed staged SHA is checked; the active config is not touched until the later exact GO token.

After GO, the runner creates a unique backup under the P7 directory and verifies it byte-for-byte against the active P4b baseline. It stages and validates the same dual-residency routes as P4b, then replaces the active config only if its hash still equals the backup. The initial GO window is 1,800 seconds; renewals begin only after exact GO, then occur every 1,500 seconds, 300 seconds before expiry, through the P4 claim writer. The monitor checks GPU floor, service and protected-port state, backend process identity, and per-process GPU UUID attribution throughout the run and cleanup.

Backend identity is discovered from the exact alias/model-path/executable process, its own loopback socket, `/health`, `/props`, and direct `/v1/models`. Benchmark requests go through `http://127.0.0.1:8080`; direct backend endpoints are used only for identity checks. A gateway/backend collision, unexpected PID, wrong model path, alias, listener, or GPU attribution blocks acceptance.

P4's fixed archive-note prefill prompt runs concurrently on both candidates and must report at least 1,000 prompt tokens per candidate. The runner records context, prompt/completion token counts, client TTFT, generation/decode timing, backend timings when present, raw SSE, per-GPU memory before/peak/minimum/after, and P4b per-process GPU memory attribution. It does not infer pure model initialization time from request-to-ready time.

Task 12 runs as actual function tool calls, with a fresh `reference.simulate_order_calls` state for every candidate attempt. Each exact returned tool result is serialized and fed back in the matching `tool` message. The v2 suite validator covers 23 invalid/incomplete call sequences and transcript checks. Client attach currently excludes this task, along with v2 task 11.

Generated Python source is executed only inside bubblewrap with all namespaces unshared, network disabled, read-only system/oracle inputs, and a temporary writable `/tmp`. The runner preserves exact response SSE, visible output, reasoning output, extracted source, sandbox stdout/stderr, tool trace, and failing input under the unique evidence directory. The P4 reference oracles determine acceptance; there is no model judge.

Every attempt records task/candidate/seed, prompt and output hashes, UTC start/end, wall time, generation time, TTFT, decode rate, oracle identity, failure class, exact-input hash, and evidence path. Per task/candidate summaries include pass@1, pass@3, first accepted attempt, cumulative time through first acceptance, failed-first-attempt penalty, and right-censoring when all attempts fail. Effective time to an accepted result is the cumulative wall/generation time through that first independent pass. All three attempts still run.

Cleanup unloads only an alias whose live PID, exact model path, executable, socket, and alias match the frozen P4b identity. It verifies the PID exits and the gateway reports unloaded. The runner restores its config backup only when the active file still has the exact staged SHA; if another writer changed it, the runner preserves that file and marks cleanup failed. It then verifies the original config hash, protected services/ports, both candidate ports empty, no candidate process, and the lease release. P4 and P4b artifacts/backups are not overwritten.

Results are written to `/home/joe/.local/state/inference-research/p7-19-2026-11-11/result.json`; raw evidence is in the adjacent lease-specific evidence directory.

## Invocation modes

### Read-only client attach

Use client attach when a separately owned holder is already `RESIDENT`:

```sh
.herdr/project-exec "hc run --bg --outlive-parent --name p7-client --cwd /home/joe/.local/state/inference-research/p7-19-2026-11-11 python3 p7_runner.py --attach-resident <LEASE_ID> --tasks merge_intervals,parse_records"
```

Attach requires the exact live `RESIDENT` lease ID, the holder's live PID/start ticks/boot ID, the active config and staged config hashes, both model artifact hashes, each exact backend PID/path/executable/socket plus read-only `/health`, `/props`, and `/v1/models` identity, and per-GPU PID attribution. Requests go directly to those resident backend endpoints so llama-swap cannot load a model on behalf of the client. `--tasks` accepts only `merge_intervals` and `parse_records` (or either one individually); it deliberately excludes v2 tasks 11 and 12. Attach never acquires the lease lock, changes the claim/config, renews the holder lease, or performs unload, restore, or cleanup. It writes `attach-result-<lease>-<run>.json` and a separate `attach-evidence-<lease>-<run>/` directory.

### Lease-owning run

After owner review, launch from the Mac with the workspace wrapper:

```sh
.herdr/project-exec "hc run --bg --outlive-parent --name p7-runner --cwd /home/joe/.local/state/inference-research/p7-19-2026-11-11 python3 p7_runner.py"
```

Confirm the returned target is `5090fe/p7-runner` and that stdin remains persistent. The runner prints a unique lease ID and `WAITING_GO` token. Only after that confirmation, the owner can authorize the config stage/model loads by sending the exact token:

```sh
hc send 5090fe/p7-runner "GO winter lease=<printed-lease-id>"
```

Do not substitute another lease ID or send GO before confirming the terminal target. No launch, GO, model load/unload, active config edit, lease archival, GPU query, or inference API request was performed while adding client attach support.

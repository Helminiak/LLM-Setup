# Tiel Coder / Qwen Turbo MTP evaluation — 2026-11-22

## Decision

BLOCKED FROM PROMOTION: ranking is correctness-first. The current Qwen3.8-27B Q6 number-three reference scored 6/8 (0.75), Qwen Turbo scored 5/8 (0.625), and Tiel scored 4/8 (0.50). Neither candidate qualified, so neither was optimized or integrated into llama-swap.

The earlier rejection of Qwen Turbo was speed/short-round based and is superseded by this quality gate: it passed the frozen `safe_join` task in the full round, but still ranked below the reference. Tiel’s earlier two-task smoke was insufficient; the full quality round found failures in JSON Pointer, safe_join, pack_batches, and aggregate_logs.

## Evidence

- [model-inventory.json](model-inventory.json) records exact local sizes, SHA-256 matches to Hugging Face LFS OIDs, revisions, projector provenance, and update/security notices.
- [benchmark-summary.json](benchmark-summary.json) records the unchanged suite tasks, exclusions, identical generation budget, scores, and per-task results.
- [vision-tests.json](vision-tests.json) and [smoke-tests.json](smoke-tests.json) record direct engine and vision results.
- [llama-swap-diagnostics.md](llama-swap-diagnostics.md) records the validated unchanged installation.

## Separate performance/context measurements

Measured, not ranking criteria: Tiel without MTP was ~217 tok/s on a short coding request; Tiel with embedded MTP reached ~318 tok/s with 170/203 draft tokens accepted (83.7%). Qwen Turbo was ~48.5 tok/s; q27b reference was ~62.4 tok/s. Peak observed test residency was approximately Tiel 21.5/20.1 GiB and Qwen 16.5/16.9 GiB across GPUs; idle was restored afterward. Context allocation 65,536 was near-full validated at 60,311 prompt tokens; 131,072 was near-full validated at 120,307 prompt tokens with all three sentinels retrieved and a bounded merge task correct. Recommended operating context is 131,072 for Tiel under the tested q8 K/V, full offload, flash attention, and MTP settings; these context claims are measured for Tiel only and do not imply promotion.

Advertised model context and upstream update state are not used as ranking evidence. The exact upstream repository identities for the local q27b and q35/gyro top-three files were not recorded in the current source-of-truth branch, so full current-HF update comparison for those references is UNVERIFIED rather than inferred; the new-model repositories and revisions are recorded.

## Runtime outcome

No new llama-swap entries were added. Existing valid registrations were preserved, configuration validation passed, and no model remained resident after testing. There are no exact selection commands for the rejected aliases; use the existing documented aliases only.

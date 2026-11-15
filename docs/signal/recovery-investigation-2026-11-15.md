# Signal AP-IQ4_XS recovery investigation — 2026-11-15

## Result

**Replacement required; no repair performed.** The quarantined file was not modified or deleted.

Pinned revision: `c01924df1459d6c201fd6d61560432712448f6a6`
Publisher LFS SHA-256: `7fadb6b29035377204aed0d0085d3f58cc65fc7b4c3aa79f8f3f84fdfc304529`
Quarantined local SHA-256: `0d0da433bc1920eb6669ec6d945fe2efff1156d44aa2941d58a93a45a14da869`
Both files are exactly `90447294816` bytes.

## Transfer/cache investigation

- Revision-specific resolve headers reported the pinned commit, `x-linked-size=90447294816`, LFS OID `7fadb6b29035377204aed0d0085d3f58cc65fc7b4c3aa79f8f3f84fdfc304529`, and Xet ETag `3a06cceb386b0b489e670a0a41aebfb2815c1ff8f7e8c5e76934c0d6fc4ccbb8`.
- The Hugging Face API returned the same revision, LFS OID, size, Xet hash, and blob oid `31af870db7f212b77da693e536efc52c9c284c66`.
- Local Xet logs contained no Signal/AP-IQ4_XS entry, failed transfer, or recoverable incomplete cache object. Existing logs document unrelated reconstructions.
- The quarantined file is a normal 75-extent regular file. `filefrag` showed no filesystem error; recent kernel error/warning inspection showed no relevant storage error.
- HTTP range requests support `206 Content-Range`. Five 1-MiB samples at offsets 0, 1 MiB, 1 GiB, 42.0 GiB, and EOF-1 MiB matched upstream byte-for-byte. A second bounded sweep of 32 evenly distributed one-MiB samples also matched.

The samples show the file is structurally close to the pinned upstream object but do not prove full-file equality. The full SHA-256 mismatch is decisive; no safe patch map can be derived without hashing the complete upstream object. The file cannot be repaired through a verified range patch or cache resume.

## Recovery method requiring approval

Preserve the quarantined file. After approval, download the exact pinned resolve URL using a resume-capable official HF client or `curl --continue-at -` into a new destination, never over the quarantine. Verify byte count and full SHA-256 against the pinned LFS OID before admission. No model loading is authorized by this report.

Available space: `478G`; sufficient for one replacement copy, but not permission to start it.

## Resource assessment

- RAM: 61 GiB total, 41 GiB available.
- Swap: `/swap.img`, 16 GiB total, 15.3 GiB used, 735 MiB free.
- Three one-second `/proc/vmstat` samples were stable at `pswpin=7282260`, `pswpout=13608037`; no active swap movement was observed during the sample. Large swap occupancy remains a load risk.
- Largest observed process: `llama-server`, approximately 3.2 GiB RSS.
- Both RTX 5090s had approximately 32.1 GiB free and 0% utilization.
- A 128K run requires the approximately 84.2 GiB quantized weights plus runtime allocations and KV cache; two 32 GiB GPUs cannot hold the weights alone. CPU/system RAM backing and swap-free headroom are required. Exact split depends on loader overhead and KV type; no load was attempted.

Production routes, DR100, llama-swap configuration, and the quarantine were unchanged. No new 84.2 GiB transfer or model loading was started.

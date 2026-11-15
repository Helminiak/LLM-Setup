# Signal AP-IQ4_XS integrity/admission evidence — 2026-11-15

Artifact: `Signal-3.8-Flash-Next-AP-IQ4_XS.gguf`
Pinned revision: `c01924df1459d6c201fd6d61560432712448f6a6`

## Integrity

- Expected/publisher size: `90447294816` bytes
- Local quarantined artifact size: `90447294816` bytes
- Revision-specific Hugging Face LFS OID (SHA-256): `7fadb6b29035377204aed0d0085d3f58cc65fc7b4c3aa79f8f3f84fdfc304529`
- Local independently computed SHA-256: `0d0da433bc1920eb6669ec6d945fe2efff1156d44aa2941d58a93a45a14da869`
- Result: **FAIL** — exact-size file does not match the pinned revision's LFS SHA-256.
- Xet hash is separately recorded by HF and was not used as the SHA-256 comparison.

The original file was quarantined without deletion at:
`/home/joe/models/signal/quarantine-20261115-verified-lfs-mismatch/`

No replacement download was started. Available filesystem space before any replacement: `478G`.

## Offline GGUF inspection

- Magic/version: `GGUF`, version 3
- Tensor count: `1224`
- Metadata entries: `70`
- Architecture: `qwen4exp`
- Model name: `Signal 3.8 Flash Next`
- Size label: `512x56B`
- Context metadata: `262144`
- Experts: `512` total, `10` used
- Quantization metadata: file type `25`, quantization version `2`
- Embedded key: `tokenizer.chat_template`

No inference or model launch was performed.

## Security review

Hugging Face reports `securityFileStatus.status=safe` and JFrog reports `Safe GGUF model`; Protect AI reports `PAIT-GGUF-100`. The GGUF contains a Jinja chat template with normal rendering constructs and `raise_exception` validation branches, including tool-call formatting. Offline inspection found no executable payload or network/process primitive in the metadata. This is an informational/admission risk requiring a sandboxed/approved template renderer; it is not evidence of malicious behavior in the artifact. Because integrity failed, no runtime template test was performed.

## Host/resource checks

- Available RAM: `41Gi`
- Swap: `15.3Gi/16Gi` used, `735Mi` free
- `/swap.img` is the active swap device
- `/proc/vmstat` samples were stable during a 3-second observation: `pswpin=7282260`, `pswpout=13608037`
- Largest observed process: `llama-server`, approximately `3.2GiB` RSS
- GPU0/GPU1: approximately `32.1GiB` free each, 0% utilization
- Research endpoint `127.0.0.1:8080/health`: `OK`

The swap occupancy is not currently showing active swap-in/out in the short sample, and no `swapoff`, service restart, or model-server change was attempted. The large occupied swap remains a resource risk for a new ~84GiB artifact/runtime and requires longer observation/approval before loading.

## Admission outcome

**BLOCKED.** Do not register, load, benchmark, or route Signal until a replacement download is explicitly approved and verified against the pinned LFS OID. Existing llama-swap configuration, entries, routes, and backup were not changed.

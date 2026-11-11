# P2 local model inventory — manifest schema and scan contract

Companion code: `scripts/llamactl-control-center/inventory.py`
Fixture tests: `scripts/llamactl-control-center/test_inventory.py`

## Scan contract (acceptance gate)

| Property | How it is enforced |
| --- | --- |
| No downloads | stdlib only (`argparse`, `hashlib`, `json`, `os`, `re`, `struct`); no network import |
| No relocation | files are opened read-only (`"rb"`, `os.lstat`, `os.scandir`); no write, move, rename or delete call exists |
| No writes inside a scanned root | `--output` is rejected (exit 2) when the path equals or sits under any root |
| Bounded work | per-root `max_depth`; GGUF **header only** is parsed; arrays are summarized (count + first element), long strings are replaced by length + hash id |
| No full hashing of large files | identity is `head_sha256_1MiB` (first 1 MiB only) |
| Deterministic | `--stable` omits timestamps; artifacts are sorted by `(root, location, id)`; ids derive from `(root, relative location, size)` |
| Symlink / bind handling | each physical file (identified by `realpath`) is claimed **once**; the claim goes to the most model-like path by rank: GGUF split shard > GGUF > HF snapshot path > HF `blobs` path > other root. Same-directory aliases, cross-directory model→blob links and symlinked roots (e.g. `~/models -> /mnt/llm/models`) all collapse to one artifact |
| Variants are not duplicates | duplicate flag requires identical `size_bytes` **and** identical 1 MiB head hash |

Manifests are generated outside the repository (`~/.hermes/.../cache/scratch/llamactl-p2/`)
and are **not** committed: they contain absolute host paths and internal cache layout.

## Manifest fields

```
schema_version        string   "1.0"
generated_at_utc      string   present unless --stable
scan_policy           object   read_only, writes_inside_roots, head_hash_bytes, downloads, relocations
roots[]               object   id, path, max_depth
counts                object   artifacts, gguf_artifacts, gguf_files, gguf_split_sets,
                               incomplete_split_sets, hf_snapshot_dirs, safetensors_dirs,
                               runnable_llms, sidecar_or_projector_only, duplicate_pairs,
                               symlink_aliases_collapsed, by_kind, by_state, total_bytes
duplicates[]          object   artifact_id, duplicate_of
warnings[]            string   absent roots, unreadable headers/configs
artifacts[]           object   one logical model (split sets are merged into one artifact)
```

### Artifact fields

| Field | Meaning |
| --- | --- |
| `id` | stable sha1 of `(root, relative location, total size)` |
| `kind` | `gguf`, `gguf_split_set`, `safetensors_dir`, `hf_snapshot` |
| `name`, `family` | `general.name` from GGUF metadata (or repo/dir name), plus a normalized family tag |
| `format`, `quantization`, `gguf_file_type_enum` | GGUF container plus `general.quantization_type` (fallback: filename quant pattern) |
| `architecture` | `general.architecture` or the first architecture key seen |
| `root`, `location` | scanned root id and **relative** location inside it |
| `paths`, `size_bytes`, `files`, `declared_shards` | concrete members of the logical artifact |
| `split` | `{declared_shards, present_shards, missing_indices, contiguous}` for split sets |
| `identity` | `head_sha256_1MiB`, `n_tensors`, `n_kv`, `gguf_version`, or HF weight-file/symlink table |
| `metadata` | curated GGUF KV subset (shape, tokenizer, adapter); arrays appear as `{count, elem_type, first}` |
| `capabilities` | `runnable_llm`, `has_tokenizer`, `has_vocab`, `sidecar_or_projector_only`, `embedding_or_reranker` |
| `backend_compatibility` | `llama_cpp`, `vllm`, `mlx`, `onnx` — only asserted from observed evidence |
| `dependencies` | `base_model`, `projector`, `tokenizer_present`, `missing_split_shards`, `missing` |
| `state` | `running`, `configured`, `unconfigured`, `incomplete`, `unsupported` (see below) |
| `duplicate_of` | present only when an identical artifact was already recorded |

## State definitions

- `running` — the artifact (or one of its split shards) is the `--model` of a live llama.cpp/vLLM process.
- `configured` — referenced by Llamactl config or reported by the Llamactl models API.
- `unconfigured` — present locally, complete, but not referenced by any launcher or service.
- `incomplete` — missing split shards, tokenizer/vocab absent, projector/adapter-only file, or unreadable metadata.
- `unsupported` — present but not launchable by the installed backends (for example an ONNX-only
  embedding/reranker model where only llama.cpp-style backends exist).

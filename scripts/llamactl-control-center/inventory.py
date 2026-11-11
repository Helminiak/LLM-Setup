#!/usr/bin/env python3
"""Read-only local model inventory for the Llamactl Control Center (phase P2).

Deterministic. No writes inside any scanned root, no downloads, no relocation,
no full hashing of large files (a 1 MiB head hash is used as the identity).
Symlink aliases (HF cache blobs, Xet links) are resolved once and never counted
twice; quantization variants are never treated as duplicates.

Usage:
  inventory.py [--root id=path ...] [--references FILE] [--running PATH,...]
               [--output FILE] [--stable] [--summary]
Defaults are the model roots verified on 5090FE during P0/P1.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import struct
import sys

SCHEMA_VERSION = "1.0"
HEAD_HASH_BYTES = 1 << 20  # 1 MiB only
SKIP_DIRS = {".locks", ".no_exist", "xet", "logs", "staging"}

# Verified on 5090FE (P0/P1). /mnt/llm is scanned shallowly to prove it holds
# no model artifacts.
DEFAULT_ROOTS = [
    ("home_models", 5, os.path.expanduser("~/models")),
    ("lmstudio_models", 4, os.path.expanduser("~/.lmstudio/models")),
    ("hf_hub_cache", 6, os.path.expanduser("~/.cache/huggingface/hub")),
    ("mnt_llm", 2, "/mnt/llm"),
]

SPLIT_RE = re.compile(r"^(?P<stem>.+)-(?P<index>\d{5})-of-(?P<total>\d{5})\.gguf$")
QUANT_RE = re.compile(
    r"(IQ\d_[A-Z]+|IQ\d(?:_NL)?|TQ\d_[0-9]|Q\d_K(?:_[SML])?|Q\d_[0-9]|Q[4-9]_0|BF16|F16|F32)",
    re.I,
)
SNAP_RE = re.compile(r"/models--(?P<repo>[^/]+)--(?P<name>[^/]+)/snapshots/(?P<rev>[0-9a-f]{40})"
                     r"(?P<rest>/.*)?$")
# Weight files may sit in snapshot subdirectories (onnx/, references/), so a file
# belongs to the snapshot root, not to its immediate parent directory.
TOKENIZER_NAME_RE = re.compile(r"(^|/)(tokenizer|vocab|special_tokens|sentencepiece|spm)|\.bpe\.model$")

# GGUF value types (ggml-org gguf_spec): FLOAT32=6, BOOL=7, STRING=8, ARRAY=9,
# UINT64=10, INT64=11, FLOAT64=12.
T_UINT8, T_INT8, T_UINT16, T_INT16, T_UINT32, T_INT32 = 0, 1, 2, 3, 4, 5
T_FLOAT32, T_BOOL, T_STRING, T_ARRAY = 6, 7, 8, 9
T_UINT64, T_INT64, T_FLOAT64 = 10, 11, 12
_SCALAR = {
    T_UINT8: "B", T_INT8: "b", T_UINT16: "H", T_INT16: "h",
    T_UINT32: "I", T_INT32: "i", T_FLOAT32: "f", T_BOOL: "?",
    T_UINT64: "Q", T_INT64: "q", T_FLOAT64: "d",
}

KEEP_EXACT = {
    "general.name", "general.architecture", "general.type", "general.quantization_type",
    "general.file_type", "general.description", "general.language", "general.adapter_type",
}
KEEP_SUFFIX = (
    ".architecture", ".context_length", ".block_count", ".embedding_length",
    ".feed_forward_length", ".attention.head_count", ".attention.head_count_kv",
    ".rope.freq_base", ".tokenizer.ggml.model", ".tokenizer.ggml.pre",
    ".tokenizer.ggml.token_type_count", ".vocab.type", ".adapter.type",
    "tokenizer.ggml.model", "tokenizer.chat_template", ".tokenizer.ggml.eos_token_id",
    ".mtp.enabled", ".lora.version", ".projector.type",
)
ARCH_HINT_RE = re.compile(r"^(?P<arch>[a-z0-9_]+)\.(architecture|tokenizer|context_length|block_count)\b")


class TruncatedGGUF(Exception):
    pass


MAX_FIELD_BYTES = 8 << 20
MAX_ARRAY_ELEMS = 1 << 20
MIN_TENSORS_PER_BLOCK = 4  # a complete transformer needs >=4 tensors per declared block


def _read_exact(fh, n, path):
    if n > MAX_FIELD_BYTES:
        raise TruncatedGGUF(f"{path}: implausible field length {n} (header desync)")
    data = fh.read(n)
    if len(data) != n:
        raise TruncatedGGUF(f"{path}: expected {n} bytes, got {len(data)}")
    return data


def _read_value(fh, vtype, path, key, char_limit):
    """Return (recorded_value, keep). Long values are summarized, never dumped."""
    if vtype in _SCALAR:
        fmt = "<" + _SCALAR[vtype]
        raw = struct.unpack(fmt, _read_exact(fh, struct.calcsize(fmt), path))[0]
        return (bool(raw) if vtype == T_BOOL else raw), True
    if vtype == T_STRING:
        slen = struct.unpack("<Q", _read_exact(fh, 8, path))[0]
        raw = _read_exact(fh, slen, path).decode("utf-8", "replace")
        keep = key in KEEP_EXACT or key.endswith(KEEP_SUFFIX)
        if len(raw) > char_limit:
            return {"len": slen, "sha256": hashlib.sha256(raw.encode()).hexdigest()[:16]}, keep
        return raw, keep
    if vtype == T_ARRAY:
        elem = struct.unpack("<I", _read_exact(fh, 4, path))[0]
        count = struct.unpack("<Q", _read_exact(fh, 8, path))[0]
        first = None
        if elem in _SCALAR:
            size = struct.calcsize(_SCALAR[elem])
            if count:
                first = struct.unpack("<" + _SCALAR[elem], _read_exact(fh, size, path))[0]
            if count > 1:
                fh.seek(size * (count - 1), 1)
        elif count > MAX_ARRAY_ELEMS:
            raise TruncatedGGUF(f"{path}: array {key} claims {count} elements")
        else:
            for i in range(count):
                v, _ = _read_value(fh, elem, path, f"{key}[{i}]", char_limit)
                if i == 0:
                    first = v
        keep = (key.endswith(".tokens") or key.endswith(".scores")
                or key.endswith(".token_type") or key in KEEP_EXACT
                or key.endswith(KEEP_SUFFIX))
        return {"count": count, "elem_type": elem, "first": first}, keep
    raise TruncatedGGUF(f"{path}: unknown GGUF value type {vtype} for key {key}")


def parse_gguf_header(path, kv_value_char_limit=200):
    """Parse only the GGUF header/KV block. Returns None when not a GGUF."""
    out: dict = {"magic_ok": False}
    try:
        with open(path, "rb") as fh:
            if _read_exact(fh, 4, path) != b"GGUF":
                return None
            out["magic_ok"] = True
            out["version"] = struct.unpack("<I", _read_exact(fh, 4, path))[0]
            out["n_tensors"] = struct.unpack("<Q", _read_exact(fh, 8, path))[0]
            n_kv = struct.unpack("<Q", _read_exact(fh, 8, path))[0]
            kv, archs = {}, set()
            for _ in range(n_kv):
                klen = struct.unpack("<Q", _read_exact(fh, 8, path))[0]
                key = _read_exact(fh, klen, path).decode("utf-8", "replace")
                vtype = struct.unpack("<I", _read_exact(fh, 4, path))[0]
                value, keep = _read_value(fh, vtype, path, key, kv_value_char_limit)
                m = ARCH_HINT_RE.match(key)
                if m:
                    archs.add(m.group("arch"))
                if keep:
                    kv[key] = value
            out["n_kv"] = n_kv
            out["kv"] = kv
            out["architectures"] = sorted(archs)
            return out
    except (OSError, TruncatedGGUF, struct.error) as exc:
        out["error"] = str(exc)
        return out


def head_sha256(path, nbytes=HEAD_HASH_BYTES):
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            h.update(fh.read(nbytes))
        return h.hexdigest()
    except OSError:
        return None


def short_id(*parts):
    return hashlib.sha1("\0".join(str(p) for p in parts).encode()).hexdigest()[:12]


def scan_files(root, max_depth):
    """Bounded walk. Returns (regular_files, symlinks). Nothing is followed into
    another filesystem and nothing is written."""
    root = os.path.abspath(root)
    base_depth = root.rstrip("/").count("/")
    regular, links = [], []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        depth = dirpath.rstrip("/").count("/") - base_depth
        if depth >= max_depth:
            dirnames[:] = []
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            try:
                st = os.lstat(full)
            except OSError:
                continue
            if os.path.islink(full):
                try:
                    rst = os.stat(full)
                    entry = {"path": full, "name": name, "size": rst.st_size,
                             "is_symlink": True, "link_target": os.path.realpath(full)}
                except OSError:
                    entry = {"path": full, "name": name, "size": 0,
                             "is_symlink": True, "link_target": None}
                links.append(entry)
            else:
                regular.append({"path": full, "name": name, "size": st.st_size,
                                "is_symlink": False, "link_target": None})
    regular.sort(key=lambda f: f["path"])
    links.sort(key=lambda f: f["path"])
    return regular, links


def _family(name):
    m = re.search(r"(Qwen[0-9.]+[A-Za-z.]*|flint|MiniLM|multilingual-e5)", name or "", re.I)
    return m.group(1) if m else None


def _gguf_artifact(root_id, rel, files, declared_shards, missing, warnings):
    paths = [f["path"] for f in files]
    primary = files[0]
    total_size = sum(f["size"] for f in files)
    header = parse_gguf_header(primary["path"])
    kv = (header or {}).get("kv", {})
    archs = (header or {}).get("architectures", [])
    arch = kv.get("general.architecture") or (archs[0] if archs else None)
    name = kv.get("general.name") or os.path.splitext(primary["name"])[0]
    quant = kv.get("general.quantization_type")
    if not quant:
        m = QUANT_RE.search(primary["name"])
        quant = m.group(0) if m else None
    keys = set(kv)
    # llama.cpp writes tokenizer keys both prefixed ("<arch>.tokenizer.ggml.tokens")
    # and bare ("tokenizer.ggml.tokens"); match the trailing path, not the prefix.
    tok_tokens = [k for k in keys if k.endswith("tokenizer.ggml.tokens")
                  or k.endswith("tokenizer.ggml.vocabulary")]
    tok_meta = [k for k in keys if "tokenizer.ggml." in k or k.endswith("tokenizer.chat_template")]
    has_vocab = bool(tok_tokens)
    has_tokenizer = has_vocab or any(k.endswith("tokenizer.ggml.model")
                                     or k.endswith("tokenizer.chat_template") for k in keys)
    vocab_size = None
    for k in tok_tokens:
        v = kv.get(k)
        if isinstance(v, dict) and isinstance(v.get("count"), int):
            vocab_size = v["count"]
            break
    chat_template = next((k for k in keys if k.endswith("tokenizer.chat_template")), None)
    sidecar_keys = sorted(k for k in keys
                          if k.startswith(("clip.", "audio.", "projector.")) or "mmproj" in k)
    is_sidecar = bool(sidecar_keys) and not has_tokenizer
    block_count = next((v for k, v in kv.items() if k.endswith(".block_count")), None)
    n_tensors = (header or {}).get("n_tensors")
    # A file that declares N transformer blocks but carries far fewer tensors cannot
    # hold that model: nextn/MTP and per-layer-embedding exports (here bakeoff/flash-sidecar/
    # mtp-*.gguf and gyro-coder-l/*-PLE-*.gguf) are modules loaded together with a base
    # model, not standalone runnable LLMs.
    is_module = bool(isinstance(block_count, int) and block_count > 0
                     and isinstance(n_tensors, int) and 0 < n_tensors < block_count * MIN_TENSORS_PER_BLOCK)
    is_sidecar = is_sidecar or is_module
    runnable = bool(arch) and has_vocab and has_tokenizer and not is_module

    state = "unconfigured"
    deps = {"base_model": None, "projector": None, "tokenizer_present": has_tokenizer,
            "missing_split_shards": missing or []}
    if header is None or not header.get("magic_ok"):
        state = "incomplete"
        deps["missing"] = ["GGUF header unreadable"]
        warnings.append(f"GGUF header unreadable: {primary['path']}")
    elif missing:
        state = "incomplete"
    elif is_sidecar and is_module:
        state = "incomplete"
        deps["base_model"] = (f"module export: {n_tensors} tensors against declared "
                              f"block_count {block_count}; load with the base model")
        deps["missing"] = [f"transformer block tensors ({n_tensors} tensors for "
                           f"{block_count} declared blocks)"]
    elif is_sidecar:
        state = "incomplete"
        deps["projector"] = "projector/adapter-only GGUF; needs a base model GGUF"
    elif not (has_vocab and has_tokenizer):
        state = "incomplete"
        deps["missing"] = ["tokenizer/vocab absent from GGUF metadata"]

    art = {
        "id": short_id(root_id, rel, total_size),
        "kind": "gguf",
        "name": name,
        "family": _family(name),
        "format": "GGUF",
        "quantization": quant,
        "gguf_file_type_enum": kv.get("general.file_type"),
        "architecture": arch,
        "root": root_id,
        "location": rel,
        "paths": paths,
        "size_bytes": total_size,
        "files": len(files),
        "declared_shards": declared_shards,
        "identity": {"head_sha256_1MiB": head_sha256(primary["path"]),
                     "n_tensors": (header or {}).get("n_tensors"),
                     "n_kv": (header or {}).get("n_kv"),
                     "gguf_version": (header or {}).get("version")},
        # array values were summarized during parsing (counts, not payloads)
        "metadata": {k: kv[k] for k in sorted(kv)},
        "capabilities": {"runnable_llm": runnable, "has_tokenizer": has_tokenizer,
                         "has_vocab": has_vocab, "vocab_size": vocab_size,
                         "chat_template_key": chat_template,
                         "tokenizer_keys": sorted(tok_meta)[:8],
                         "sidecar_or_projector_only": is_sidecar,
                         "sidecar_keys": sidecar_keys[:6],
                         "module_export": is_module,
                         "n_tensors": n_tensors, "block_count": block_count},
        "backend_compatibility": {"llama_cpp": bool(arch) and not is_sidecar,
                                  "vllm": False, "mlx": False, "onnx": False},
        "dependencies": deps,
        "state": state,
    }
    if missing is not None:
        art["split"] = {"declared_shards": declared_shards, "present_shards": len(files),
                        "missing_indices": missing,
                        "contiguous": not missing}
    return art


def gguf_entries(root_id, root, files, warnings):
    """Group GGUF files into single files and split sets."""
    singles, sets = [], {}
    for f in files:
        if not f["name"].lower().endswith(".gguf"):
            continue
        rel = os.path.relpath(f["path"], root)
        m = SPLIT_RE.match(f["name"])
        if m:
            key = (os.path.dirname(f["path"]), m.group("stem"))
            s = sets.setdefault(key, {
                "shards": {}, "total": int(m.group("total")), "root_id": root_id,
                "rel": os.path.join(os.path.dirname(rel), m.group("stem")) + ".gguf"})
            s["shards"][int(m.group("index"))] = f
        else:
            singles.append((root_id, rel, f))

    artifacts = [_gguf_artifact(r, rel, [f], 1, None, warnings) for r, rel, f in singles]
    for (_, _), s in sorted(sets.items()):
        have = s["shards"]
        missing = [i for i in range(1, s["total"] + 1) if i not in have]
        shards = [have[i] for i in sorted(have)]
        art = _gguf_artifact(s["root_id"], s["rel"], shards, s["total"], missing, warnings)
        art["kind"] = "gguf_split_set"
        artifacts.append(art)
    return artifacts


def _task_of(archs, model_type, directory):
    joined = " ".join(list(archs) + [model_type or "", os.path.basename(directory)]).lower()
    if any(a.lower().startswith(("bert", "roberta")) for a in archs) or "bert" in joined:
        if "marco" in joined or "cross-encoder" in joined or "rerank" in joined:
            return "reranking"
        return "embedding"
    if "e5" in joined or "embedding" in joined:
        return "embedding"
    if any(a.lower().startswith(("qwen", "llama", "mistral", "gemma")) for a in archs):
        return "generative"
    return "unknown"


def _read_config(directory, warnings):
    cfg_path = os.path.join(directory, "config.json")
    if not os.path.isfile(cfg_path):
        return {}
    try:
        with open(cfg_path, "rb") as fh:
            return json.loads(fh.read(65536).decode("utf-8", "replace"))
    except (OSError, ValueError) as exc:
        warnings.append(f"config.json unreadable in {directory}: {exc}")
        return {}


def _hf_dir_artifact(root_id, root, directory, cfg, weight_files, kind, warnings, display_name=None):
    archs = cfg.get("architectures") or []
    model_type = cfg.get("model_type")
    name = display_name or os.path.basename(directory)
    task = _task_of(archs, model_type, name)
    weights = sorted(weight_files, key=lambda f: f["path"])
    total = sum(f["size"] for f in weights)
    tokenizer_files = []
    try:
        with os.scandir(directory) as it:
            for e in sorted(it, key=lambda x: x.name):
                if e.is_file() and (e.name.startswith(("tokenizer", "vocab", "special_tokens",
                                                       "sentencepiece")) or e.name.endswith(".model")):
                    tokenizer_files.append(e.name)
    except OSError:
        pass
    state = "unconfigured"
    deps = {"base_model": None, "projector": None, "tokenizer_present": bool(tokenizer_files),
            "missing_split_shards": []}
    if not weights:
        state = "incomplete"
        deps["missing"] = ["weight file absent from this directory"]
    elif task in ("embedding", "reranking"):
        state = "unsupported"  # llama-cpp / vllm / mlx expose no embedding/reranker route here
    return {
        "id": short_id(root_id, os.path.relpath(directory, root), total),
        "kind": kind,
        "name": name,
        "family": _family(name),
        "format": "safetensors" if kind == "safetensors" else "hf_snapshot",
        "quantization": None,
        "architecture": (archs[0] if archs else model_type),
        "root": root_id,
        "location": os.path.relpath(directory, root),
        "paths": [f["path"] for f in weights],
        "size_bytes": total,
        "files": len(weights),
        "declared_shards": None,
        "identity": {"weight_files": [{"name": f["name"], "size": f["size"],
                                       "symlink_to": f["link_target"]} for f in weights],
                     "symlink_count": sum(1 for f in weights if f["is_symlink"])},
        "metadata": {"config_json_keys": sorted(cfg)[:20], "model_type": model_type,
                     "task": task, "tokenizer_files": tokenizer_files[:8]},
        "capabilities": {"runnable_llm": False, "embedding_or_reranker": task in ("embedding", "reranking")},
        "backend_compatibility": {"llama_cpp": False, "vllm": False, "mlx": False,
                                  "onnx": task in ("embedding", "reranking")},
        "dependencies": deps,
        "state": state,
    }


def safetensors_entries(root_id, root, files, warnings):
    dirs = {}
    for f in files:
        if f["name"].endswith(".safetensors"):
            dirs.setdefault(os.path.dirname(f["path"]), []).append(f)
    return [_hf_dir_artifact(root_id, root, d, _read_config(d, warnings), w,
                             "safetensors", warnings) for d, w in sorted(dirs.items())]


def _snapshot_root(path):
    """(snapshot dir, repo, revision) for a path inside an HF snapshot tree."""
    m = SNAP_RE.search(path)
    if not m:
        return None
    head = path[:m.start() + 1]
    snap = f"{head}/models--{m.group('repo')}--{m.group('name')}/snapshots/{m.group('rev')}"
    return snap, f"{m.group('repo')}/{m.group('name')}", m.group("rev")


def hf_snapshot_entries(root_id, root, files, links, warnings):
    by_dir, repos = {}, {}
    for f in links + files:
        got = _snapshot_root(f["path"])
        if not got:
            continue
        snap, repo, rev = got
        by_dir.setdefault(snap, []).append(f)
        repos[snap] = repo
    out = []
    for directory, entries in sorted(by_dir.items()):
        repo = repos[directory]
        weights = [f for f in entries
                   if f["name"].endswith((".safetensors", ".onnx", ".bin", ".gguf", ".pt"))
                   or (f["name"].endswith(".model") and not TOKENIZER_NAME_RE.search(f["name"]))]
        art = _hf_dir_artifact(root_id, root, directory, _read_config(directory, warnings),
                               weights, "hf_snapshot", warnings, display_name=repo)
        art["repo"] = repo
        art["revision"] = _snapshot_root(directory)[2]
        art["capabilities"]["runnable_llm"] = False
        art["backend_compatibility"]["onnx"] = any(f["name"].endswith(".onnx") for f in weights)
        out.append(art)
    return out


def _model_stems(paths):
    """Real paths plus split-set stems, so a shard matches its logical model."""
    out = set()
    for p in paths:
        rp = os.path.realpath(p)
        out.add(rp)
        m = SPLIT_RE.match(os.path.basename(rp))
        if m:
            out.add(os.path.join(os.path.dirname(rp), m.group("stem") + ".gguf"))
    return out


def mark_states(artifacts, running, referenced):
    run_stems, ref_stems = _model_stems(running), _model_stems(referenced)
    for a in artifacts:
        if a["state"] in ("incomplete", "unsupported"):
            continue
        stems = _model_stems(a["paths"])
        if stems & run_stems:
            a["state"] = "running"
        elif stems & ref_stems:
            a["state"] = "configured"


def mark_duplicates(artifacts):
    seen, dupes = {}, []
    for a in sorted(artifacts, key=lambda x: (x["size_bytes"], x["id"])):
        head = (a.get("identity") or {}).get("head_sha256_1MiB")
        if head is None:
            continue
        key = (a["size_bytes"], head)
        if key in seen:
            a["duplicate_of"] = seen[key]
            dupes.append((a["id"], seen[key]))
        else:
            seen[key] = a["id"]
    return dupes


def build(roots, references, running, stable=False, warnings=None):
    warnings = warnings if warnings is not None else []
    artifacts = []
    alias_count = 0
    cross_root_count = 0
    # Roots on this host overlap through symlinks (~/models -> /mnt/llm/models,
    # ~/.cache -> /mnt/llm/.cache), so every attributed file is claimed by its
    # realpath: a file is counted once, under the first root that reaches it.
    claimed = set()
    for root_id, depth, root in roots:
        if not os.path.isdir(root):
            warnings.append(f"root absent, skipped: {root}")
            continue
        regular, links = scan_files(root, depth)
        # A symlink whose target is enumerated in the same walk is an alias, not a
        # second artifact. Same-directory alias -> keep the real file. Cross-directory
        # link (HF cache blob layout) -> keep the model-directory link and drop the
        # blob, so the weight is attributed to the model that actually uses it.
        enumerated = {f["path"] for f in regular}
        blob_targets, kept_links = set(), []
        for l in links:
            t = l["link_target"]
            if t and t in enumerated:
                alias_count += 1
                if os.path.dirname(l["path"]) == os.path.dirname(t):
                    continue
                blob_targets.add(t)
                kept_links.append(l)
            else:
                kept_links.append(l)
        candidates = [f for f in regular if f["path"] not in blob_targets] + kept_links
        # Claim order matters when several paths reach the same bytes: a HF snapshot
        # entry (the model directory the tool actually reads) claims the bytes before
        # the blob-store alias symlink in blobs/ does. Deterministic ranking, not walk order.
        def claim_rank(f):
            if _snapshot_root(f["path"]):
                return (0, f["path"])
            if f.get("is_symlink"):
                return (2, f["path"])
            return (1, f["path"])
        candidates.sort(key=claim_rank)
        model_files = []
        for f in candidates:
            real = os.path.realpath(f["path"])
            if real in claimed:
                cross_root_count += 1
                continue
            claimed.add(real)
            model_files.append(f)
        artifacts += gguf_entries(root_id, root, model_files, warnings)
        artifacts += safetensors_entries(root_id, root, model_files, warnings)
        artifacts += hf_snapshot_entries(root_id, root, model_files, [], warnings)
    artifacts.sort(key=lambda a: (a["root"], a["location"], a["id"]))
    duplicates = mark_duplicates(artifacts)
    mark_states(artifacts, running, references)

    by_kind, by_state = {}, {}
    for a in artifacts:
        by_kind[a["kind"]] = by_kind.get(a["kind"], 0) + 1
        by_state[a["state"]] = by_state.get(a["state"], 0) + 1
    gguf_arts = [a for a in artifacts if a["kind"].startswith("gguf")]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "scan_policy": {"read_only": True, "writes_inside_roots": 0,
                        "head_hash_bytes": HEAD_HASH_BYTES,
                        "dedupe_key": "realpath per file; (size, head_sha256_1MiB) per artifact",
                        "downloads": 0, "relocations": 0},
        "roots": [{"id": r[0], "max_depth": r[1], "path": r[2]} for r in roots],
        "counts": {
            "artifacts": len(artifacts),
            "gguf_artifacts": len(gguf_arts),
            "gguf_files": sum(a["files"] for a in gguf_arts),
            "gguf_split_sets": sum(1 for a in gguf_arts if a["kind"] == "gguf_split_set"),
            "incomplete_split_sets": sum(1 for a in gguf_arts
                                         if a.get("split") and a["split"]["missing_indices"]),
            "hf_snapshot_dirs": sum(1 for a in artifacts if a["kind"] == "hf_snapshot"),
            "safetensors_dirs": sum(1 for a in artifacts if a["kind"] == "safetensors"),
            "runnable_llms": sum(1 for a in artifacts
                                 if a["capabilities"].get("runnable_llm")),
            "sidecar_or_projector_only": sum(1 for a in artifacts
                                             if a["capabilities"].get("sidecar_or_projector_only")),
            "duplicate_pairs": len(duplicates),
            "symlink_aliases_collapsed": alias_count,
            "cross_root_aliases_collapsed": cross_root_count,
            "by_kind": by_kind,
            "by_state": by_state,
            "total_bytes": sum(a["size_bytes"] for a in artifacts),
        },
        "duplicates": [{"artifact_id": a, "duplicate_of": b} for a, b in duplicates],
        "warnings": warnings,
        "artifacts": artifacts,
    }
    if not stable:
        manifest["generated_at_utc"] = datetime.datetime.now(
            datetime.timezone.utc).isoformat(timespec="seconds")
    return manifest


def main(argv=None):
    ap = argparse.ArgumentParser(description="Read-only local model inventory (P2)")
    ap.add_argument("--root", action="append", default=[], help="extra root as id=path or path")
    ap.add_argument("--references", help="file of paths referenced by Llamactl (JSON list or lines)")
    ap.add_argument("--running", default="", help="comma-separated model paths live in process argv")
    ap.add_argument("--output", help="write manifest JSON here (must be outside every root)")
    ap.add_argument("--stable", action="store_true", help="omit timestamps for byte-reproducible output")
    ap.add_argument("--summary", action="store_true", help="print counts and warnings only")
    args = ap.parse_args(argv)

    roots = list(DEFAULT_ROOTS)
    for r in args.root:
        if "=" in r:
            rid, path = r.split("=", 1)
        else:
            path = r
            rid = re.sub(r"[^a-z0-9]+", "_", path.rstrip("/").rsplit("/", 1)[-1] or "root").lower()
        roots.append((rid, 6, os.path.abspath(os.path.expanduser(path))))

    refs = []
    if args.references:
        ref_path = os.path.abspath(os.path.expanduser(args.references))
        if os.path.isfile(ref_path):
            with open(ref_path, "rb") as fh:
                raw = fh.read().decode("utf-8", "replace")
            try:
                data = json.loads(raw)
                refs = data if isinstance(data, list) else data.get("paths", [])
            except ValueError:
                refs = [ln.strip() for ln in raw.splitlines() if ln.startswith("/")]

    manifest = build(roots, refs, [p.strip() for p in args.running.split(",") if p.strip()],
                     stable=args.stable)
    text = json.dumps(manifest, indent=2, sort_keys=True)
    if args.output:
        out = os.path.abspath(args.output)
        for root_id, _, root in roots:
            if out == root or out.startswith(root + os.sep):
                print(f"refusing to write inside scanned root {root}", file=sys.stderr)
                return 2
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    if args.summary:
        print(json.dumps({"counts": manifest["counts"], "duplicates": manifest["duplicates"],
                          "warnings": manifest["warnings"]}, indent=2, sort_keys=True))
    elif not args.output:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

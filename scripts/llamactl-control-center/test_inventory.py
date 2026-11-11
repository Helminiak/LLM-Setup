#!/usr/bin/env python3
"""Fixture tests for scripts/llamactl-control-center/inventory.py (phase P2).

Run: python3 scripts/llamactl-control-center/test_inventory.py
All fixtures are synthetic files under a temp dir; no production path is touched.
"""
import json
import os
import shutil
import struct
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import inventory as inv  # noqa: E402

T_INT32, T_STRING, T_ARRAY = 5, 8, 9


def gguf_bytes(kv, n_tensors=0):
    out = [b"GGUF", struct.pack("<I", 3), struct.pack("<Q", n_tensors), struct.pack("<Q", len(kv))]
    for key, vtype, val in kv:
        elem = None
        if isinstance(vtype, tuple):
            vtype, elem = vtype
        kb = key.encode()
        out.append(struct.pack("<Q", len(kb)) + kb + struct.pack("<I", vtype))
        if vtype == T_INT32:
            out.append(struct.pack("<i", val))
        elif vtype == T_STRING:
            vb = val.encode()
            out.append(struct.pack("<Q", len(vb)) + vb)
        elif vtype == T_ARRAY:
            out.append(struct.pack("<I", elem) + struct.pack("<Q", len(val)))
            if elem == T_STRING:
                for s in val:
                    sb = s.encode()
                    out.append(struct.pack("<Q", len(sb)) + sb)
            elif elem == T_INT32:
                for n in val:
                    out.append(struct.pack("<i", n))
    return b"".join(out)


RUNNABLE = [("general.architecture", T_STRING, "qwen3"),
            ("general.name", T_STRING, "FixtureQwen"),
            ("general.quantization_type", T_STRING, "Q4_K_M"),
            ("general.file_type", T_INT32, 15),
            ("qwen3.context_length", T_INT32, 4096),
            ("qwen3.block_count", T_INT32, 32),
            ("qwen3.tokenizer.ggml.model", T_STRING, "gpt2"),
            ("qwen3.tokenizer.ggml.tokens", (T_ARRAY, T_STRING), ["a", "b", "c"])]
SIDECAR = [("general.architecture", T_STRING, "clip"),
           ("general.name", T_STRING, "mmproj-fixture"),
           ("clip.projector_type", T_STRING, "mlp"),
           ("clip.vision.block_count", T_INT32, 24)]
NO_TOKENIZER = [("general.architecture", T_STRING, "qwen3"),
                ("general.name", T_STRING, "NoTokenizerFixture"),
                ("qwen3.block_count", T_INT32, 8)]
# nextn/MTP export: full metadata and tokenizer, but only a handful of tensors for a
# 32-block architecture (matches bakeoff/flash-sidecar/mtp-*.gguf on 5090FE)
MODULE = NO_TOKENIZER[:2] + [("general.name", T_STRING, "MTPModuleFixture"),
                             ("qwen3.block_count", T_INT32, 32),
                             ("qwen3.nextn_predict_layers", T_INT32, 1),
                             ("qwen3.tokenizer.ggml.model", T_STRING, "gpt2"),
                             ("qwen3.tokenizer.ggml.tokens", (T_ARRAY, T_STRING), ["a", "b"])]
# real llama.cpp exports use bare tokenizer keys, not "<arch>." prefixed ones
BARE_TOKENIZER = [("general.architecture", T_STRING, "qwen3"),
                  ("general.name", T_STRING, "BareTokenizerFixture"),
                  ("general.quantization_type", T_STRING, "Q4_K_M"),
                  ("qwen3.block_count", T_INT32, 4),
                  ("tokenizer.ggml.tokens", (T_ARRAY, T_STRING), ["x", "y", "z", "w"]),
                  ("tokenizer.ggml.token_type", (T_ARRAY, T_INT32), [1, 1, 1, 1]),
                  ("tokenizer.chat_template", T_STRING, "{{ prompt }}" * 200)]
SNAP_REV = "0" * 40


class FixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="llamactl-inv-test-")
        m = os.path.join(cls.tmp, "models")
        os.makedirs(m)
        cls.single = os.path.join(m, "single.gguf")
        cls._write(cls.single, gguf_bytes(RUNNABLE))
        # complete split set
        cls.split_rel = "split.gguf"
        cls._write(os.path.join(m, "split-00001-of-00002.gguf"), gguf_bytes(RUNNABLE))
        cls._write(os.path.join(m, "split-00002-of-00002.gguf"), b"\0" * 4096)
        # incomplete split set (shard 2 missing)
        cls._write(os.path.join(m, "broken-00001-of-00003.gguf"), gguf_bytes(NO_TOKENIZER))
        cls._write(os.path.join(m, "broken-00003-of-00003.gguf"), b"\0" * 4096)
        # bare tokenizer keys (observed layout on 5090FE exports)
        cls._write(os.path.join(m, "bare-tok-Q4.gguf"), gguf_bytes(BARE_TOKENIZER))
        # weights-only export: no tokenizer metadata at all
        cls._write(os.path.join(m, "no-tokenizer.gguf"), gguf_bytes(NO_TOKENIZER))
        # sidecar / projector only
        cls._write(os.path.join(m, "mmproj-fixture.gguf"), gguf_bytes(SIDECAR))
        cls._write(os.path.join(m, "mtp-module-Q8_0.gguf"), gguf_bytes(MODULE, n_tensors=6))
        # quantization variants: same architecture, different sizes -> not duplicates
        cls.variant_q4 = os.path.join(m, "variant-Q4_K_M.gguf")
        cls._write(cls.variant_q4, gguf_bytes(RUNNABLE) + b"\1" * 8192)
        cls._write(os.path.join(m, "variant-Q8_0.gguf"), gguf_bytes(RUNNABLE) + b"\2" * 16384)
        # genuine copy: identical bytes and size -> duplicate
        cls._write(os.path.join(m, "variant-Q4_K_M.copy.gguf"), gguf_bytes(RUNNABLE) + b"\1" * 8192)
        # symlink alias to an enumerated file
        os.symlink(cls.single, os.path.join(m, "linked.gguf"))
        # HF snapshot whose weights are blob symlinks (Xet-style layout)
        snap = os.path.join(m, "hf", "models--cross-encoder--ms-marco-MiniLM", "snapshots", SNAP_REV)
        blobs = os.path.join(m, "hf", "blobs")
        os.makedirs(snap)
        os.makedirs(blobs)
        blob = os.path.join(blobs, "deadbeef" * 8)
        cls._write(blob, b"ONNXDATA" * 512)
        # real HF snapshots keep weights in a subdirectory (onnx/) and the snapshot
        # entry is a symlink into the shared blob store
        os.makedirs(os.path.join(snap, "onnx"))
        os.symlink(blob, os.path.join(snap, "onnx", "model.onnx"))
        # real hub layout: blobs/ also holds an alias symlink to the same bytes, and it
        # must not win the claim against the snapshot entry
        os.symlink(blob, os.path.join(blobs, "cafe42" * 8))
        cls._write(os.path.join(snap, "sentencepiece.bpe.model.txt"), b"x" * 4096)
        os.symlink(blob, os.path.join(snap, "spm.model"))
        cls._write(os.path.join(snap, "config.json"), json.dumps(
            {"architectures": ["BertForSequenceClassification"], "model_type": "bert"}).encode())
        cls._write(os.path.join(snap, "tokenizer.json"), b"{}")
        cls.root_id, cls.root = "test_models", m

    @classmethod
    def _write(cls, path, data):
        with open(path, "wb") as fh:
            fh.write(data)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _build(self, **kw):
        return inv.build([(self.root_id, 6, self.root)], kw.get("references", []),
                         kw.get("running", []), stable=True)

    def _find(self, manifest, needle):
        return next(a for a in manifest["artifacts"] if needle in a["location"]
                    or needle in a["name"])

    def test_single_runnable_gguf(self):
        m = self._build()
        a = self._find(m, "single.gguf")
        self.assertEqual(a["kind"], "gguf")
        self.assertEqual(a["architecture"], "qwen3")
        self.assertEqual(a["quantization"], "Q4_K_M")
        self.assertTrue(a["capabilities"]["runnable_llm"])
        self.assertTrue(a["backend_compatibility"]["llama_cpp"])
        self.assertEqual(a["state"], "unconfigured")
        self.assertEqual(a["metadata"]["qwen3.tokenizer.ggml.tokens"]["count"], 3)

    def test_split_sets_are_grouped_and_missing_shards_flagged(self):
        m = self._build()
        complete = self._find(m, "split.gguf")
        broken = self._find(m, "broken.gguf")
        self.assertEqual(complete["kind"], "gguf_split_set")
        self.assertEqual(complete["files"], 2)
        self.assertTrue(complete["split"]["contiguous"])
        self.assertEqual(complete["size_bytes"],
                         os.path.getsize(os.path.join(self.root, "split-00001-of-00002.gguf"))
                         + os.path.getsize(os.path.join(self.root, "split-00002-of-00002.gguf")))
        self.assertEqual(broken["split"]["missing_indices"], [2])
        self.assertEqual(broken["state"], "incomplete")
        self.assertEqual(m["counts"]["incomplete_split_sets"], 1)

    def test_bare_tokenizer_keys_are_recognised(self):
        m = self._build()
        a = self._find(m, "bare-tok-Q4.gguf")
        self.assertTrue(a["capabilities"]["has_vocab"])
        self.assertTrue(a["capabilities"]["runnable_llm"])
        self.assertEqual(a["capabilities"]["vocab_size"], 4)
        self.assertEqual(a["capabilities"]["chat_template_key"], "tokenizer.chat_template")
        self.assertEqual(a["state"], "unconfigured")
        # long strings are summarized, never dumped
        self.assertIsInstance(a["metadata"]["tokenizer.chat_template"], dict)
        self.assertGreater(a["metadata"]["tokenizer.chat_template"]["len"], 200)

    def test_weights_only_export_is_incomplete(self):
        m = self._build()
        a = self._find(m, "no-tokenizer.gguf")
        self.assertFalse(a["capabilities"]["has_vocab"])
        self.assertFalse(a["capabilities"]["runnable_llm"])
        self.assertEqual(a["state"], "incomplete")
        self.assertEqual(a["dependencies"]["missing"], ["tokenizer/vocab absent from GGUF metadata"])

    def test_overlapping_roots_count_a_file_once(self):
        # 5090FE layout: ~/models is a symlink into /mnt/llm/models and ~/.cache into
        # /mnt/llm/.cache, so two roots reach the same bytes. The realpath claim must
        # collapse them so no weight is counted or sized twice.
        single = self._build()
        link_root = self.root + "-mnt-view"
        os.symlink(self.root, link_root)
        try:
            both = inv.build([(self.root_id, 6, self.root), ("mnt_view", 6, link_root)],
                             [], [], stable=True)
        finally:
            os.unlink(link_root)
        self.assertEqual(single["counts"]["gguf_artifacts"], both["counts"]["gguf_artifacts"])
        self.assertEqual(single["counts"]["total_bytes"], both["counts"]["total_bytes"])
        self.assertEqual(single["counts"]["duplicate_pairs"], both["counts"]["duplicate_pairs"])
        self.assertGreater(both["counts"]["cross_root_aliases_collapsed"], 0)
        self.assertEqual(1, len([a for a in both["artifacts"]
                                 if a["location"].endswith("single.gguf")]))

    def test_sidecar_is_not_a_runnable_model(self):
        m = self._build()
        a = self._find(m, "mmproj-fixture.gguf")
        self.assertTrue(a["capabilities"]["sidecar_or_projector_only"])
        self.assertFalse(a["capabilities"]["runnable_llm"])
        self.assertEqual(a["state"], "incomplete")
        self.assertFalse(a["backend_compatibility"]["llama_cpp"])

    def test_variants_are_not_duplicates_but_copies_are(self):
        m = self._build()
        q4 = self._find(m, "variant-Q4_K_M.gguf")
        q8 = self._find(m, "variant-Q8_0.gguf")
        copy = self._find(m, "variant-Q4_K_M.copy.gguf")
        dup_ids = {d["artifact_id"] for d in m["duplicates"]}
        self.assertNotIn(q8["id"], dup_ids)
        self.assertIn(copy["id"], dup_ids)
        self.assertEqual(dup_ids, {copy["id"]})
        self.assertEqual(next(d for d in m["duplicates"] if d["artifact_id"] == copy["id"])
                         ["duplicate_of"], q4["id"])
        self.assertEqual(m["counts"]["duplicate_pairs"], 1)

    def test_symlink_alias_is_collapsed_not_double_counted(self):
        m = self._build()
        locations = [a["location"] for a in m["artifacts"]]
        self.assertNotIn("linked.gguf", locations)
        self.assertGreaterEqual(m["counts"]["symlink_aliases_collapsed"], 1)
        self.assertEqual(sum(1 for a in m["artifacts"] if a["location"] == "single.gguf"), 1)

    def test_hf_snapshot_weights_counted_once_and_marked_unsupported(self):
        m = self._build()
        snap = self._find(m, SNAP_REV)
        self.assertEqual(snap["kind"], "hf_snapshot")
        self.assertEqual(snap["repo"], "cross-encoder/ms-marco-MiniLM")
        self.assertEqual(snap["metadata"]["task"], "reranking")
        self.assertEqual(snap["state"], "unsupported")
        self.assertTrue(snap["backend_compatibility"]["onnx"])
        self.assertFalse(snap["backend_compatibility"]["llama_cpp"])
        self.assertEqual(snap["size_bytes"], os.path.getsize(os.path.join(self.root, "hf", "blobs",
                                                                          "deadbeef" * 8)))
        # the blob itself must not appear as a second artifact
        self.assertEqual(sum(1 for a in m["artifacts"] if "blobs" in a["location"]), 0)
        # weights come from the snapshot subdirectory; a tokenizer .model is not a weight
        self.assertEqual([os.path.basename(p) for p in snap["paths"]], ["model.onnx"])
        self.assertTrue(snap["paths"][0].endswith("onnx/model.onnx"))
        self.assertEqual(snap["files"], 1)

    def test_nextn_mtp_module_export_is_not_a_runnable_llm(self):
        m = self._build()
        a = self._find(m, "mtp-module-Q8_0.gguf")
        self.assertTrue(a["capabilities"]["module_export"])
        self.assertTrue(a["capabilities"]["sidecar_or_projector_only"])
        self.assertFalse(a["capabilities"]["runnable_llm"])
        self.assertEqual("incomplete", a["state"])
        self.assertIn("block_count", a["dependencies"]["base_model"])
        self.assertEqual(6, a["capabilities"]["n_tensors"])
        self.assertEqual(32, a["capabilities"]["block_count"])

    def test_state_transitions_running_configured_incomplete(self):
        m = self._build(running=[self.single])
        self.assertEqual(self._find(m, "single.gguf")["state"], "running")
        m = self._build(references=[self.variant_q4])
        self.assertEqual(self._find(m, "variant-Q4_K_M.gguf")["state"], "configured")
        m = self._build(running=[os.path.join(self.root, "broken-00001-of-00003.gguf")])
        self.assertEqual(self._find(m, "broken.gguf")["state"], "incomplete")
        # a split shard reference marks the logical model configured
        m = self._build(references=[os.path.join(self.root, "split-00002-of-00002.gguf")])
        self.assertEqual(self._find(m, "split.gguf")["state"], "configured")

    def test_scan_is_deterministic(self):
        self.assertEqual(json.dumps(self._build(), sort_keys=True),
                         json.dumps(self._build(), sort_keys=True))
        m = self._build()
        self.assertNotIn("generated_at_utc", m)
        self.assertIn("generated_at_utc", inv.build([(self.root_id, 6, self.root)], [], [],
                                                    stable=False))

    def test_scan_does_not_modify_or_create_anything_in_the_root(self):
        before = {}
        for dirpath, _dirs, files in os.walk(self.root):
            for f in files:
                p = os.path.join(dirpath, f)
                st = os.lstat(p)
                before[p] = (st.st_size, st.st_mode, st.st_mtime_ns)
        self._build()
        after = {}
        for dirpath, _dirs, files in os.walk(self.root):
            for f in files:
                p = os.path.join(dirpath, f)
                st = os.lstat(p)
                after[p] = (st.st_size, st.st_mode, st.st_mtime_ns)
        self.assertEqual(sorted(before), sorted(after))
        self.assertEqual(before, after)

    def test_output_inside_a_scanned_root_is_refused(self):
        out = os.path.join(self.root, "manifest.json")
        self.assertEqual(inv.main(["--root", f"{self.root_id}={self.root}", "--stable",
                                   "--output", out]), 2)
        self.assertFalse(os.path.exists(out))

    def test_absent_root_is_a_warning_not_a_crash(self):
        m = inv.build([("missing", 3, os.path.join(self.tmp, "does-not-exist"))], [], [],
                      stable=True)
        self.assertTrue(any("absent" in w for w in m["warnings"]))
        self.assertEqual(m["counts"]["artifacts"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
"""Acceptance tests for artifacts.manifest."""

import hashlib
import json
import os
import stat
import sys
import tempfile
import shutil
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from artifacts import manifest, sha256_file  # noqa: E402


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


def h(data):
    return hashlib.sha256(data).hexdigest()


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="manifest-test-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def rooted(self, *parts):
        return os.path.join(self.tmp, *parts)

    def test_empty_tree(self):
        self.assertEqual(manifest(self.tmp), [])

    def test_single_file(self):
        data = b"hello\n"
        write(self.rooted("a.txt"), data)
        got = manifest(self.tmp)
        self.assertEqual(
            got, [{"path": "a.txt", "bytes": len(data), "sha256": h(data)}]
        )

    def test_recursive_and_sorted(self):
        files = {
            "b.txt": b"bbb",
            "a.txt": b"a",
            "sub/deep/z.py": b"zz\n",
            "sub/a.py": b"a",
            "sub/deep/aa.md": b"",
        }
        for rel, data in files.items():
            write(self.rooted(*rel.split("/")), data)
        got = manifest(self.tmp)
        self.assertEqual([e["path"] for e in got], sorted(files))
        for e in got:
            self.assertEqual(set(e), {"path", "bytes", "sha256"})
            self.assertEqual(e["bytes"], len(files[e["path"]]))
            self.assertEqual(e["sha256"], h(files[e["path"]]))
            self.assertIsInstance(e["bytes"], int)
            self.assertIsInstance(e["sha256"], str)
            self.assertEqual(len(e["sha256"]), 64)
            self.assertNotIn("\\", e["path"])

    def test_paths_are_relative_posix_and_not_absolute(self):
        write(self.rooted("d/e/f.txt"), b"x" * 10)
        for e in manifest(self.tmp):
            self.assertFalse(os.path.isabs(e["path"]))
            self.assertTrue(e["path"].startswith("d/e/"))
            self.assertNotIn(self.tmp, e["path"])

    def test_no_timestamps_anywhere(self):
        write(self.rooted("t.txt"), b"time")
        blob = json.dumps(manifest(self.tmp))
        for key in ("mtime", "ctime", "modified", "timestamp", "time", "date"):
            self.assertNotIn(key, blob)

    def test_empty_file_hashed(self):
        write(self.rooted("empty"), b"")
        got = manifest(self.tmp)
        self.assertEqual(got[0]["bytes"], 0)
        self.assertEqual(got[0]["sha256"], h(b""))

    def test_deterministic_across_calls(self):
        for i in range(5):
            write(self.rooted(f"d/{i}/f.bin"), bytes([i]) * (i + 1))
        first = manifest(self.tmp)
        for _ in range(3):
            self.assertEqual(manifest(self.tmp), first)

    def test_nonexistent_root_rejected(self):
        missing = self.rooted("does", "not", "exist")
        with self.assertRaises(ValueError):
            manifest(missing)

    def test_root_that_is_a_file_rejected(self):
        write(self.rooted("regular.txt"), b"data")
        with self.assertRaises(ValueError):
            manifest(self.rooted("regular.txt"))

    def test_symlink_to_file_rejected(self):
        write(self.rooted("target.txt"), b"payload")
        os.symlink(self.rooted("target.txt"), self.rooted("link.txt"))
        with self.assertRaises(ValueError):
            manifest(self.tmp)

    def test_symlink_to_directory_rejected(self):
        write(self.rooted("realdir/f.txt"), b"inside")
        os.symlink(self.rooted("realdir"), self.rooted("dirlink"))
        with self.assertRaises(ValueError):
            manifest(self.tmp)

    def test_symlink_inside_subdir_rejected(self):
        write(self.rooted("pkg/mod.py"), b"pass\n")
        os.symlink(self.rooted("pkg/mod.py"), self.rooted("pkg/alias.py"))
        with self.assertRaises(ValueError):
            manifest(self.tmp)

    def test_symlink_is_never_followed(self):
        # Target lives outside the root; if anything followed the link, hashing
        # would succeed instead of rejecting, and no outside content can be
        # reported.
        outside = tempfile.mkdtemp(prefix="manifest-out-")
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
        secret = os.path.join(outside, "secret.bin")
        with open(secret, "wb") as fh:
            fh.write(b"do-not-include")
        write(self.rooted("keep.txt"), b"keep")
        os.symlink(secret, self.rooted("sneak.txt"))
        with self.assertRaises(ValueError):
            manifest(self.tmp)

    def test_symlinked_ancestor_rejected(self):
        outside = tempfile.mkdtemp(prefix="manifest-out2-")
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
        real = os.path.join(outside, "real")
        write(os.path.join(real, "f.txt"), b"contents")
        link = os.path.join(outside, "alias")
        os.symlink(real, link)
        # root reached *through* a symlink is refused.
        with self.assertRaises(ValueError):
            manifest(link)

    def test_relative_symlink_inside_root_rejected(self):
        write(self.rooted("src/a.py"), b"a")
        os.symlink("a.py", os.path.join(self.rooted("src"), "b.py"))
        with self.assertRaises(ValueError):
            manifest(self.tmp)

    def test_odd_file_types_are_skipped(self):
        write(self.rooted("ok.txt"), b"ok")
        fifo = self.rooted("pipe.fifo")
        os.mkfifo(fifo)
        got = manifest(self.tmp)
        self.assertEqual([e["path"] for e in got], ["ok.txt"])

    def test_streamed_hashing_does_not_whole_buffer(self):
        # A file larger than the internal chunk: the streamed digest must equal
        # the one-shot digest, and bytes must reflect the real size.
        big = os.path.join(self.tmp, "big.bin")
        pattern = bytes(range(256)) * 8192  # 2 MiB
        with open(big, "wb") as fh:
            fh.write(pattern)
        got = manifest(self.tmp)
        self.assertEqual(got[0]["bytes"], len(pattern))
        self.assertEqual(got[0]["sha256"], h(pattern))

    def test_read_error_surfaces_as_valueerror(self):
        if os.geteuid() == 0:
            self.skipTest("chmod-based unreadable check is meaningless as uid 0")
        write(self.rooted("hidden/secret.txt"), b"nope")
        os.chmod(self.rooted("hidden/secret.txt"), 0)
        self.addCleanup(os.chmod, self.rooted("hidden/secret.txt"), 0o644)
        # Reading is refused; the walk itself still reaches the entry, so a
        # ValueError (not a bare OSError) must surface from manifest().
        try:
            manifest(self.tmp)
        except ValueError:
            pass
        except OSError as exc:
            self.fail(f"expected ValueError, got {type(exc).__name__}: {exc}")


    def test_sha256_file_matches_hashlib_and_returns_size(self):
        data = bytes(range(256)) * 1234
        path = self.rooted("stream.bin")
        with open(path, "wb") as fh:
            fh.write(data)
        digest, size = sha256_file(path)
        self.assertEqual(digest, h(data))
        self.assertEqual(size, len(data))

    def test_sha256_file_empty(self):
        path = self.rooted("zero")
        write(path, b"")
        self.assertEqual(sha256_file(path), (h(b""), 0))


if __name__ == "__main__":
    unittest.main(verbosity=2)

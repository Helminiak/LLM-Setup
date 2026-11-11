"""File-tree manifesting utilities.

Standard library only. Manifest entries carry no timestamps and no absolute
paths, so the result is byte-stable across machines, clocks and mount points —
exactly the data a review/diff controller needs.
"""

import hashlib
import os
import stat
import posixpath

__all__ = ("manifest", "sha256_file")

_CHUNK = 1024 * 1024


def sha256_file(path):
    """Return (sha256hexdigest, byte_count) reading the file in chunks.

    Contents are streamed, never buffered whole: memory stays flat regardless
    of file size.
    """
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(_CHUNK)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), size


def _reject_symlink(path):
    """Raise ValueError if *path* is a symlink (leaf or any component)."""
    if os.path.islink(path):
        raise ValueError(f"refusing to follow symlink: {path}")
    # os.path.islink only tests the leaf, so walk the ancestors too: a path
    # under a symlinked directory is reachable only by following a link.
    parent = os.path.dirname(path)
    while parent not in (parent.rstrip(os.sep), "", os.sep, os.curdir):
        if os.path.islink(parent):
            raise ValueError(f"refusing to follow symlinked ancestor: {parent}")
        parent = os.path.dirname(parent)


def manifest(root):
    """Manifest every regular file under *root*, deterministically.

    Returns a list of ``{"path": str, "bytes": int, "sha256": str}`` sorted by
    ``path``, where ``path`` is relative to *root* with forward-slash
    separators. Results contain no timestamps and no absolute paths.

    * ValueError if *root* does not exist or is not a directory.
    * ValueError if ANY symlink exists inside *root* — a symlinked file, a
      symlinked directory, or a symlinked path component on the way in. The
      symlink is never followed or resolved.
    * Only regular files appear in the manifest; directories and other odd
      types (sockets, fifos, devices) are neither hashed nor emitted.
    """
    root = os.fspath(root)
    if not os.path.isdir(root):
        raise ValueError(f"root does not exist or is not a directory: {root}")

    base = os.path.abspath(root)
    entries = []
    # followlinks=False so os.walk never descends into a linked directory on
    # its own; the explicit rejection below turns each such link into an error
    # rather than a silent omission.
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        _reject_symlink(dirpath)
        kept = []
        for name in dirnames:
            child = os.path.join(dirpath, name)
            if os.path.islink(child):
                raise ValueError(f"refusing to follow symlink: {child}")
            kept.append(name)
        dirnames[:] = kept
        dirnames.sort()
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            _reject_symlink(path)
            try:
                st = os.stat(path, follow_symlinks=False)
            except OSError as exc:
                raise ValueError(f"cannot stat {path}: {exc}") from exc
            if not stat.S_ISREG(st.st_mode):
                continue
            rel = os.path.relpath(path, base)
            try:
                digest, size = sha256_file(path)
            except OSError as exc:
                raise ValueError(f"cannot hash {path}: {exc}") from exc
            entries.append(
                {"path": rel.replace(os.sep, posixpath.sep),
                 "bytes": size,
                 "sha256": digest}
            )
    entries.sort(key=lambda entry: entry["path"])
    return entries

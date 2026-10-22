"""Walk a directory tree into a ``{relative_path: Entry}`` snapshot."""

from __future__ import annotations

import fnmatch
import os
from collections.abc import Iterable

from comparator.models import Entry, EntryKind


def is_excluded(rel_path: str, patterns: Iterable[str]) -> bool:
    """True if ``rel_path`` (``/``-separated) matches any glob pattern.

    A pattern matches either the whole relative path (``build/*.o``) or any
    single path component (``__pycache__``, ``*.tmp``).
    """
    parts = rel_path.split("/")
    for pattern in patterns:
        pattern = pattern.strip().strip("/")
        if not pattern:
            continue
        if fnmatch.fnmatchcase(rel_path, pattern):
            return True
        if any(fnmatch.fnmatchcase(part, pattern) for part in parts):
            return True
    return False


def scan_tree(root: str | os.PathLike[str], exclude: Iterable[str] = ()) -> dict[str, Entry]:
    """Snapshot every file and directory below ``root``.

    * Paths are relative to ``root`` and ``/``-separated.
    * Excluded entries (and everything under an excluded directory) are left out.
    * Symbolic links are skipped entirely (neither followed nor copied).
    * A missing ``root`` yields an empty snapshot.
    """
    patterns = tuple(exclude)
    root = os.fspath(root)
    entries: dict[str, Entry] = {}
    if not os.path.isdir(root):
        return entries

    stack = [""]
    while stack:
        rel_dir = stack.pop()
        abs_dir = os.path.join(root, *rel_dir.split("/")) if rel_dir else root
        try:
            with os.scandir(abs_dir) as it:
                children = list(it)
        except OSError:
            continue
        for child in children:
            rel = f"{rel_dir}/{child.name}" if rel_dir else child.name
            if is_excluded(rel, patterns):
                continue
            try:
                if child.is_symlink():
                    continue
                if child.is_dir(follow_symlinks=False):
                    entries[rel] = Entry(rel, EntryKind.DIR)
                    stack.append(rel)
                elif child.is_file(follow_symlinks=False):
                    st = child.stat(follow_symlinks=False)
                    entries[rel] = Entry(rel, EntryKind.FILE, st.st_size, st.st_mtime)
            except OSError:
                continue
    return entries

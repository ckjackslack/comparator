import os

import pytest

from comparator.models import EntryKind
from comparator.scan import is_excluded, scan_tree


def test_scan_relative_posix_paths(tree):
    root = tree("t", {"a.txt": "abc", "sub": {"deep": {"x.bin": b"12"}}, "empty": {}})
    snap = scan_tree(root)
    assert set(snap) == {"a.txt", "sub", "sub/deep", "sub/deep/x.bin", "empty"}
    assert snap["a.txt"].kind is EntryKind.FILE and snap["a.txt"].size == 3
    assert snap["sub/deep"].kind is EntryKind.DIR
    assert snap["sub/deep/x.bin"].size == 2
    assert snap["a.txt"].mtime == pytest.approx(os.stat(root / "a.txt").st_mtime)


def test_scan_missing_root_is_empty(tmp_path):
    assert scan_tree(tmp_path / "missing") == {}


def test_scan_excludes_dirs_and_files(tree):
    root = tree(
        "t",
        {"keep.py": "", "x.tmp": "", "__pycache__": {"m.pyc": ""}, "build": {"o": {"a.o": ""}}},
    )
    snap = scan_tree(root, exclude=["*.tmp", "__pycache__", "build/o"])
    assert set(snap) == {"keep.py", "build"}


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="no symlinks")
def test_scan_skips_symlinks(tree):
    root = tree("t", {"real.txt": "x", "dir": {"f": "y"}})
    os.symlink(root / "real.txt", root / "link.txt")
    os.symlink(root / "dir", root / "linkdir")
    assert set(scan_tree(root)) == {"real.txt", "dir", "dir/f"}


@pytest.mark.parametrize(
    "path, patterns, expected",
    [
        ("a/b/c.txt", ["*.txt"], True),
        ("a/b/c.txt", ["b"], True),
        ("a/b/c.txt", ["a/b/*"], True),
        ("a/b/c.txt", ["a/b/"], True),
        ("a/b/c.txt", ["*.py", "x"], False),
        ("a/b/c.txt", ["", "  "], False),
        ("a/b/C.TXT", ["*.txt"], False),
    ],
)
def test_is_excluded(path, patterns, expected):
    assert is_excluded(path, patterns) is expected

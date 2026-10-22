from __future__ import annotations

from pathlib import Path

import pytest


def make_tree(root: Path, spec: dict) -> Path:
    """Create files (str/bytes values) and directories (dict values) under root."""
    root.mkdir(parents=True, exist_ok=True)
    for name, content in spec.items():
        path = root / name
        if isinstance(content, dict):
            make_tree(path, content)
        elif isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content)
    return root


@pytest.fixture
def tree(tmp_path):
    def _tree(name: str, spec: dict) -> Path:
        return make_tree(tmp_path / name, spec)

    return _tree


@pytest.fixture
def sample(tree):
    """Mirrors examples/: a copy, an extra, a same, an update and a nested mkdir."""
    src = tree(
        "src",
        {
            "a.txt": "Hello, world!\n",
            "c.txt": "aaargh hi\n",
            "d.txt": "version 2\n",
            "some-directory": {"nested.txt": "nested\n"},
        },
    )
    dst = tree("dst", {"b.txt": "Hell no.\n", "c.txt": "aaargh hi\n", "d.txt": "version 1\n"})
    return src, dst

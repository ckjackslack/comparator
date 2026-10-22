import hashlib

import pytest

from comparator.hashing import file_hash, validate_algorithm


def test_file_hash_matches_hashlib(tmp_path):
    data = b"x" * 200_000 + b"tail"
    path = tmp_path / "f.bin"
    path.write_bytes(data)
    assert file_hash(path) == hashlib.sha256(data).hexdigest()
    assert file_hash(path, "md5", chunk_size=7) == hashlib.md5(data).hexdigest()


def test_empty_file(tmp_path):
    path = tmp_path / "empty"
    path.write_bytes(b"")
    assert file_hash(path) == hashlib.sha256(b"").hexdigest()


@pytest.mark.parametrize("name", ["nope", "shake_128", ""])
def test_invalid_algorithm(name):
    with pytest.raises(ValueError):
        validate_algorithm(name)


def test_validate_normalises():
    assert validate_algorithm(" SHA1 ") == "sha1"


def test_bad_chunk_size(tmp_path):
    path = tmp_path / "f"
    path.write_text("x")
    with pytest.raises(ValueError):
        file_hash(path, chunk_size=0)


def test_missing_file_raises_oserror(tmp_path):
    with pytest.raises(OSError):
        file_hash(tmp_path / "missing")

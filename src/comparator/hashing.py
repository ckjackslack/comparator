"""Chunked file hashing."""

from __future__ import annotations

import hashlib
import os

DEFAULT_ALGORITHM = "sha256"
DEFAULT_CHUNK_SIZE = 64 * 1024


def validate_algorithm(name: str) -> str:
    """Return the normalised algorithm name or raise ``ValueError``.

    Variable-length digests (``shake_*``) are rejected because they need an
    explicit length.
    """
    normalised = name.strip().lower()
    try:
        hashlib.new(normalised).hexdigest()
    except (ValueError, TypeError):
        raise ValueError(f"unsupported hash algorithm: {name!r}") from None
    return normalised


def file_hash(
    path: str | os.PathLike[str],
    algorithm: str = DEFAULT_ALGORITHM,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> str:
    """Hex digest of a file's contents, read in chunks."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    digest = hashlib.new(validate_algorithm(algorithm))
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()

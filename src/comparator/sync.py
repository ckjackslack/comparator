"""Apply a plan to the filesystem (the only module that writes)."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from comparator.models import Action, Change, EntryKind

Reporter = Callable[[Change], None]


@dataclass
class ApplyResult:
    applied: list[Change] = field(default_factory=list)
    failed: list[tuple[Change, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failed


def _abs(root: str, rel: str) -> str:
    return os.path.join(root, *rel.split("/"))


def _apply_one(change: Change, source_root: str, target_root: str) -> None:
    dst = _abs(target_root, change.path)
    if change.action is Action.MKDIR:
        os.makedirs(dst, exist_ok=True)
        shutil.copystat(_abs(source_root, change.path), dst)
    elif change.action in (Action.COPY, Action.UPDATE):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(_abs(source_root, change.path), dst)
    elif change.action is Action.DELETE:
        if change.kind is EntryKind.DIR:
            os.rmdir(dst)  # children were deleted first; never rmtree excluded files
        else:
            os.remove(dst)
    else:  # SAME / EXTRA / CONFLICT are informational only
        raise ValueError(f"not an applicable action: {change.action}")


def _order(changes: Iterable[Change]) -> list[Change]:
    """Deletions first (deepest first), then mkdir/copy/update parents-first."""
    actionable = [c for c in changes if c.action.mutates]
    deletes = sorted(
        (c for c in actionable if c.action is Action.DELETE),
        key=lambda c: c.path.split("/"),
        reverse=True,
    )
    writes = sorted(
        (c for c in actionable if c.action is not Action.DELETE),
        key=lambda c: c.path.split("/"),
    )
    return deletes + writes


def apply_plan(
    changes: Iterable[Change],
    source_root: str | os.PathLike[str],
    target_root: str | os.PathLike[str],
    *,
    on_change: Reporter | None = None,
) -> ApplyResult:
    """Execute every mutating change; errors are collected, never raised.

    Directory mtimes are re-synced at the end because copying files into a
    directory bumps its modification time.
    """
    source_root = os.fspath(source_root)
    target_root = os.fspath(target_root)
    result = ApplyResult()

    os.makedirs(target_root, exist_ok=True)
    for change in _order(changes):
        try:
            _apply_one(change, source_root, target_root)
        except OSError as exc:
            result.failed.append((change, exc.strerror or str(exc)))
            continue
        result.applied.append(change)
        if on_change is not None:
            on_change(change)

    for change in reversed(result.applied):
        if change.action is Action.MKDIR:
            try:
                shutil.copystat(_abs(source_root, change.path), _abs(target_root, change.path))
            except OSError:
                pass
    return result

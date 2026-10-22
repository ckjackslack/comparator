"""Pure planning logic: two snapshots in, a sorted list of changes out.

Nothing here touches the filesystem. Content comparison that needs file
contents (hash mode) goes through the injected ``content_equal`` callable.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from enum import Enum

from comparator.models import Action, Change, Entry

MTIME_TOLERANCE = 1.0  # seconds; coarse filesystems (FAT, some network FS) round mtimes


class CompareMode(str, Enum):
    HASH = "hash"  # size, then content digest (default, safest)
    MTIME = "mtime"  # size + modification time (fast, like rsync's quick check)
    SIZE = "size"  # size only (fastest, least reliable)


ContentEqual = Callable[[str], bool]


def _files_equal(
    src: Entry,
    dst: Entry,
    mode: CompareMode,
    content_equal: ContentEqual | None,
) -> tuple[bool, str]:
    if src.size != dst.size:
        return False, f"size {dst.size} -> {src.size}"
    if mode is CompareMode.SIZE:
        return True, ""
    if mode is CompareMode.MTIME:
        if abs(src.mtime - dst.mtime) > MTIME_TOLERANCE:
            return False, "modification time differs"
        return True, ""
    if content_equal is None:
        raise ValueError("hash mode needs a content_equal callable")
    if content_equal(src.path):
        return True, ""
    return False, "content differs"


def build_plan(
    source: Mapping[str, Entry],
    target: Mapping[str, Entry],
    *,
    mode: CompareMode = CompareMode.HASH,
    content_equal: ContentEqual | None = None,
    delete: bool = False,
) -> list[Change]:
    """Work out what is needed to make ``target`` mirror ``source``.

    Every path present in either snapshot gets exactly one ``Change``. The
    result is sorted by path, which also guarantees parents come before their
    children.
    """
    mode = CompareMode(mode)
    changes: list[Change] = []

    for path, src in source.items():
        dst = target.get(path)
        if dst is None:
            action = Action.MKDIR if src.is_dir else Action.COPY
            changes.append(Change(path, action, src.kind, "missing in target"))
        elif src.kind is not dst.kind:
            reason = f"{src.kind.value} in source, {dst.kind.value} in target"
            changes.append(Change(path, Action.CONFLICT, src.kind, reason))
        elif src.is_dir:
            changes.append(Change(path, Action.SAME, src.kind))
        else:
            equal, reason = _files_equal(src, dst, mode, content_equal)
            action = Action.SAME if equal else Action.UPDATE
            changes.append(Change(path, action, src.kind, reason))

    for path, dst in target.items():
        if path in source:
            continue
        if delete:
            changes.append(Change(path, Action.DELETE, dst.kind, "not in source"))
        else:
            changes.append(Change(path, Action.EXTRA, dst.kind, "only in target"))

    changes.sort(key=lambda c: c.path.split("/"))
    return _propagate_conflicts(changes)


def _propagate_conflicts(changes: list[Change]) -> list[Change]:
    """Anything below a conflicting path cannot be synced safely either."""
    conflicted: list[str] = []
    result: list[Change] = []
    for change in changes:  # sorted, so a conflict is seen before its children
        parent = next((p for p in conflicted if change.path.startswith(p + "/")), None)
        if parent is not None:
            change = Change(change.path, Action.CONFLICT, change.kind, f"inside conflicting {parent!r}")
        if change.action is Action.CONFLICT:
            conflicted.append(change.path)
        result.append(change)
    return result


def has_differences(changes: Iterable[Change]) -> bool:
    """True when the two trees are not identical (anything but SAME)."""
    return any(c.action is not Action.SAME for c in changes)


def count_actions(changes: Iterable[Change]) -> dict[Action, int]:
    counts = {action: 0 for action in Action}
    for change in changes:
        counts[change.action] += 1
    return counts

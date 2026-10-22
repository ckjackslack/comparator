"""Plain data types shared by the scanner, the planner and the syncer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class EntryKind(str, Enum):
    FILE = "file"
    DIR = "dir"


@dataclass(frozen=True)
class Entry:
    """One file or directory inside a scanned tree.

    ``path`` is relative to the tree root and always uses ``/`` as separator,
    so plans are identical on every platform.
    """

    path: str
    kind: EntryKind
    size: int = 0
    mtime: float = 0.0

    @property
    def is_dir(self) -> bool:
        return self.kind is EntryKind.DIR


class Action(str, Enum):
    """What should happen to one relative path."""

    COPY = "copy"  # file exists only in source
    MKDIR = "mkdir"  # directory exists only in source
    UPDATE = "update"  # file exists in both but differs
    SAME = "same"  # nothing to do
    EXTRA = "extra"  # exists only in target, kept (no --delete)
    DELETE = "delete"  # exists only in target, removed (--delete)
    CONFLICT = "conflict"  # file in one tree, directory in the other

    @property
    def label(self) -> str:
        return self.value.capitalize()

    @property
    def mutates(self) -> bool:
        """True when applying the plan changes the target for this action."""
        return self in MUTATING_ACTIONS


MUTATING_ACTIONS = frozenset({Action.COPY, Action.MKDIR, Action.UPDATE, Action.DELETE})


@dataclass(frozen=True)
class Change:
    """A planned action for one relative path, with a human readable reason."""

    path: str
    action: Action
    kind: EntryKind
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "action": self.action.value,
            "kind": self.kind.value,
            "reason": self.reason,
        }

"""Render plans and results as text tables, summaries or JSON (pure functions)."""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence

from comparator.compare import count_actions, has_differences
from comparator.models import Action, Change, EntryKind
from comparator.sync import ApplyResult

_SUMMARY_WORDS = {
    Action.COPY: "to copy",
    Action.MKDIR: "dir(s) to create",
    Action.UPDATE: "to update",
    Action.DELETE: "to delete",
    Action.EXTRA: "only in target",
    Action.CONFLICT: "conflicts",
    Action.SAME: "unchanged",
}


def display_path(change: Change) -> str:
    return change.path + "/" if change.kind is EntryKind.DIR else change.path


def visible(changes: Iterable[Change], show_same: bool = False) -> list[Change]:
    return [c for c in changes if show_same or c.action is not Action.SAME]


def format_table(changes: Sequence[Change], show_same: bool = False) -> str:
    """A plain aligned text table; ``SAME`` rows are hidden unless asked for."""
    rows = [(c.action.label, display_path(c), c.reason) for c in visible(changes, show_same)]
    if not rows:
        return "(no differences)"
    headers = ("Action", "Path", "Details")
    widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]

    def line(cells: Sequence[str]) -> str:
        return "  ".join(cell.ljust(w) for cell, w in zip(cells, widths)).rstrip()

    out = [line(headers), line(["-" * w for w in widths])]
    out.extend(line(r) for r in rows)
    return "\n".join(out)


def format_summary(changes: Sequence[Change]) -> str:
    counts = count_actions(changes)
    parts = [f"{counts[a]} {_SUMMARY_WORDS[a]}" for a in _SUMMARY_WORDS if counts[a]]
    if not parts:
        return "Both trees are empty."
    status = "differences found" if has_differences(changes) else "in sync"
    return f"{', '.join(parts)} ({status})"


def format_apply_result(result: ApplyResult) -> str:
    msg = f"Applied {len(result.applied)} change(s)"
    if result.failed:
        msg += f", {len(result.failed)} failed"
    return msg + "."


def to_json(
    changes: Sequence[Change],
    *,
    source: str,
    target: str,
    show_same: bool = False,
    result: ApplyResult | None = None,
) -> str:
    counts = count_actions(changes)
    payload: dict = {
        "source": source,
        "target": target,
        "in_sync": not has_differences(changes),
        "summary": {a.value: counts[a] for a in Action},
        "changes": [c.to_dict() for c in visible(changes, show_same)],
    }
    if result is not None:
        payload["applied"] = [c.to_dict() for c in result.applied]
        payload["failed"] = [{**c.to_dict(), "error": err} for c, err in result.failed]
    return json.dumps(payload, indent=2)

"""Planner tests use in-memory snapshots only: no filesystem involved."""

import pytest

from comparator.compare import CompareMode, build_plan, count_actions, has_differences
from comparator.models import Action, Entry, EntryKind


def f(path, size=1, mtime=100.0):
    return Entry(path, EntryKind.FILE, size, mtime)


def d(path):
    return Entry(path, EntryKind.DIR)


def snap(*entries):
    return {e.path: e for e in entries}


def actions(plan):
    return {c.path: c.action for c in plan}


def never_called(path):  # pragma: no cover - fails the test if used
    raise AssertionError(f"content_equal called for {path}")


def test_copy_mkdir_extra_and_same_dirs():
    plan = build_plan(
        snap(f("a"), d("sub"), f("sub/x"), d("both")),
        snap(f("b"), d("both")),
        content_equal=never_called,
    )
    assert actions(plan) == {
        "a": Action.COPY,
        "b": Action.EXTRA,
        "both": Action.SAME,
        "sub": Action.MKDIR,
        "sub/x": Action.COPY,
    }


def test_delete_flag_turns_extra_into_delete():
    plan = build_plan(snap(), snap(d("old"), f("old/x")), delete=True)
    assert actions(plan) == {"old": Action.DELETE, "old/x": Action.DELETE}
    assert all(c.reason == "not in source" for c in plan)


def test_size_difference_never_hashes():
    plan = build_plan(snap(f("a", 3)), snap(f("a", 4)), content_equal=never_called)
    assert plan[0].action is Action.UPDATE
    assert plan[0].reason == "size 4 -> 3"


@pytest.mark.parametrize("equal, expected", [(True, Action.SAME), (False, Action.UPDATE)])
def test_hash_mode_uses_content_equal(equal, expected):
    calls = []

    def content_equal(path):
        calls.append(path)
        return equal

    plan = build_plan(snap(f("a")), snap(f("a")), content_equal=content_equal)
    assert calls == ["a"]
    assert plan[0].action is expected


def test_hash_mode_requires_callable():
    with pytest.raises(ValueError):
        build_plan(snap(f("a")), snap(f("a")))


def test_size_mode_ignores_content_and_mtime():
    plan = build_plan(snap(f("a", 5, 1.0)), snap(f("a", 5, 999.0)), mode="size")
    assert plan[0].action is Action.SAME


@pytest.mark.parametrize("dst_mtime, expected", [(100.5, Action.SAME), (102.0, Action.UPDATE)])
def test_mtime_mode_tolerance(dst_mtime, expected):
    plan = build_plan(
        snap(f("a", 5, 100.0)), snap(f("a", 5, dst_mtime)), mode=CompareMode.MTIME
    )
    assert plan[0].action is expected


def test_invalid_mode():
    with pytest.raises(ValueError):
        build_plan(snap(), snap(), mode="nope")


def test_kind_conflict_propagates_to_children():
    plan = build_plan(
        snap(d("x"), f("x/inner"), f("y")),
        snap(f("x"), d("y"), f("y/z")),
        delete=True,
    )
    assert actions(plan) == {
        "x": Action.CONFLICT,
        "x/inner": Action.CONFLICT,
        "y": Action.CONFLICT,
        "y/z": Action.CONFLICT,
    }
    assert plan[0].reason == "dir in source, file in target"
    assert "inside conflicting 'x'" in plan[1].reason


def test_sorted_parents_before_children():
    plan = build_plan(
        snap(d("a"), f("a/z"), f("a-b"), d("a/b"), f("a/b/c")), snap(), content_equal=never_called
    )
    assert [c.path for c in plan] == ["a", "a/b", "a/b/c", "a/z", "a-b"]


def test_has_differences_and_counts():
    same = build_plan(snap(d("a")), snap(d("a")))
    assert not has_differences(same)
    assert not has_differences([])
    extra_only = build_plan(snap(), snap(f("b")))
    assert has_differences(extra_only)
    counts = count_actions(extra_only)
    assert counts[Action.EXTRA] == 1 and counts[Action.COPY] == 0

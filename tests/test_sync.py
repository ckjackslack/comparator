import os

from comparator.compare import build_plan
from comparator.models import Action, Change, EntryKind
from comparator.scan import scan_tree
from comparator.sync import _order, apply_plan


def plan_for(src, dst, **kw):
    from comparator.cli import make_content_equal

    return build_plan(
        scan_tree(src), scan_tree(dst), content_equal=make_content_equal(str(src), str(dst), "sha256"), **kw
    )


def test_apply_makes_target_mirror_source(sample):
    src, dst = sample
    plan = plan_for(src, dst, delete=True)
    seen = []
    result = apply_plan(plan, src, dst, on_change=seen.append)
    assert result.ok
    assert {c.path for c in seen} == {"a.txt", "b.txt", "d.txt", "some-directory", "some-directory/nested.txt"}
    assert (dst / "some-directory" / "nested.txt").read_text() == "nested\n"
    assert (dst / "d.txt").read_text() == "version 2\n"
    assert not (dst / "b.txt").exists()
    after = plan_for(src, dst)
    assert all(c.action is Action.SAME for c in after)


def test_apply_without_delete_keeps_extras(sample):
    src, dst = sample
    result = apply_plan(plan_for(src, dst), src, dst)
    assert result.ok
    assert (dst / "b.txt").exists()


def test_apply_preserves_mtime(sample):
    src, dst = sample
    os.utime(src / "a.txt", (1_000_000, 1_000_000))
    apply_plan(plan_for(src, dst), src, dst)
    assert os.stat(dst / "a.txt").st_mtime == 1_000_000


def test_apply_creates_missing_target(tree, tmp_path):
    src = tree("src", {"x": {"y": {"z.txt": "deep"}}})
    dst = tmp_path / "new" / "target"
    result = apply_plan(plan_for(src, dst), src, dst)
    assert result.ok
    assert (dst / "x" / "y" / "z.txt").read_text() == "deep"


def test_delete_dirs_deepest_first(tree):
    src = tree("src", {})
    dst = tree("dst", {"old": {"deeper": {"f": "1"}, "g": "2"}})
    result = apply_plan(plan_for(src, dst, delete=True), src, dst)
    assert result.ok
    assert list(dst.iterdir()) == []


def test_delete_never_removes_excluded_files(tree):
    src = tree("src", {})
    dst = tree("dst", {"old": {"f": "1", "keep.tmp": "precious"}})
    plan = build_plan(scan_tree(src, ["*.tmp"]), scan_tree(dst, ["*.tmp"]), delete=True)
    result = apply_plan(plan, src, dst)
    assert (dst / "old" / "keep.tmp").read_text() == "precious"
    assert [c.path for c, _ in result.failed] == ["old"]


def test_informational_changes_are_ignored(tree):
    src = tree("src", {"a": "1"})
    dst = tree("dst", {"a": "1", "b": "2"})
    plan = [
        Change("a", Action.SAME, EntryKind.FILE),
        Change("b", Action.EXTRA, EntryKind.FILE),
        Change("c", Action.CONFLICT, EntryKind.FILE),
    ]
    result = apply_plan(plan, src, dst)
    assert result.ok and result.applied == []


def test_errors_are_collected_not_raised(tree):
    src = tree("src", {"ok.txt": "1"})
    dst = tree("dst", {})
    plan = [
        Change("missing.txt", Action.COPY, EntryKind.FILE),
        Change("ok.txt", Action.COPY, EntryKind.FILE),
    ]
    result = apply_plan(plan, src, dst)
    assert [c.path for c in result.applied] == ["ok.txt"]
    assert [c.path for c, _ in result.failed] == ["missing.txt"]
    assert not result.ok


def test_order_deletes_first_then_parents_first():
    changes = [
        Change("n/f", Action.COPY, EntryKind.FILE),
        Change("n", Action.MKDIR, EntryKind.DIR),
        Change("o", Action.DELETE, EntryKind.DIR),
        Change("o/f", Action.DELETE, EntryKind.FILE),
        Change("s", Action.SAME, EntryKind.FILE),
    ]
    assert [c.path for c in _order(changes)] == ["o/f", "o", "n", "n/f"]

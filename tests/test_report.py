import json

from comparator.models import Action, Change, EntryKind
from comparator.report import format_apply_result, format_summary, format_table, to_json
from comparator.sync import ApplyResult

PLAN = [
    Change("a.txt", Action.COPY, EntryKind.FILE, "missing in target"),
    Change("c.txt", Action.SAME, EntryKind.FILE),
    Change("dir", Action.MKDIR, EntryKind.DIR, "missing in target"),
]


def test_table_hides_same_by_default():
    out = format_table(PLAN)
    lines = out.splitlines()
    assert lines[0].split() == ["Action", "Path", "Details"]
    assert "c.txt" not in out
    assert "dir/" in out  # directories get a trailing slash
    assert any(line.startswith("Copy ") for line in lines)


def test_table_columns_align():
    lines = format_table(PLAN, show_same=True).splitlines()
    col = lines[0].index("Path")
    assert all(line[col - 2 : col] == "  " for line in lines[2:])
    assert "c.txt" in "\n".join(lines)


def test_table_empty():
    assert format_table([]) == "(no differences)"
    assert format_table([PLAN[1]]) == "(no differences)"


def test_summary():
    assert format_summary(PLAN) == "1 to copy, 1 dir(s) to create, 1 unchanged (differences found)"
    assert format_summary([PLAN[1]]) == "1 unchanged (in sync)"
    assert format_summary([]) == "Both trees are empty."


def test_apply_result_text():
    r = ApplyResult(applied=[PLAN[0]], failed=[(PLAN[2], "Permission denied")])
    assert format_apply_result(r) == "Applied 1 change(s), 1 failed."
    assert format_apply_result(ApplyResult()) == "Applied 0 change(s)."


def test_json_payload():
    r = ApplyResult(applied=[PLAN[0]], failed=[(PLAN[2], "boom")])
    data = json.loads(to_json(PLAN, source="/s", target="/t", result=r))
    assert data["in_sync"] is False
    assert data["summary"]["copy"] == 1 and data["summary"]["same"] == 1
    assert [c["path"] for c in data["changes"]] == ["a.txt", "dir"]
    assert data["failed"] == [
        {"path": "dir", "action": "mkdir", "kind": "dir", "reason": "missing in target", "error": "boom"}
    ]
    assert "applied" not in json.loads(to_json(PLAN, source="/s", target="/t"))

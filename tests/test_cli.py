import json
import subprocess
import sys

import pytest

from comparator.cli import EXIT_APPLY_FAILED, EXIT_DIFFERENT, EXIT_OK, EXIT_USAGE, main


def run(argv, env=None, confirm=None):
    return main([str(a) for a in argv], environ=env or {}, confirm=confirm)


def test_preview_reports_and_changes_nothing(sample, capsys):
    src, dst = sample
    before = sorted(p.name for p in dst.iterdir())
    assert run([src, dst]) == EXIT_DIFFERENT
    out = capsys.readouterr().out
    for expected in ("Copy", "a.txt", "Extra", "b.txt", "Update", "d.txt", "some-directory/nested.txt"):
        assert expected in out
    assert "c.txt" not in out
    assert "differences found" in out
    assert sorted(p.name for p in dst.iterdir()) == before


def test_show_all_and_quiet(sample, capsys):
    src, dst = sample
    run([src, dst, "--all"])
    assert "c.txt" in capsys.readouterr().out
    run([src, dst, "-q"])
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1 and out[0].endswith("(differences found)")


def test_in_sync_exit_zero(tree, capsys):
    a = tree("a", {"x": "1", "d": {"y": "2"}})
    b = tree("b", {"x": "1", "d": {"y": "2"}})
    assert run([a, b]) == EXIT_OK
    assert "(in sync)" in capsys.readouterr().out


def test_apply_yes_with_delete(sample, capsys):
    src, dst = sample
    assert run([src, dst, "--apply", "--yes", "--delete"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "Applied 5 change(s)." in out
    assert not (dst / "b.txt").exists()
    assert run([src, dst]) == EXIT_OK


def test_apply_asks_and_respects_no(sample, capsys):
    src, dst = sample
    prompts = []

    def decline(prompt):
        prompts.append(prompt)
        return False

    assert run([src, dst, "--apply"], confirm=decline) == EXIT_DIFFERENT
    assert prompts and "Apply 4 change(s)" in prompts[0]
    assert "Aborted" in capsys.readouterr().err
    assert not (dst / "a.txt").exists()


def test_apply_confirmed(sample):
    src, dst = sample
    assert run([src, dst, "--apply"], confirm=lambda p: True) == EXIT_OK
    assert (dst / "a.txt").exists() and (dst / "b.txt").exists()


def test_apply_nothing_to_do_skips_prompt(tree, capsys):
    a = tree("a", {"x": "1"})
    b = tree("b", {"x": "1", "extra": "2"})

    def fail(prompt):  # pragma: no cover
        raise AssertionError("should not ask")

    assert run([a, b, "--apply"], confirm=fail) == EXIT_OK
    assert "Nothing to apply." in capsys.readouterr().out


def test_apply_non_interactive_without_yes_is_refused(sample, monkeypatch, capsys):
    src, dst = sample

    class FakeStdin:
        def isatty(self):
            return False

    monkeypatch.setattr(sys, "stdin", FakeStdin())
    assert main([str(src), str(dst), "--apply"], environ={}) == EXIT_USAGE
    assert "--yes" in capsys.readouterr().err
    assert not (dst / "a.txt").exists()


def test_apply_into_new_target(tree, tmp_path):
    src = tree("src", {"f": "1", "d": {"g": "2"}})
    dst = tmp_path / "backup"
    assert run([src, dst, "--apply", "-y", "-q"]) == EXIT_OK
    assert (dst / "d" / "g").read_text() == "2"


def test_apply_failure_exit_code_with_fake(sample, monkeypatch, capsys):
    src, dst = sample
    import shutil

    def broken_copy(*a, **k):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(shutil, "copy2", broken_copy)
    assert run([src, dst, "--apply", "-y", "-q"]) == EXIT_APPLY_FAILED
    err = capsys.readouterr().err
    assert "error: copy a.txt: Permission denied" in err


def test_json_output(sample, capsys):
    src, dst = sample
    assert run([src, dst, "-f", "json"]) == EXIT_DIFFERENT
    data = json.loads(capsys.readouterr().out)
    assert data["in_sync"] is False
    assert {c["path"]: c["action"] for c in data["changes"]}["d.txt"] == "update"


def test_json_apply(sample, capsys):
    src, dst = sample
    assert run([src, dst, "-f", "json", "--apply", "-y"]) == EXIT_OK
    data = json.loads(capsys.readouterr().out)
    assert len(data["applied"]) == 4 and data["failed"] == []


def test_exclude_flag_and_env(sample, capsys):
    src, dst = sample
    args = [src, dst, "-e", "a.txt", "-e", "some-directory", "-e", "d.txt"]
    assert run(args, env={"COMPARATOR_EXCLUDE": "b.txt, "}) == EXIT_OK
    assert run(args) == EXIT_DIFFERENT  # b.txt is extra without the env exclude


def test_compare_mode_from_env(sample):
    src, dst = sample
    # d.txt differs in content but not in size
    args = [src, dst, "-e", "a.txt", "-e", "b.txt", "-e", "some-directory"]
    assert run(args, env={"COMPARATOR_COMPARE": "size"}) == EXIT_OK
    assert run(args) == EXIT_DIFFERENT
    assert run([*args, "--compare", "hash"], env={"COMPARATOR_COMPARE": "size"}) == EXIT_DIFFERENT


def test_algorithm_option(sample):
    src, dst = sample
    assert run([src, dst, "--algorithm", "md5"]) == EXIT_DIFFERENT
    assert run([src, dst], env={"COMPARATOR_ALGORITHM": "blake2b"}) == EXIT_DIFFERENT


@pytest.mark.parametrize(
    "argv_fn, env, message",
    [
        (lambda s, d: [s / "nope", d], {}, "source does not exist"),
        (lambda s, d: [s / "a.txt", d], {}, "source is not a directory"),
        (lambda s, d: [s, d / "c.txt"], {}, "target is not a directory"),
        (lambda s, d: [s, s], {}, "same directory"),
        (lambda s, d: [s, s / "some-directory"], {}, "nested"),
        (lambda s, d: [s / "some-directory", s], {}, "nested"),
        (lambda s, d: [s, d, "--algorithm", "md42"], {}, "unsupported hash algorithm"),
        (lambda s, d: [s, d], {"COMPARATOR_COMPARE": "bogus"}, "invalid compare mode"),
        (lambda s, d: [s, d], {"COMPARATOR_ALGORITHM": "nope"}, "unsupported hash algorithm"),
    ],
)
def test_usage_errors(sample, capsys, argv_fn, env, message):
    src, dst = sample
    assert run(argv_fn(src, dst), env=env) == EXIT_USAGE
    assert message in capsys.readouterr().err


def test_argparse_errors_exit_2(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["only-one-arg"])
    assert exc.value.code == 2
    with pytest.raises(SystemExit) as exc:
        main(["a", "b", "--compare", "nope"])
    assert exc.value.code == 2


def test_help_and_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    assert "--apply" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main(["--version"])
    assert "comparator" in capsys.readouterr().out


def test_python_dash_m_entry_point(sample):
    src, dst = sample
    proc = subprocess.run(
        [sys.executable, "-m", "comparator", str(src), str(dst), "-q"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == EXIT_DIFFERENT
    assert "differences found" in proc.stdout

"""Command line interface: preview by default, ``--apply`` to sync."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable, Mapping, Sequence

from comparator import __version__
from comparator.compare import CompareMode, build_plan, has_differences
from comparator.hashing import DEFAULT_ALGORITHM, file_hash, validate_algorithm
from comparator.models import Action, Change
from comparator.report import (
    display_path,
    format_apply_result,
    format_summary,
    format_table,
    to_json,
)
from comparator.scan import scan_tree
from comparator.sync import apply_plan

EXIT_OK = 0
EXIT_DIFFERENT = 1
EXIT_USAGE = 2
EXIT_APPLY_FAILED = 3

ENV_EXCLUDE = "COMPARATOR_EXCLUDE"
ENV_COMPARE = "COMPARATOR_COMPARE"
ENV_ALGORITHM = "COMPARATOR_ALGORITHM"

Confirm = Callable[[str], bool]


class UsageError(Exception):
    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="comparator",
        description=(
            "Compare SOURCE with TARGET and show what it would take to make TARGET "
            "mirror SOURCE. Nothing is changed unless --apply is given."
        ),
        epilog=(
            "exit codes: 0 in sync / applied, 1 differences found (or apply declined), "
            "2 usage error, 3 some operations failed.  "
            f"environment: {ENV_EXCLUDE} (comma separated globs), "
            f"{ENV_COMPARE}, {ENV_ALGORITHM}."
        ),
    )
    parser.add_argument("source", help="directory to copy from")
    parser.add_argument("target", help="directory to copy to (created on --apply if missing)")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="perform the copy/update/mkdir (and --delete) actions; asks first unless --yes",
    )
    parser.add_argument("-y", "--yes", action="store_true", help="do not ask for confirmation")
    parser.add_argument(
        "--delete",
        action="store_true",
        help="plan deletion of entries that exist only in TARGET (default: just report them)",
    )
    parser.add_argument(
        "-c",
        "--compare",
        choices=[m.value for m in CompareMode],
        default=None,
        help=f"how to decide two files are equal (default: hash, env {ENV_COMPARE})",
    )
    parser.add_argument(
        "--algorithm",
        default=None,
        help=f"hash algorithm for --compare hash (default: {DEFAULT_ALGORITHM}, env {ENV_ALGORITHM})",
    )
    parser.add_argument(
        "-e",
        "--exclude",
        action="append",
        default=[],
        metavar="GLOB",
        help="skip paths matching GLOB (whole relative path or any component); repeatable",
    )
    parser.add_argument(
        "-a", "--all", action="store_true", dest="show_same", help="also list unchanged entries"
    )
    parser.add_argument(
        "-f", "--format", choices=["table", "json"], default="table", help="output format"
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="table format: print only the summary line"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def resolve_settings(args: argparse.Namespace, environ: Mapping[str, str]) -> None:
    """Fill unset options from the environment and validate them (in place)."""
    env_excludes = [p for p in environ.get(ENV_EXCLUDE, "").split(",") if p.strip()]
    args.exclude = [*env_excludes, *args.exclude]

    compare = args.compare or environ.get(ENV_COMPARE) or CompareMode.HASH.value
    try:
        args.compare = CompareMode(compare.strip().lower())
    except ValueError:
        choices = ", ".join(m.value for m in CompareMode)
        raise UsageError(f"invalid compare mode {compare!r} (choose from {choices})") from None

    algorithm = args.algorithm or environ.get(ENV_ALGORITHM) or DEFAULT_ALGORITHM
    try:
        args.algorithm = validate_algorithm(algorithm)
    except ValueError as exc:
        raise UsageError(str(exc)) from None


def validate_paths(source: str, target: str) -> tuple[str, str]:
    src = os.path.abspath(os.path.expanduser(source))
    dst = os.path.abspath(os.path.expanduser(target))
    if not os.path.exists(src):
        raise UsageError(f"source does not exist: {source}")
    if not os.path.isdir(src):
        raise UsageError(f"source is not a directory: {source}")
    if os.path.exists(dst) and not os.path.isdir(dst):
        raise UsageError(f"target is not a directory: {target}")
    real_src, real_dst = os.path.realpath(src), os.path.realpath(dst)
    if real_src == real_dst:
        raise UsageError("source and target are the same directory")
    if real_dst.startswith(real_src + os.sep) or real_src.startswith(real_dst + os.sep):
        raise UsageError("source and target must not be nested inside each other")
    return src, dst


def make_content_equal(source: str, target: str, algorithm: str) -> Callable[[str], bool]:
    def content_equal(rel: str) -> bool:
        parts = rel.split("/")
        try:
            return file_hash(os.path.join(source, *parts), algorithm) == file_hash(
                os.path.join(target, *parts), algorithm
            )
        except OSError:
            return False  # unreadable: report as different, apply will surface the error

    return content_equal


def default_confirm(prompt: str) -> bool:
    if not sys.stdin or not sys.stdin.isatty():
        raise UsageError("refusing to apply without confirmation on a non-interactive stdin; pass --yes")
    sys.stderr.write(prompt)
    sys.stderr.flush()
    answer = sys.stdin.readline().strip().lower()
    return answer in {"y", "yes"}


def _print_change(change: Change) -> None:
    print(f"{change.action.value:<7} {display_path(change)}")


def run(args: argparse.Namespace, environ: Mapping[str, str], confirm: Confirm) -> int:
    resolve_settings(args, environ)
    source, target = validate_paths(args.source, args.target)

    plan = build_plan(
        scan_tree(source, args.exclude),
        scan_tree(target, args.exclude),
        mode=args.compare,
        content_equal=make_content_equal(source, target, args.algorithm),
        delete=args.delete,
    )
    actionable = [c for c in plan if c.action.mutates]
    as_json = args.format == "json"

    if not args.apply:
        if as_json:
            print(to_json(plan, source=source, target=target, show_same=args.show_same))
        else:
            if not args.quiet:
                print(format_table(plan, args.show_same))
            print(format_summary(plan))
        return EXIT_DIFFERENT if has_differences(plan) else EXIT_OK

    if not as_json:
        if not args.quiet:
            print(format_table(plan, args.show_same))
        print(format_summary(plan))

    if not actionable:
        if as_json:
            print(to_json(plan, source=source, target=target, show_same=args.show_same))
        else:
            print("Nothing to apply.")
        return EXIT_OK

    if not args.yes and not confirm(f"Apply {len(actionable)} change(s) to {target}? [y/N] "):
        print("Aborted, nothing changed.", file=sys.stderr)
        return EXIT_DIFFERENT

    result = apply_plan(plan, source, target, on_change=None if as_json else _print_change)
    if as_json:
        print(to_json(plan, source=source, target=target, show_same=args.show_same, result=result))
    else:
        for change, error in result.failed:
            print(f"error: {change.action.value} {display_path(change)}: {error}", file=sys.stderr)
        print(format_apply_result(result))
        if any(c.action is Action.CONFLICT for c in plan):
            print("warning: conflicts were left untouched", file=sys.stderr)
    return EXIT_OK if result.ok else EXIT_APPLY_FAILED


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    confirm: Confirm | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args, os.environ if environ is None else environ, confirm or default_confirm)
    except UsageError as exc:
        print(f"comparator: error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

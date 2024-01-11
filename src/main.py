import argparse
import datetime
import filecmp
import hashlib
import os
import shutil
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from itertools import chain
from operator import attrgetter, itemgetter
from typing import Callable, Union

from prettytable import PrettyTable


IS_DEMO = True


class Action(Enum):
    COPY = "copy"
    MODIFY = "modify"
    NO_ACTION = "no_action"

    def get_name(self):
        return chr(32).join(map(str.capitalize, self.value.split("_")))

    @classmethod
    def mutation_options(cls):
        return {cls.COPY, cls.MODIFY}


@dataclass
class Result:
    source_path: str
    target_path: str
    action: Action

    @staticmethod
    def headers():
        return ["Source Path", "Target Path", "Action"]

    def as_tuple(self):
        return (self.source_path, self.target_path, self.action)


@dataclass
class FileMetadata:
    file_extension: str
    file_size: int
    file_hash: str

    def as_tuple(self):
        return (self.file_extension, self.file_size, self.file_hash)


def compare_directories(source_dir, target_dir):
    results = []

    for root, dirs, files in os.walk(source_dir):
        for file in files:
            source_path = os.path.join(root, file)
            target_path = os.path.join(
                target_dir,
                os.path.relpath(source_path, source_dir),
            )

            if os.path.isfile(target_path):
                source_metadata = get_file_metadata(source_path).as_tuple()
                target_metadata = get_file_metadata(target_path).as_tuple()

                if source_metadata == target_metadata:
                    action = Action.NO_ACTION
                else:
                    action = Action.MODIFY
            else:
                action = Action.COPY

            results.append(Result(source_path, target_path, action))

    return results


def get_file_metadata(file_path):
    file_extension = os.path.splitext(file_path)[1]
    file_size = os.path.getsize(file_path)
    file_hash = get_file_hash(file_path)

    return FileMetadata(file_extension, file_size, file_hash)


def get_file_hash(file_path, algorithm="sha256", block_size=4096):
    assert hasattr(hashlib, algorithm)
    hash_obj = getattr(hashlib, algorithm)
    hash_obj = hash_obj()

    with open(file_path, "rb") as file:
        for chunk in iter(lambda: file.read(block_size), b""):
            hash_obj.update(chunk)

    return hash_obj.hexdigest()


def group_by(things, grouper: Union[str, Callable[[object], object]]):
    if type(grouper) == str:
        grouper = attrgetter(grouper)
    elif not callable(grouper):
        raise TypeError("grouper arg is not a valid callable")

    grouped = defaultdict(list)
    for thing in things:
        grouped[grouper(thing)].append(thing)
    return grouped


def do_action(results, dry_run=True):
    grouped = group_by(results, itemgetter(2))

    to_be_skipped = grouped.get(Action.NO_ACTION, [])

    if to_be_skipped:
        for source_path, target_path, _ in to_be_skipped:
            print(f"No action: {source_path}")

    for source_path, target_path, action in chain(*map(
        lambda key: grouped.get(key, []),
        Action.mutation_options()
    )):
        out = f"{action.get_name()}: {source_path} -> {target_path}"
        if dry_run:
            out += " (dry run)"
        else:
            shutil.copy2(source_path, target_path)
        print(out)


def are_directories_equal(dir1, dir2):
    comparison = filecmp.dircmp(dir1, dir2, ignore=None, shallow=False)

    if any(
        getattr(comparison, attr)
        for attr
        in ("left_only", "right_only", "diff_files", "funny_files")
    ):
        return False

    for common_dir in comparison.common_dirs:
        new_dir1 = os.path.join(dir1, common_dir)
        new_dir2 = os.path.join(dir2, common_dir)
        if not are_directories_equal(new_dir1, new_dir2):
            return False

    return True


def cli():
    parser = argparse.ArgumentParser(
        description="Compare two directories and display the results in a table.",
    )

    parser.add_argument("source_dir", help="Path to the source directory")
    parser.add_argument("target_dir", help="Path to the target directory")
    parser.add_argument("-d", "--dry-run",
        action="store_true",
        help="Don't apply changes, just show what will be done",
    )

    return parser.parse_args()


def to_bool(obj, include_human_parseable=True):
    falsy = [
        0, 0.0, 0j,
        "",
        False, None,
        list(), set(), tuple(), dict(), range(0),
    ]
    if include_human_parseable:
        more_falsy = [
            "n", "no", "not",
            "0", "0.0",
            "-",
            "false",
            "void",
            "null", "nil", "none",
        ]
        falsy.extend(more_falsy)
    if type(obj) is str:
        obj = obj.strip().lower()
    if obj in falsy:
        return False
    try:
        return bool(obj)
    except:
        return False


def main():

    if not IS_DEMO:
        args = cli()
    else:
        root_dir = os.path.dirname(__file__)
        resolve_dir = lambda directory: os.path.abspath(
            os.path.join(root_dir, directory)
        )

        from types import SimpleNamespace
        args = SimpleNamespace(
            source_dir=resolve_dir("dir1"),
            target_dir=resolve_dir("dir2"),
            dry_run=True,
        )

    results = compare_directories(args.source_dir, args.target_dir)
    results = [r.as_tuple() for r in results]

    table = PrettyTable(Result.headers())
    for result in results:
        table.add_row(result)

    print(table)

    passed_dry_run = getattr(args, "dry_run", False)
    if not passed_dry_run:
        user_choice = input("Dry run? (yes/no): ")
        do_action(results, to_bool(user_choice))
    else:
        do_action(results)


if __name__ == "__main__":
    main()

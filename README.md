# comparator

Compare a **source** directory with a **target** directory and see exactly what it would
take to make the target mirror the source: which files must be copied, which differ and
must be updated, which directories are missing, and what exists only in the target.
Nothing is touched until you pass `--apply`. Think of it as a tiny, previewable,
one-way `rsync` for backups and mirrors, with no dependencies beyond the Python
standard library.

## Install

Requires Python 3.10+.

```bash
python3 -m venv .venv
.venv/bin/pip install -e .          # or: pip install -e '.[dev]' for pytest
```

This installs a `comparator` command; `python -m comparator` works too.

## Usage

```
comparator SOURCE TARGET [--apply [-y]] [--delete] [-c {hash,mtime,size}]
           [--algorithm NAME] [-e GLOB ...] [-a] [-f {table,json}] [-q]
```

Preview (the default) using the sample trees in `examples/`:

```console
$ comparator examples/dir1 examples/dir2 --all
Action  Path                       Details
------  -------------------------  -----------------
Copy    a.txt                      missing in target
Extra   b.txt                      only in target
Same    c.txt
Update  d.txt                      content differs
Mkdir   some-directory/            missing in target
Copy    some-directory/nested.txt  missing in target
2 to copy, 1 dir(s) to create, 1 to update, 1 only in target, 1 unchanged (differences found)
$ echo $?
1
```

Apply it, also deleting what is only in the target (on a scratch copy of the samples):

```console
$ comparator dir1 dir2 --apply --yes --delete -q
2 to copy, 1 dir(s) to create, 1 to update, 1 to delete, 1 unchanged (differences found)
delete  b.txt
copy    a.txt
update  d.txt
mkdir   some-directory/
copy    some-directory/nested.txt
Applied 5 change(s).
$ comparator dir1 dir2
(no differences)
5 unchanged (in sync)
```

Without `--yes`, `--apply` asks `Apply N change(s) to TARGET? [y/N]` and refuses to run
when stdin is not a terminal. A missing target directory is created on `--apply`, so
`comparator photos /mnt/backup/photos --apply -y` works for a first backup.

Machine-readable output and excludes:

```console
$ comparator dir1 dir2 -e '*.txt' -f json
{
  "source": ".../dir1",
  "target": ".../dir2",
  "in_sync": true,
  "summary": {"copy": 0, "mkdir": 0, "update": 0, "same": 1, "extra": 0, "delete": 0, "conflict": 0},
  "changes": []
}
```

(`summary` shortened onto one line here.) Bad input gives a one-line error and exit code 2:

```console
$ comparator dir1 dir1/some-directory
comparator: error: source and target must not be nested inside each other
```

### Options

| Option | Meaning |
| --- | --- |
| `--apply` | Perform copy / update / mkdir (and delete with `--delete`). Asks first. |
| `-y`, `--yes` | Skip the confirmation prompt. |
| `--delete` | Plan deletion of target-only entries (otherwise they are reported as `Extra` and kept). |
| `-c`, `--compare` | `hash` (default): same size and same digest. `mtime`: same size and modification time within 1 s (fast). `size`: same size only. |
| `--algorithm` | Any fixed-length `hashlib` algorithm (default `sha256`). |
| `-e`, `--exclude GLOB` | Skip paths whose relative path, a parent path, or any component matches the glob (`*.tmp`, `__pycache__`, `build/out`). Repeatable. Excluded entries are never copied or deleted. |
| `-a`, `--all` | Also list unchanged entries. |
| `-f`, `--format` | `table` (default) or `json`. |
| `-q`, `--quiet` | Table format: print only the summary line. |

### Exit codes

`0` trees in sync / apply succeeded, `1` differences found (or apply declined),
`2` usage error (bad paths, bad options), `3` some operations failed during apply
(each failure is printed to stderr; the rest still ran).

### Configuration via environment

| Variable | Effect |
| --- | --- |
| `COMPARATOR_EXCLUDE` | Comma-separated globs, added to any `--exclude` flags. |
| `COMPARATOR_COMPARE` | Default for `--compare`. |
| `COMPARATOR_ALGORITHM` | Default for `--algorithm`. |

Command line flags win over the environment.

## Design

```
scan.py     filesystem -> snapshot {relative/path: Entry(kind, size, mtime)}
compare.py  two snapshots -> sorted list[Change]           (pure, no I/O)
sync.py     list[Change] -> filesystem writes, ApplyResult  (the only writer)
report.py   changes/results -> table, summary, JSON         (pure)
cli.py      argparse, env config, path validation, confirmation, exit codes
hashing.py  chunked file digests
```

- Each relative path gets exactly one `Action`: `copy`, `mkdir`, `update`, `same`,
  `extra`, `delete` or `conflict` (a file in one tree and a directory in the other;
  everything below it is also marked as conflict and left alone).
- The planner never reads files itself. Hash mode calls an injected `content_equal(path)`
  and only for files whose sizes already match.
- Apply order: deletions deepest-first, then directories and files parents-first.
  Parent directories are created as needed, `shutil.copy2` keeps timestamps and modes,
  and directories are removed with `rmdir`, so files hidden by `--exclude` are never
  deleted along with their directory.
- Paths in plans always use `/`, so the planner is platform independent.

## Tests

```bash
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```

All tests use `tmp_path` trees or in-memory snapshots; nothing outside the temp dir is touched.

## Known limitations

- One-way only: changes in the target are never copied back.
- Symbolic links are skipped in both trees (not followed, not copied, not deleted).
- No rename/move detection: a renamed file shows as one `copy` plus one `extra`/`delete`.
- Ownership, ACLs and extended attributes are not synced (only what `shutil.copy2` keeps).
- Not atomic: an interrupted `--apply` leaves a partially synced target; rerunning finishes it.
- Hash mode reads every same-size file pair fully; use `-c mtime` on large trees.
- Only tested on Linux; Windows path handling is written to work but is unverified.

## History

Version 0.1 (January 2024) was a single `src/main.py` prototype with a hard-coded demo
mode that always compared `src/dir1` with `src/dir2`. It was redesigned into this package;
the original is still in git history on `master`.

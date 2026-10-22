# comparator

> **DRAFT - assessment only. This README is unfinished on purpose; see "TODO" below.**

## What this seems to be

A small one-way directory sync tool ("compare, then copy what's missing or changed").
Given a *source* and a *target* directory, `src/main.py` walks the source tree, compares
every file with the file at the same relative path in the target (extension + size +
SHA-256 hash), prints a table of what it would do (`Copy`, `Modify`, `No Action`) and then
optionally copies files over with `shutil.copy2`. Think of a tiny, previewable
`rsync --dry-run` for backups/mirroring. `src/dir1` and `src/dir2` are sample trees.

## Current state (single commit, January 2024)

What works:

- Walking the source tree, hashing files in chunks, classifying files as copy / modify /
  no action, and printing a `prettytable` summary.
- Dry-run output of the planned actions.

What is broken or missing:

- `IS_DEMO = True` is hard-coded, so the argparse CLI is never used: it always compares
  `src/dir1` against `src/dir2` and always runs as a dry run.
- When not a dry run, it asks an inverted-sounding question ("Dry run? (yes/no)") via
  `input()`; non-interactive use is impossible.
- Copying into a nested path that does not exist in the target crashes
  (`shutil.copy2` without creating parent directories).
- Files that exist only in the target are silently ignored; empty directories are ignored.
- `some-directory` in the sample is actually an empty *file* (git cannot track empty dirs).
- The table prints `Action.COPY` (enum repr) and absolute paths; action order is
  nondeterministic (iterates a `set`).
- `are_directories_equal()` is dead code; exit code is always 0.
- Packaging: Poetry stub with no entry point, no package, no tests.
- No secrets or personal paths in the code.

## TODO / to be finished

- [ ] Redesign as a proper package with a real CLI
- [ ] Install / usage / config docs
- [ ] Tests

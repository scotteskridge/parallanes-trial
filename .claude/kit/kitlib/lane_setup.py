"""`kit lanes create` and `kit lanes remove`: making and removing lane worktrees (decisions 35, 39, 45)."""

import filecmp
import os
import shutil
import subprocess
from pathlib import Path

from .lanes import (
    LaneError,
    find_lane,
    git,
    integration_tip,
    is_nested,
    is_registered,
    lane_folder,
    locate,
    main_checkout,
    registered_worktrees,
    same_path,
    toplevel,
    worktree_root,
)
from .settings import SettingsError, Style, read_json, style_of, write_json

LOCAL_SETTINGS_REL = Path(".claude") / "settings.local.json"
# The main checkout's instruction files. Claude Code loads every CLAUDE.md from the session folder up
# to the filesystem root, so a nested lane would also read these (decision 35).
INSTRUCTION_FILES = ("CLAUDE.md", "AGENTS.md", ".claude/CLAUDE.md")


class PartialCreate(LaneError):
    """Some lanes failed; lines still says what happened to every lane."""

    def __init__(self, message: str, lines: list[str]):
        super().__init__(message)
        self.lines = lines


# ---- create ------------------------------------------------------------------------------------


def _selected(config, names) -> list:
    if not config.lanes:
        raise LaneError("no lanes defined: add [[lanes]] tables to .claude/kit.toml")
    return [find_lane(config, name) for name in names] if names else list(config.lanes)


def create(start: Path, config, names=(), dry_run: bool = False) -> list[str]:
    """Create the named lanes (all when none are named). Returns one line per lane."""
    main = main_checkout(start)
    selected = _selected(config, names)
    tip = integration_tip(main, config)
    if tip is None:
        branch = config.lane_settings.integration_branch
        raise LaneError(f"integration branch {branch!r} not found (neither origin/{branch} nor {branch})")
    root = worktree_root(main, config)
    if is_nested(main, root):
        rel = Path(os.path.relpath(root, main)).as_posix()
        # A folder that isn't ignored shows up as an untracked nested repository in every `git status`.
        if _not_ignored(main, f"{rel}/x"):
            raise LaneError(
                f"{rel}/ is not gitignored. Add this line to .gitignore, commit it, then run this again:\n  {rel}/"
            )

    registered = registered_worktrees(main)
    include = [] if dry_run else _worktreeinclude_files(main, root)
    lines, errors = [], []
    # Every lane is attempted and reported, so a rerun after a fix finishes the job.
    for lane in selected:
        folder = lane_folder(main, config, lane)
        known = any(same_path(path, folder) for path in registered)
        exists = known and folder.is_dir()
        try:
            if known and not exists:
                raise LaneError(f"registered, but {folder} is missing; run `git worktree prune`, then create again")
            if not exists and folder.exists():
                raise LaneError(f"{folder} exists but is not this lane's worktree; move it away first")
            if dry_run:
                lines.append(
                    f"{lane.name}: "
                    + (f"already created at {folder}" if exists else f"would create {folder}, detached at {tip}")
                )
                continue
            if not exists:
                git(main, "worktree", "add", "--detach", str(folder), tip)
                _check_traceable(main, folder)
            # Reported once the worktree exists: a later step's failure is an error of its own.
            lines.append(
                f"{lane.name}: "
                + (f"already created at {folder}" if exists else f"created {folder}, detached at {tip}")
            )
            # On a rerun this copies only what is missing (a failed run's leftovers), never overwriting.
            _copy(main, folder, include)
            if is_nested(main, folder):
                exclude_main_instructions(main, folder)
        except LaneError as error:
            errors.append(f"{lane.name}: {error}")
    if errors:
        raise PartialCreate("\n".join(errors), lines)
    return lines


def _check_traceable(main: Path, folder: Path) -> None:
    """Undo a lane that its hooks couldn't trace back to the main checkout (a separate git dir)."""
    try:
        found = locate(folder)[1]
    except LaneError as error:
        found, reason = None, str(error)
    else:
        reason = f"the lane resolves to {found} instead of {main}"
    if found is not None and same_path(found, main):
        return
    git(main, "worktree", "remove", "--force", str(folder))
    raise LaneError(f"not created: {reason}. Lanes need a normal checkout (docs/ai/parallel-lanes.md)")


def _copy(main: Path, folder: Path, include: list[str]) -> None:
    failed = []
    for rel in include:
        target = folder / rel
        if target.exists():
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(main / rel, target)
        except OSError as error:
            failed.append(f"{rel} ({error})")
    if failed:
        raise LaneError(f"couldn't copy into the lane: {', '.join(failed)}; fix it and run create again")


def _not_ignored(main: Path, rel: str) -> bool:
    try:
        result = subprocess.run(["git", "check-ignore", "-q", rel], cwd=main, capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as error:
        raise LaneError(f"git check-ignore: {error}") from None
    if result.returncode not in (0, 1):
        raise LaneError(f"git check-ignore failed: {result.stderr.decode('utf-8', 'replace').strip()}")
    return result.returncode == 1


def _worktreeinclude_files(main: Path, root: Path) -> list[str]:
    """Files that match `.worktreeinclude` and are gitignored, as Claude Code copies them.

    git does the matching, so it is exactly gitignore syntax. Other lanes' folders are skipped.
    """
    if not (main / ".worktreeinclude").is_file():
        return []
    args = ["ls-files", "-z", "--others", "--ignored", "--exclude-from=.worktreeinclude"]
    if is_nested(main, root):
        args += ["--", ".", f":(exclude){Path(os.path.relpath(root, main)).as_posix()}"]
    listed = [name for name in git(main, *args).split("\0") if name]
    if not listed:
        return []
    result = subprocess.run(
        ["git", "check-ignore", "-z", "--stdin"],
        cwd=main,
        input="\0".join(listed).encode("utf-8"),
        capture_output=True,
        timeout=60,
    )
    if result.returncode not in (0, 1):
        raise LaneError(f"git check-ignore failed: {result.stderr.decode('utf-8', 'replace').strip()}")
    ignored = {name for name in result.stdout.decode("utf-8", "replace").split("\0") if name}
    return [name for name in listed if name in ignored and (main / name).is_file()]


def exclude_main_instructions(main: Path, folder: Path) -> None:
    """Add the main checkout's instruction files to the lane's claudeMdExcludes (decision 35).

    `settings.local.json` is gitignored and specific to this machine, the right home for absolute
    paths. Other keys and the file's formatting are kept; an unreadable file is left alone.
    """
    path = folder / LOCAL_SETTINGS_REL
    what = f"{folder.name}/{LOCAL_SETTINGS_REL.as_posix()}"
    try:
        data = read_json(path, what)
    except SettingsError as error:
        raise LaneError(
            f"{error}. The lane was created; add claudeMdExcludes by hand (docs/ai/parallel-lanes.md)"
        ) from None
    excludes = data.get("claudeMdExcludes", [])
    if not isinstance(excludes, list):
        raise LaneError(f"{what}: 'claudeMdExcludes' must be a list; left untouched")
    added = [entry for entry in main_instruction_excludes(main) if entry not in excludes]
    if added:
        data["claudeMdExcludes"] = excludes + added
        try:
            write_json(path, data, style_of(path) if path.is_file() else Style())
        except OSError as error:
            raise LaneError(f"{what}: can't write it: {error}") from None


def main_instruction_excludes(main: Path) -> list[str]:
    return [Path(os.path.realpath(main / name)).as_posix() for name in INSTRUCTION_FILES]


# ---- remove ------------------------------------------------------------------------------------


def remove(start: Path, config, name: str, force: bool = False) -> str:
    lane = find_lane(config, name)
    main = main_checkout(start)
    folder = lane_folder(main, config, lane)
    if not is_registered(main, folder):
        raise LaneError(f"{name}: not created ({folder} is not a worktree of this repository)")
    top = toplevel(Path(start))
    if top is not None and same_path(top, folder):
        raise LaneError(f"{name}: can't remove the lane this command runs in; run it from another folder")
    changes = git(folder, "status", "--porcelain").splitlines()
    if changes:
        raise LaneError(f"{name}: {len(changes)} uncommitted change(s) in {folder}; commit or discard them first")
    if not force:
        # git ignores ignored files, but they can hold work: a lane's .env, its local settings.
        kept = ignored_work(main, folder)
        if kept:
            shown = ", ".join(kept[:10]) + (f" and {len(kept) - 10} more" if len(kept) > 10 else "")
            raise LaneError(
                f"{name}: removing {folder} would delete ignored files: {shown}. "
                "Save what you need, then run again with --force"
            )
    git(main, "worktree", "remove", *(["--force"] if force else []), str(folder))
    return f"{name}: removed {folder}"


def ignored_work(main: Path, folder: Path) -> list[str]:
    """Ignored files and folders in the lane that may hold work (decision 45).

    Not counted: caches any tool rebuilds, and what matches the main checkout's current copy (what
    `create` copied in, unchanged), including the `claudeMdExcludes` it added.
    """
    out = git(folder, "ls-files", "-z", "--others", "--ignored", "--exclude-standard", "--directory")
    lost = []
    for rel in (name for name in out.split("\0") if name):
        if rel.endswith("/") and rel.rstrip("/").rsplit("/", 1)[-1] in REBUILT_FOLDERS:
            continue  # a whole cache folder; a file inside work that merely has such a name still counts
        mine, original = folder / rel, main / rel
        if rel == LOCAL_SETTINGS_REL.as_posix() and _only_our_excludes(main, mine, original):
            continue
        try:
            if _same_content(mine, original):
                continue
        except OSError:
            pass  # can't read it: it may hold work, so it is listed

        lost.append(rel)
    return lost


# Folders tools rebuild on demand: deleting them loses no work, and counting them would make
# `remove --force` routine, which defeats the check.
REBUILT_FOLDERS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules", ".venv", "venv"}


def _same_content(mine: Path, original: Path) -> bool:
    """A file with the same bytes, or a folder whose every file has a same-bytes original."""
    if mine.is_file():
        return original.is_file() and _identical_files(mine, original)
    if not mine.is_dir() or not original.is_dir():
        return False
    return all(path.is_dir() or _same_content(path, original / path.relative_to(mine)) for path in mine.rglob("*"))


def _identical_files(a: Path, b: Path) -> bool:
    # Size first, then chunked: an included model or dataset may be gigabytes.
    return a.stat().st_size == b.stat().st_size and filecmp.cmp(a, b, shallow=False)


def _only_our_excludes(main: Path, mine: Path, original: Path) -> bool:
    """The lane's settings.local.json differs from the main checkout's only by create's excludes."""
    try:
        data = read_json(mine, mine.name)
        before = read_json(original, original.name)
    except SettingsError:
        return False
    ours = set(main_instruction_excludes(main))
    excludes = [entry for entry in data.get("claudeMdExcludes", []) if entry not in ours]
    data = {key: value for key, value in data.items() if key != "claudeMdExcludes"}
    if excludes:
        data["claudeMdExcludes"] = excludes
    return data == before

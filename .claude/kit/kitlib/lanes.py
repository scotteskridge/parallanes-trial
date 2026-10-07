"""Lanes: one git worktree per lane, found from the config and git alone (decisions 11, 35-39, 42, 43).

No state file: a folder is a lane when its git top level is `<main checkout>/<worktree_root>/<name>`,
so nothing can go stale. Creating and removing lanes is in `lane_setup.py`, their status in `lane_status.py`,
the task cycle in `lane_cycle.py`.
"""

import os
import subprocess
from pathlib import Path


class LaneError(Exception):
    """A lanes command can't go ahead; the message says why and what to do."""


class Unfinished(LaneError):
    """The work is mid-way, not untouched: tests failed, a conflict waits, or a push or PR failed (exit 1)."""


def git(folder: Path, *args: str, check: bool = True) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=folder,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise LaneError(f"git {' '.join(args)}: {error}") from None
    if check and result.returncode != 0:
        raise LaneError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout if result.returncode == 0 else ""


def run_git(top: Path, *args: str, timeout: int = 300) -> subprocess.CompletedProcess:
    """git with its exit code, for the steps whose failure has its own message."""
    try:
        return subprocess.run(
            ["git", *args], cwd=top, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise LaneError(f"git {' '.join(args)}: {error}") from None


def same_path(a: Path, b: Path) -> bool:
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def toplevel(folder: Path) -> Path | None:
    out = git(folder, "rev-parse", "--show-toplevel", check=False).strip()
    return Path(out) if out else None


def locate(folder: Path) -> tuple[Path | None, Path | None]:
    """(git top level of folder, main checkout); (None, None) outside a working tree. One git call
    in the common case, because the hooks run this on every session start and edit."""
    out = git(
        folder, "rev-parse", "--path-format=absolute", "--show-toplevel", "--git-dir", "--git-common-dir", check=False
    ).splitlines()
    if not out:
        return None, None  # outside git, or a bare repository (no top level)
    if len(out) != 3:
        # An older git echoes `--path-format=absolute` back instead of failing: say so, don't go quiet.
        raise LaneError("unexpected output from git rev-parse: lanes need git 2.36 or newer")
    top, git_dir, common = (Path(line) for line in out)
    if same_path(git_dir, common):
        return top, top  # this is the main checkout (also a submodule's own checkout)
    return top, _main_from_linked(folder, common)


def _main_from_linked(folder: Path, common: Path) -> Path:
    """The main checkout seen from a linked worktree (a lane).

    git lists it first in `worktree list`; a submodule's worktrees name it in `core.worktree`. With a
    separate git dir git lists the git dir itself, so a candidate counts only if it has the kit's
    config checked out, as every main checkout of a project with lanes does. No match is an error,
    never a guess.
    """
    first = git(folder, "worktree", "list", "--porcelain", "-z").split("\0\0")[0].split("\0")
    candidates = (
        [Path(first[0][len("worktree ") :])] if first[0].startswith("worktree ") and "bare" not in first else []
    )
    configured = git(folder, "config", "--file", str(common / "config"), "--get", "core.worktree", check=False).strip()
    if configured:
        candidates.append(Path(os.path.normpath(common / configured)))
    candidates = [candidate for candidate in candidates if not same_path(candidate, common)]
    for candidate in candidates:
        if (candidate / ".claude" / "kit.toml").is_file():
            return candidate
    if candidates and (candidates[0] / ".git").exists():
        raise LaneError(
            f"the main checkout {candidates[0]} has no .claude/kit.toml checked out (is it on a commit from "
            "before the kit, or is this a separate git dir?); lanes need it there"
        )
    raise LaneError(
        "can't find the main checkout from this worktree (the repository is bare or uses a separate "
        "git dir); lanes need a normal checkout"
    )


def main_checkout(folder: Path) -> Path:
    """The main working tree, found from any folder of the repository (a lane included)."""
    _, main = locate(folder)
    if main is None:
        raise LaneError(f"{folder} is not inside a git working tree (lanes need one)")
    return main


def worktree_root(main: Path, config) -> Path:
    name = config.project.get("name") or main.name
    root = config.lane_settings.worktree_root.replace("{project}", name)
    return Path(os.path.normpath(main / root))


def lane_folder(main: Path, config, lane) -> Path:
    return worktree_root(main, config) / lane.name


def is_nested(main: Path, folder: Path) -> bool:
    try:
        Path(os.path.normcase(os.path.abspath(folder))).relative_to(os.path.normcase(os.path.abspath(main)))
    except ValueError:
        return False
    return True


def current_lane(folder: Path, config):
    """The lane whose worktree contains folder, or None (the main checkout, or any other folder)."""
    return find_current(folder, config)[0]


def find_current(folder: Path, config):
    """(lane or None, git top level, main checkout) for folder."""
    top, main = locate(Path(folder))
    if top is None or same_path(top, main):
        return None, top, main
    lane = next((lane for lane in config.lanes if same_path(top, lane_folder(main, config, lane))), None)
    return lane, top, main


def find_lane(config, name: str):
    for lane in config.lanes:
        if lane.name == name:
            return lane
    known = ", ".join(lane.name for lane in config.lanes) or "none"
    raise LaneError(f"no lane named {name!r} in .claude/kit.toml (lanes: {known})")


def integration_tip(folder: Path, config) -> str | None:
    """Where finished work lands: PR mode prefers `origin/<integration>`, local mode the local
    branch (ARCHITECTURE §6); each falls back to the other. None if neither exists.

    No fetch: everything here works offline (decision 39).
    """
    branch = config.lane_settings.integration_branch
    refs = (f"origin/{branch}", branch)
    if config.lane_settings.merge_mode == "local":
        refs = refs[::-1]
    for ref in refs:
        if git(folder, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}", check=False).strip():
            return ref
    return None


def is_ancestor(folder: Path, commit: str, of: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit, of], cwd=folder, capture_output=True, timeout=60
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise LaneError(f"git merge-base: {error}") from None
    if result.returncode not in (0, 1):
        raise LaneError(f"git merge-base --is-ancestor failed: {result.stderr.decode('utf-8', 'replace').strip()}")
    return result.returncode == 0


def registered_worktrees(main: Path) -> list[Path]:
    out = git(main, "worktree", "list", "--porcelain", "-z")
    return [Path(entry[len("worktree ") :]) for entry in out.split("\0") if entry.startswith("worktree ")]


def is_registered(main: Path, folder: Path) -> bool:
    return any(same_path(path, folder) for path in registered_worktrees(main))


# ---- state of one folder ------------------------------------------------------------------------


def branch_of(folder: Path) -> str | None:
    name = git(folder, "rev-parse", "--abbrev-ref", "HEAD").strip()
    return None if name == "HEAD" else name


def ahead_behind(folder: Path, tip: str) -> tuple[int, int]:
    out = git(folder, "rev-list", "--left-right", "--count", f"HEAD...{tip}").split()
    return int(out[0]), int(out[1])


def changes(folder: Path) -> tuple[int, list[str]]:
    """(tracked changes, untracked paths): only tracked changes are unfinished work (decision 52).

    One `git status` (each git call costs ~35 ms on Windows). -z: names as they are, not git's
    quoted octal form; a rename's second entry is its old name, with no status prefix.
    """
    entries = iter(git(folder, "status", "--porcelain", "-z", "--untracked-files=normal").split("\0"))
    tracked, untracked = 0, []
    for entry in entries:
        if entry.startswith("?? "):
            untracked.append(entry[3:])
        elif entry:
            tracked += 1
            if entry[0] in "RC" or entry[1] in "RC":  # staged, or in the worktree (`add -N` then rename)
                next(entries, None)
    return tracked, untracked


def unpushed_count(folder: Path) -> int | None:
    if not git(folder, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", check=False).strip():
        return None
    return int(git(folder, "rev-list", "--count", "@{u}..HEAD").strip())


def upstream_gone(folder: Path) -> bool:
    """The branch was pushed, but its remote branch is gone (usually: PR merged, head branch deleted)."""
    ref = git(folder, "symbolic-ref", "-q", "HEAD", check=False).strip()
    return bool(ref) and git(folder, "for-each-ref", "--format=%(upstream:track)", ref).strip() == "[gone]"

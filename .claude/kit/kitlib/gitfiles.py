"""Which files to check, and their text: from disk, from the git index, or changed since a base."""

import subprocess
from pathlib import Path

_SNIFF = 8192  # bytes looked at to decide whether a file is binary


class GitError(Exception):
    """A git command failed; the message includes git's own error."""


def _git(root: Path, *args: str) -> bytes:
    try:
        result = subprocess.run(["git", *args], cwd=root, capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as error:
        raise GitError(f"git {' '.join(args)}: {error}") from None
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", "replace").strip()
        raise GitError(f"git {' '.join(args)} failed: {message}")
    return result.stdout


def _names(output: bytes) -> list[str]:
    return [name for name in output.decode("utf-8", "replace").split("\0") if name]


def decode(data: bytes) -> str | None:
    """Text of a file, or None for a binary file (a NUL byte near the start)."""
    if b"\0" in data[:_SNIFF]:
        return None
    return data.decode("utf-8-sig", "replace")


def tracked(root: Path) -> list[str]:
    return _names(_git(root, "ls-files", "-z"))


_REGULAR_FILE_MODES = {"100644", "100755"}  # not submodules (160000) or symlinks (120000)


def staged(root: Path) -> list[str]:
    """Regular files added, copied, modified or renamed in the index.

    Deleted files have nothing to check; submodules and symlinks have no text to read.
    """
    fields = _names(_git(root, "diff", "--cached", "--raw", "-z", "--diff-filter=ACMR"))
    paths = []
    i = 0
    while i < len(fields):
        # Each entry: ":oldmode newmode oldsha newsha status", then one path (two for R/C).
        meta = fields[i].lstrip(":").split(" ")
        new_mode, status = meta[1], meta[4]
        count = 2 if status[:1] in "RC" else 1
        path = fields[i + count]  # the new name for a rename or copy
        if new_mode in _REGULAR_FILE_MODES:
            paths.append(path)
        i += 1 + count
    return paths


def changed_since(root: Path, base: str) -> list[str]:
    """Files changed on this branch since it left base (merge-base diff, as a pull request sees it)."""
    return _names(_git(root, "diff", "--name-only", "--diff-filter=ACMR", "-z", f"{base}...HEAD"))


def touched_staged(root: Path) -> list[str]:
    """Every path the next commit adds, changes or deletes; a rename counts as both names."""
    return _names(_git(root, "diff", "--cached", "--name-only", "--no-renames", "-z"))


def touched_since(root: Path, base: str) -> list[str]:
    """Every path this branch added, changed or deleted since it left base (both names of a rename)."""
    return _names(_git(root, "diff", "--name-only", "--no-renames", "-z", f"{base}...HEAD"))


def current_branch(root: Path) -> str | None:
    """The checked-out branch, or None when HEAD is detached (as in CI).

    symbolic-ref, not `rev-parse --abbrev-ref`: it also works before the first commit, which is
    when the pre-commit hook runs on a new project.
    """
    result = _run(root, "symbolic-ref", "--quiet", "HEAD")
    if result.returncode == 1 and not result.stderr.strip():  # --quiet: exit 1, silent, means detached
        return None
    if result.returncode != 0:
        raise GitError(f"git symbolic-ref HEAD failed: {result.stderr.decode('utf-8', 'replace').strip()}")
    # The full name, not --short: that prints `heads/core/task` when a tag or remote shares the name.
    ref = result.stdout.decode("utf-8", "replace").strip()
    if not ref.startswith("refs/heads/"):
        raise GitError(f"HEAD points at {ref!r}, not a branch")
    return ref.removeprefix("refs/heads/")


def is_repo(root: Path) -> bool:
    return _run(root, "rev-parse", "--git-dir").returncode == 0


def has_ref(root: Path, ref: str) -> bool:
    return _run(root, "rev-parse", "--quiet", "--verify", ref + "^{commit}").returncode == 0


def touched_by_merge_commit(root: Path) -> list[str]:
    """During a merge, the paths the commit changes from both parents: the resolution and anything
    added to it, not what the merged branch brought in. Both names of a rename."""
    ours = set(_names(_git(root, "diff", "--cached", "--name-only", "--no-renames", "-z", "HEAD")))
    theirs = _names(_git(root, "diff", "--cached", "--name-only", "--no-renames", "-z", "MERGE_HEAD"))
    return [path for path in theirs if path in ours]


def merge_base(root: Path, base: str) -> str:
    return _git(root, "merge-base", base, "HEAD").decode("utf-8", "replace").strip()


def show(root: Path, ref: str, path: str) -> str | None:
    """A file's text at a commit, or None if it doesn't exist there."""
    if _run(root, "cat-file", "-e", f"{ref}:{path}").returncode != 0:
        return None
    return _git(root, "show", f"{ref}:{path}").decode("utf-8", "replace")


def _run(root: Path, *args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", *args], cwd=root, capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as error:
        raise GitError(f"git {' '.join(args)}: {error}") from None


def read_staged(root: Path, path: str) -> str | None:
    """The staged version of a file: what the commit will contain, not the working tree."""
    return decode(_git(root, "show", f":{path}"))


def read_worktree(root: Path, path: str) -> str | None:
    """The file on disk, or None if it is missing or binary."""
    try:
        return decode((root / path).read_bytes())
    except OSError:
        return None

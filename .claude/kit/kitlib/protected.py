"""Protected paths, secrets and commands from `[protected]` in kit.toml (plan 03).

Deny rules in `settings.json` are the primary protection (decision 15). This module is the backstop
behind them, used by the PreToolUse hook (`check_tool_call`), and the check that pre-commit and CI
run on changed files (`check`).
"""

import fnmatch
import os
import re
from pathlib import Path

from . import commands, file_commands
from .findings import Finding
from .globs import WILDCARD, is_bare, matches, normalize

CHECK = "protected"
ALLOW_VARIABLE = "KIT_ALLOW_PROTECTED"

# The kit's own configuration: whoever can edit these can switch the protection off. Ask rules
# guard them (decision 30) and prompt in every mode, bypassPermissions included; but they are Edit
# rules, not documented to cover `rm` or PowerShell cmdlets, so in bypass mode the hook still
# blocks shell writes to these (decision 92). Other modes: backlog `kit-config-shell-guard-modes`.
KIT_GUARD = [".claude/settings.json", ".claude/kit.toml", ".claude/kit/**", ".githooks/**"]

FILE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
SHELL_TOOLS = {"Bash": "bash", "PowerShell": "powershell"}


# Windows file names ignore case: `VENDOR\a.py` is the file `vendor/**` protects.
CASE_INSENSITIVE = os.name == "nt"


def _matching(path: str, patterns, removes: bool = False, itself: bool = True) -> str | None:
    """The first pattern path falls under, also when path is a folder holding matching files:
    `Remove-Item vendor` deletes everything `vendor/**` protects, `rm -rf src` deletes `src/vendor/`.
    itself=False skips path's own match and asks only about what the folder holds."""
    path = normalize(path).rstrip("/")
    path = "" if path == "." else path
    if CASE_INSENSITIVE:
        path = path.lower()
    for pattern in patterns:
        original = pattern
        if CASE_INSENSITIVE:
            pattern = pattern.lower()
        if path and ((itself and matches(path, pattern)) or matches(path + "/__kit_probe__", pattern)):
            return original
        if removes and _inside(pattern, *_split_at_wildcard(path)):
            return original
    return None


def _split_at_wildcard(path: str) -> tuple[str, str | None]:
    """(folder before the first wildcard part, that part): `src/v*` is ("src", "v*"), `*` is ("", "*")."""
    parts = path.split("/") if path else []
    for index, part in enumerate(parts):
        if WILDCARD.search(part):
            return "/".join(parts[:index]), part
    return path, None


def _inside(pattern: str, folder: str, glob: str | None = None) -> bool:
    """Whether removing folder (or the entries of folder matching glob) reaches an anchored
    pattern's fixed part. "" is the project root. A pattern without a slash can match at any
    depth, so it says nothing about a given folder."""
    pattern = normalize(pattern).lstrip("/")
    if "/" not in pattern.rstrip("/"):
        return False
    fixed = WILDCARD.split(pattern, maxsplit=1)[0]
    prefix = folder + "/" if folder else ""
    if not fixed or not fixed.startswith(prefix):
        return False
    if glob is None:
        return True
    # `rm *.log` at the root must not count as deleting `vendor/`: the glob has to match the
    # pattern's entry at that depth. A wildcard there in the pattern too: assume they can meet.
    entry = pattern[len(prefix) :].split("/", 1)[0]
    return bool(WILDCARD.search(entry)) or fnmatch.fnmatchcase(entry, glob)


def path_reason(protected, path: str, removes: bool = False) -> str | None:
    """Why changing path is blocked, or None.

    removes: path is being deleted or moved away, so a protected path anywhere inside it counts too.
    """
    shown = normalize(path)
    for patterns, what, key in (
        (protected.paths, "is protected", "paths"),
        (protected.secrets, "holds secrets", "secrets"),
    ):
        pattern = _secret_matching(path, patterns) if key == "secrets" else _matching(path, patterns)
        if pattern:
            return f"{shown} {what} (matches {pattern!r} in [protected].{key}, .claude/kit.toml)"
        # Only what a folder holds: path itself was decided above, exemptions included (review
        # round 1: `rm .env.example` was blocked while editing it was allowed).
        positive = [pattern for pattern in patterns if not pattern.startswith("!")]
        pattern = _matching(path, positive, removes=True, itself=False) if removes else None
        if pattern:
            # The folder itself isn't protected; what's inside it is. Say so, or the reason misleads.
            return (
                f"removing {shown} would delete protected files "
                f"(matches {pattern!r} in [protected].{key}, .claude/kit.toml)"
            )
    return None


def _secret_matching(path: str, patterns) -> str | None:
    """The secrets pattern path falls under, after exemptions, or None.

    Matches Claude Code's deny rules (decision 92): a `!name` cancels the bare-name patterns listed
    before it, never an anchored one (a pattern with a folder in it), and a later pattern can match
    the path again.
    """
    anchored = bare = None
    for pattern in patterns:
        if pattern.startswith("!"):
            if bare and _matching(path, [pattern[1:]]):
                bare = None
        elif _matching(path, [pattern]):
            if is_bare(pattern):
                bare = pattern
            else:
                anchored = anchored or pattern
    return anchored or bare


def check(config, paths) -> list[Finding]:
    """Findings for changed paths that are protected or secret. Kit config changes are normal commits."""
    findings = []
    for path in paths:
        reason = path_reason(config.protected, path)
        if reason:
            message = f"{reason}. If this change is intended, commit it with {ALLOW_VARIABLE}=1."
            findings.append(Finding(path=normalize(path), line=0, check=CHECK, message=message))
    return sorted(findings)


def allowed_by_human() -> bool:
    return os.environ.get(ALLOW_VARIABLE) == "1"


def check_tool_call(payload: dict, root: Path, config) -> str | None:
    """Why Claude Code should block this tool call, or None to let the normal permission flow decide."""
    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input") or {}
    cwd = Path(payload.get("cwd") or root)
    protected = config.protected
    guard_kit = protected.guard_kit and payload.get("permission_mode") == "bypassPermissions"

    if tool in FILE_TOOLS:
        file_path = tool_input.get("file_path") or tool_input.get("notebook_path")
        return _target_reason(protected, root, cwd, file_path) if file_path else None

    shell = SHELL_TOOLS.get(tool)
    if shell is None:
        return None
    text = tool_input.get("command")
    if not isinstance(text, str):
        raise ValueError(f"{tool} call without a command string")
    reason = commands.disables_checks(text, shell)
    if reason:
        return reason
    for offending, pattern in commands.find_protected(text, shell, protected.commands):
        return f"`{offending}` matches the protected command {pattern!r} ([protected].commands, .claude/kit.toml)"
    git_bash = shell == "bash"
    for target in file_commands.write_targets(text, shell):
        reason = _target_reason(protected, root, cwd, target, git_bash=git_bash, guard_kit=guard_kit)
        if reason:
            return reason
    for target in file_commands.removed_targets(text, shell):
        reason = _target_reason(protected, root, cwd, target, removes=True, git_bash=git_bash, guard_kit=guard_kit)
        if reason:
            return reason
    return None


def _target_reason(
    protected, root: Path, cwd: Path, target: str, removes: bool = False, git_bash: bool = True, guard_kit: bool = False
) -> str | None:
    rel = relative(root, cwd, target, git_bash)
    if rel is None:
        return None
    if guard_kit and _matching(rel, KIT_GUARD, removes):
        return (
            f"{normalize(rel)} is (or holds) the kit's own configuration, and in bypassPermissions "
            "mode a shell command can change it without the owner's approval. Ask the owner to "
            "run it, or use the Edit tool for a content change: that asks first"
        )
    return path_reason(protected, rel, removes)


def native_path(target: str, windows: bool | None = None, git_bash: bool = True) -> str:
    """Git Bash writes `C:\\x` as `/c/x`; on Windows, Path would read that as a folder on the
    current drive and the target would fall "outside the project" unchecked. PowerShell reads
    `/d/x` exactly that way, so git_bash=False leaves it alone."""
    windows = os.name == "nt" if windows is None else windows
    found = re.match(r"^/([a-zA-Z])(?:/|$)", target) if windows and git_bash else None
    return f"{found.group(1).upper()}:/{target[3:]}" if found else target


def relative(root: Path, cwd: Path, target: str, git_bash: bool = True) -> str | None:
    """target as a project-relative POSIX path, or None if it lies outside the project."""
    target = native_path(target, git_bash=git_bash)
    path = Path(target.replace("\\", "/")) if os.sep == "/" else Path(target)
    absolute = Path(os.path.normpath(cwd / path))  # normpath, not resolve: the file may not exist yet
    try:
        rel = absolute.relative_to(Path(os.path.normpath(root)))
    except ValueError:
        try:  # a symlinked or differently-cased root (macOS /private, Windows short names)
            rel = absolute.resolve().relative_to(root.resolve())
        except (ValueError, OSError):
            return None
    return rel.as_posix()

"""Gitignore-style path patterns, matched the same way on Windows and POSIX.

Paths are relative to the project root and use `/`. A pattern without a slash matches the file name
at any depth (`*.py`); a pattern with a slash is anchored at the root (`src/*.py`). `**` crosses
folders, `*` and `?` don't, and a trailing `/` means everything inside that folder.
"""

import functools
import os
import re

WILDCARD = re.compile(r"[*?\[]")


def normalize(path: str) -> str:
    """Project-relative path in POSIX form: `src\\a.py` and `./src/a.py` both become `src/a.py`."""
    path = path.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path


def is_bare(pattern: str) -> bool:
    """A bare file name: no folder in it and no trailing slash. Claude Code matches it at any depth
    and lets a `!` exemption cancel it; anything else becomes an anchored rule (decision 92)."""
    return "/" not in normalize(pattern)


@functools.lru_cache(maxsize=512)
def _compile(pattern: str) -> re.Pattern:
    pattern = normalize(pattern)
    anchored = "/" in pattern.rstrip("/")  # decided before a trailing / expands
    if pattern.endswith("/"):
        pattern += "**"
    pattern = pattern.lstrip("/")

    out = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")  # zero or more folders
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        elif pattern[i] == "[":
            end = pattern.find("]", i + 1)
            if end == -1:  # no closing bracket: a literal "["
                out.append(re.escape("["))
                i += 1
                continue
            body = pattern[i + 1 : end]
            if body.startswith("!"):
                body = "^" + body[1:]
            out.append("[" + body.replace("\\", "\\\\") + "]")
            i = end + 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1

    prefix = "" if anchored else "(?:.*/)?"
    return re.compile(prefix + "".join(out) + r"\Z")


def validate(pattern: str) -> None:
    """Raise ValueError if pattern is empty or can't be compiled (e.g. an empty `[]` class)."""
    if not pattern.strip():
        raise ValueError("empty glob")
    try:
        _compile(pattern)
    except re.error as error:
        raise ValueError(f"invalid glob {pattern!r}: {error}") from None


def matches(path: str, pattern: str) -> bool:
    return _compile(pattern).match(normalize(path)) is not None


def matches_any(path: str, patterns) -> bool:
    return any(matches(path, pattern) for pattern in patterns)


def file_matcher(patterns):
    """matches_any_file compiled once, for judging many paths against the same patterns."""
    fold = os.name == "nt"
    combined = "|".join(f"(?:{_compile(p.lower() if fold else p).pattern})" for p in patterns)
    regex = re.compile(combined) if combined else None

    def match(path: str) -> bool:
        path = normalize(path)
        return regex is not None and regex.match(path.lower() if fold else path) is not None

    return match


def matches_any_file(path: str, patterns) -> bool:
    """matches_any for a real file: on Windows the file system ignores case, so this does too.

    Lane ownership uses it, in the edit-time hook and the boundary check alike, so the two agree.
    """
    if os.name == "nt":
        return matches_any(path.lower(), [pattern.lower() for pattern in patterns])
    return matches_any(path, patterns)

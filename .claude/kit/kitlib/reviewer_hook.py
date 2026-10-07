"""`kit hook reviewer-bash`: the reviewer agent may run read-only git commands and nothing else (57).

An allowlist, unlike the protected-paths guard's denylist: every simple command in the text must
be git with a read-only subcommand (or a plain `cd <folder>`). Like `commands.py`, it guards against
mistakes, not adversaries; it refuses anything it can't read plainly (substitutions, redirects,
unquoted globs, environment overrides). Programs git itself runs because of the repo's config
(`diff.external`, textconv drivers, `core.fsmonitor`) are out of its reach: the reviewer can't
change that config.
"""

import re

from .commands import tokenize

READ_ONLY = {
    "diff",
    "log",
    "show",
    "status",
    "merge-base",
    "rev-parse",
    "rev-list",
    "ls-files",
    "blame",
    "grep",
    "cat-file",
}
_GLOBAL_FLAGS = {"--no-pager", "-P", "--no-optional-locks", "--literal-pathspecs"}
# `HEAD@{1}`, `@{u}`, `HEAD^{tree}`: the tokenizer splits on braces, so a ref like this would read
# as two commands.
_BRACE_REF = re.compile(r"[@^]\{[^{}\s;&|()]*\}")

ALLOWED_TEXT = "git with one of " + ", ".join(sorted(READ_ONLY))


def reason(text: str) -> str | None:
    """Why text isn't a read-only git command (or a chain of them), or None if it is."""
    if found := _unquoted_specials(text):
        chars = "".join(sorted(found))
        if found <= set("*?["):
            return f"`{chars}` outside quotes is a glob bash expands; quote the pattern"
        return f"`{chars}` (substitution or redirect) is not allowed"
    segments = tokenize(_BRACE_REF.sub("REF", text), "bash")
    if not segments:
        return "empty command"
    for words in segments:
        why = _cd_reason(words) if words[0] == "cd" else _git_reason(words)
        if why:
            return f"`{' '.join(words)}`: {why}"
    return None


def _unquoted_specials(text: str) -> set[str]:
    """Characters that would run or write something the words don't show.

    Inside single quotes nothing is special to bash; inside double quotes `$` and backticks still
    substitute, but `<` and `>` are plain text (`--format='%H -> %s'` is fine). Unquoted globs
    count too: bash expands them after this check, so a file the branch under review adds, named
    `--output=AGENTS.md`, would reach git as an option.
    """
    found, quote, i = set(), None, 0
    while i < len(text):
        char = text[i]
        if quote == "'":
            if char == "'":
                quote = None
        elif char == "\\":
            i += 1  # the next character is escaped, in or out of double quotes
        elif quote == '"':
            if char == '"':
                quote = None
            elif char in "$`":
                found.add(char)
        elif char in "'\"":
            quote = char
        elif char in "$`<>*?[":
            found.add(char)
        i += 1
    return found


def _cd_reason(words: list[str]) -> str | None:
    # Agents habitually start with `cd <project> &&`; changing folder reads and writes nothing.
    if len(words) == 2 and not words[1].startswith("-"):
        return None
    return "only `cd <folder>` is allowed"


def _git_reason(words: list[str]) -> str | None:
    # Only git on the PATH: a file named git in the branch under review could be anything.
    if words[0].lower() not in ("git", "git.exe"):
        return "only git commands are allowed (plain `git`, no path)"
    args = words[1:]
    while args and args[0].startswith("-"):
        option = args.pop(0)
        if option == "-C" and args:
            args.pop(0)  # another folder: reading it is still reading
        elif option not in _GLOBAL_FLAGS:
            return f"git option {option} is not allowed"
    if not args:
        return "no git subcommand"
    subcommand, rest = args[0], args[1:]
    if subcommand not in READ_ONLY:
        return f"git {subcommand} is not a read-only command"
    for arg in rest:
        if arg == "--":
            break
        name = arg.split("=", 1)[0]
        # git accepts unambiguous abbreviations of long options (`--outp=x` is `--output=x`).
        if name == "--output" or (len(name) >= 4 and "--output".startswith(name)):
            return "--output writes a file"
        if len(name) >= 5 and "--ext-diff".startswith(name):
            return "--ext-diff runs an external program"
        if subcommand == "grep" and _opens_pager(arg):
            return "git grep -O runs a program"
    return None


def _opens_pager(arg: str) -> bool:
    """`-O`, `-Ovim`, `-nO`: the program comes attached, alone or in a short-flag cluster."""
    if arg.startswith("--"):
        name = arg.split("=", 1)[0]
        return len(name) >= 4 and "--open-files-in-pager".startswith(name)
    return arg.startswith("-") and "O" in arg

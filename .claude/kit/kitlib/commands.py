"""Read shell commands well enough to catch the protected ones (decisions 27, 28).

This guards against mistakes, not adversaries. It handles the forms an agent plausibly writes:
compound commands, quotes, `FOO=bar` prefixes, wrappers (`env`, `sudo`, `timeout`...), git's global
options (`git -C dir`), flags in any order and short-flag clusters (`-xdf`). It does not follow
`bash -c "..."` strings, aliases, `+refspec` pushes or scripts; the docs list those as misses.
"""

import ntpath
import re
from dataclasses import dataclass

# Characters that end one simple command and start the next, outside quotes. Parentheses and
# braces are included so `(cd x && git push -f)` and `$(...)` split into their commands too.
_SEPARATORS = set(";|&\n()") | {"{", "}"}

_WRAPPERS = {"env", "sudo", "timeout", "nohup", "command", "builtin", "time", "nice", "stdbuf", "xargs", "exec"}
_WRAPPER_VALUE_OPTIONS = {"-u", "-g", "-C", "-n", "-s", "-k", "-o", "-e", "-i", "-I", "-L", "-P", "-d"}
_GIT_VALUE_OPTIONS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


@dataclass(frozen=True)
class Pattern:
    text: str
    program: str
    words: tuple  # leading non-flag words after the program, in order (the subcommand)
    flags: frozenset  # flags that must all appear, in any order


@dataclass(frozen=True)
class Command:
    program: str
    args: tuple
    git_config: tuple = ()  # `-c key=value` overrides given to git before its subcommand


def tokenize(text: str, shell: str) -> list[list[str]]:
    """Split text into simple commands, each a list of words with quotes removed.

    Bash escapes with a backslash, PowerShell with a backtick (backslash is a path separator
    there). An unbalanced quote runs to the end of the text instead of failing: a guard must still
    read a command Claude Code would reject.
    """
    escape = "`" if shell == "powershell" else "\\"
    segments, words = [], []
    word, in_word, quote = [], False, None
    i = 0

    def end_word():
        nonlocal word, in_word
        if in_word:
            words.append("".join(word))
        word, in_word = [], False

    while i < len(text):
        char = text[i]
        if quote:
            if char == quote:
                quote = None
            elif char == escape and quote == '"' and i + 1 < len(text):
                i += 1
                word.append(text[i])
            else:
                word.append(char)
        elif char == escape and i + 1 < len(text):
            i += 1
            if text[i] != "\n":  # a line continuation joins lines
                word.append(text[i])
                in_word = True
        elif char in "'\"":
            quote, in_word = char, True
        elif char == ">" and not re.fullmatch(r"[0-9*]*>?", "".join(word)):
            # `x>.env` is `x` then a redirect: start a new word unless this one is only a
            # descriptor (`2>`, `*>`) or the first `>` of `>>`.
            end_word()
            word, in_word = [char], True
        elif char == "|" and re.fullmatch(r"[0-9*]*>", "".join(word)):
            word.append(char)  # `>|` (overwrite even with noclobber) is a redirect, not a pipe
        elif char in _SEPARATORS:
            end_word()
            if words:
                segments.append(words)
            words = []
        elif char.isspace():
            end_word()
        else:
            word.append(char)
            in_word = True
        i += 1
    end_word()
    if words:
        segments.append(words)
    return segments


def program_name(word: str) -> str:
    """`/usr/bin/git`, `C:\\Git\\cmd\\git.exe` and `Git.EXE` are all `git`."""
    name = ntpath.basename(word.replace("/", "\\")).lower()
    return name[:-4] if name.endswith(".exe") else name


def normalize(words: list[str]) -> Command | None:
    """Strip assignments, wrappers and git global options; None if nothing is left to run."""
    words = list(words)
    while words:
        if _ASSIGNMENT.match(words[0]):
            words.pop(0)
        elif program_name(words[0]) in _WRAPPERS:
            wrapper = program_name(words.pop(0))
            while words and (words[0].startswith("-") or _ASSIGNMENT.match(words[0])):
                option = words.pop(0)
                if option in _WRAPPER_VALUE_OPTIONS and words:
                    words.pop(0)
            if wrapper == "timeout" and words:
                words.pop(0)  # the duration
        else:
            break
    if not words:
        return None
    program, args = program_name(words[0]), words[1:]
    git_config = []
    if program == "git":
        while args and args[0].startswith("-") and args[0] != "--":
            option = args.pop(0)
            name, has_value, value = option.partition("=")
            if name in _GIT_VALUE_OPTIONS and not has_value and args:
                value = args.pop(0)
            if name == "-c":
                git_config.append(value)
    return Command(program, tuple(args), tuple(git_config))


def _expand(arg: str) -> set[str]:
    """`-xdf` is `-x -d -f`. Only short clusters, so `-m"initial"` (one word, `-minitial`) isn't."""
    if re.fullmatch(r"-[A-Za-z]{2,4}", arg):
        return {f"-{letter}" for letter in arg[1:]}
    return {arg}


def parse_pattern(text: str) -> Pattern:
    """A protected command from kit.toml. Raises ValueError if it can't be read unambiguously."""
    if text.count("'") % 2 or text.count('"') % 2:
        raise ValueError("unbalanced quote")
    segments = tokenize(text, "bash")
    if len(segments) != 1:
        raise ValueError("must be one command (no ;, |, &&, parentheses)" if segments else "empty command")
    command = normalize(segments[0])
    if command is None:
        raise ValueError("no program to match")
    words, flags = [], set()
    for arg in command.args:
        if arg.startswith("-"):
            flags |= _expand(arg)
        elif not flags:
            words.append(arg)
        else:
            raise ValueError(f"{arg!r}: put words before flags (program, subcommand, then flags)")
    return Pattern(text, command.program, tuple(words), frozenset(flags))


def matches(command: Command, pattern: Pattern) -> bool:
    if command.program != pattern.program:
        return False
    if command.args[: len(pattern.words)] != pattern.words:
        return False
    present = set()
    for arg in command.args[len(pattern.words) :]:
        if arg == "--":
            break  # after `--`, words are operands (`grep -- --force` names a pattern)
        present |= _expand(arg)
    return pattern.flags <= present


def find_protected(text: str, shell: str, patterns) -> list[tuple[str, str]]:
    """(the offending command, the pattern it matched) for each protected command in text."""
    parsed = [parse_pattern(pattern) for pattern in patterns]
    found = []
    for words in tokenize(text, shell):
        command = normalize(words)
        if command is None:
            continue
        for pattern in parsed:
            if matches(command, pattern):
                found.append((" ".join(words), pattern.text))
    return found


# ---- the agent switching the checks off (decision 34) -------------------------------------------

_CONFIG_READS = {"--get", "--get-all", "--get-regexp", "--list", "-l", "get", "list"}


# Setting an allow variable, judged per command word, not on the raw text: quoting the documented
# usage in a commit message, PR body or grep (`"...KIT_ALLOW_PROTECTED=1..."`) must pass. Only two
# forms that never appear in prose are matched on the raw text: `${X:=1}` and the .NET call.
# Protected paths (decision 34) and cross-lane changes (decision 96) each have one.
_ALLOW_NAMES = ("kit_allow_protected", "kit_allow_cross_lane")
_ALLOW_ALTERNATIVES = "|".join(_ALLOW_NAMES)
_SETS_IN_CODE = re.compile(
    rf"\$\{{(?:{_ALLOW_ALTERNATIVES}):?=|SetEnvironmentVariable\(\s*['\"](?:{_ALLOW_ALTERNATIVES})\b",
    re.IGNORECASE,
)
_PREFIX_ASSIGNMENT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\+?=")
_DECLARERS = {"export", "declare", "typeset", "local", "readonly", "set", "setx"}
_ENV_CMDLETS = {"set-item", "new-item", "si", "ni"}
_ALLOW_REASON = "the kit's KIT_ALLOW_* variables are for a human at a terminal, not for an agent"


def _sets_allow_variable(words: list[str]) -> bool:
    i = 0
    while i < len(words):  # `X=1 cmd`, `env X=1 cmd`, `sudo X=1 cmd`
        assignment = _PREFIX_ASSIGNMENT.match(words[i])
        if assignment:
            if assignment.group(1).lower() in _ALLOW_NAMES:
                return True
        elif program_name(words[i]) in _WRAPPERS:
            while i + 1 < len(words) and words[i + 1].startswith("-"):
                i += 1
        else:
            break
        i += 1
    if i >= len(words):
        return False
    first, args = words[i].lower(), [word.lower() for word in words[i + 1 :]]
    if any(first.startswith("$env:" + name) for name in _ALLOW_NAMES):  # `$env:X = 1`, `$env:X='1'`
        return "=" in first or bool(args) and args[0].startswith("=")
    if first in _DECLARERS:  # `export X=1`, `set X=1`, `setx X 1`
        return any(re.match(rf"(?:{_ALLOW_ALTERNATIVES})([+:]?=|$)", arg) for arg in args)
    if first in _ENV_CMDLETS:  # `Set-Item env:X 1`, `New-Item -Path Env: -Name X`
        named = any(arg.endswith(_ALLOW_NAMES) for arg in args)
        return named and any(arg.startswith("env:") for arg in args)
    return False


def disables_checks(text: str, shell: str) -> str | None:
    """Why text would switch the kit's local checks off, or None."""
    if _SETS_IN_CODE.search(text):
        return _ALLOW_REASON
    for words in tokenize(text, shell):
        if _sets_allow_variable(words):
            return _ALLOW_REASON
        command = normalize(words)
        if command is None or command.program != "git":
            continue
        if any(value.lower().startswith("core.hookspath") for value in command.git_config):
            return "running git with core.hooksPath overridden skips the kit's git hooks"
        args = [arg.lower() for arg in command.args]
        if args[:1] == ["config"] and "core.hookspath" in args and not _CONFIG_READS & set(args):
            return "changing core.hooksPath switches the kit's git hooks off"
    return None

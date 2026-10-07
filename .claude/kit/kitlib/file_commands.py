"""Which paths a shell command writes, deletes or moves: best effort (decision 27).

Covers common file commands (`rm`, `mv`, `cp`, `touch`; PowerShell's `Set-Content`, `Remove-Item`,
`Out-File`... and their aliases) and output redirections. Read-only commands and anything not listed
are ignored; a script that opens files itself is invisible here. Native Windows has no sandbox, so
this is the only thing between PowerShell cmdlets and a protected path there.
"""

import re

from .commands import Command, normalize, tokenize

_REDIRECT = re.compile(r"^(?:\d+|\*)?>[>|]?(?!&)(.*)$")  # `>`, `>>`, `>|`, `2>`, `12>`, `*>`


_PS_CMDLETS = {
    "set-content": "first",
    "add-content": "first",
    "clear-content": "first",
    "out-file": "first",
    "new-item": "first",
    "rename-item": "first",
    "tee-object": "first",
    "remove-item": "all",
    "move-item": "first-two",
    "copy-item": "second",
}
_PS_ALIASES = {
    "sc": "set-content",
    "ac": "add-content",
    "clc": "clear-content",
    "ni": "new-item",
    "ren": "rename-item",
    "rni": "rename-item",
    "tee": "tee-object",
    "rm": "remove-item",
    "del": "remove-item",
    "erase": "remove-item",
    "rd": "remove-item",
    "ri": "remove-item",
    "rmdir": "remove-item",
    "mv": "move-item",
    "move": "move-item",
    "mi": "move-item",
    "cp": "copy-item",
    "copy": "copy-item",
    "cpi": "copy-item",
}
# In match order: `-pa` is -Path, `-d` is -Destination (PowerShell accepts unique prefixes).
_PS_PATH_PARAMETERS = ("path", "literalpath", "pspath", "lp", "filepath", "destination")
_PS_SWITCHES = {
    "force",
    "recurse",
    "append",
    "noclobber",
    "nonewline",
    "passthru",
    "whatif",
    "confirm",
    "verbose",
    "debug",
    "asbytestream",
    "stream",
}
_BASH_COMMANDS = {
    "rm": "all",
    "rmdir": "all",
    "touch": "all",
    "truncate": "all",
    "mv": "all",
    "cp": "last",
    "ln": "last",
}
_BASH_VALUE_OPTIONS = {"-s", "-S", "-t", "--suffix", "--target-directory", "--size", "--reference"}


def write_targets(text: str, shell: str) -> list[str]:
    """Paths, as written, that the commands in text would create, change, move or delete."""
    targets = []
    for words in tokenize(text, shell):
        words, redirected = _redirections(words)
        targets.extend(redirected)
        command = normalize(words)
        if command is None:
            continue
        if command.program == "git":
            targets.extend(_git_targets(command)[0])
        elif shell == "powershell":
            targets.extend(_powershell_targets(command))
        else:
            targets.extend(_bash_targets(command))
    return targets


def _redirections(words):
    """Remove `> file`, `>>file`, `2> file` from words; return the rest and the targets."""
    rest, targets = [], []
    i = 0
    while i < len(words):
        found = _REDIRECT.match(words[i])
        if found and words[i][0] in "0123456789*>":
            if found.group(1):
                targets.append(found.group(1))
            elif i + 1 < len(words):
                i += 1
                targets.append(words[i])
        else:
            rest.append(words[i])
        i += 1
    return rest, targets


def _powershell_parse(command: Command):
    """(cmdlet, [(path parameter, value)], positionals) for a known file cmdlet, else None."""
    name = _PS_ALIASES.get(command.program, command.program)
    if name not in _PS_CMDLETS:
        return None
    named, positional = [], []
    args = list(command.args)
    while args:
        arg = args.pop(0)
        if not (arg.startswith("-") and len(arg) > 1):
            positional.append(arg)
            continue
        prefix, colon, value = arg[1:].partition(":")
        prefix = prefix.lower()
        if not colon and prefix not in _PS_SWITCHES and args:
            value = args.pop(0)
        full = next((p for p in _PS_PATH_PARAMETERS if p.startswith(prefix)), None)
        if full and value:
            named.append((full, value))
    return name, named, positional


def _powershell_targets(command: Command) -> list[str]:
    parsed = _powershell_parse(command)
    if parsed is None:
        return []
    name, named, positional = parsed
    which = _PS_CMDLETS[name]
    # A named -Path takes the first positional slot, so the positionals shift down by one.
    path_named = any(full != "destination" for full, _ in named)
    destinations = [value for full, value in named if full == "destination"]
    if which == "second":
        # Copy-Item changes only its destination, never its source (-Path or the first positional).
        return positional[0 if path_named else 1 :][:1] + destinations
    if path_named:
        chosen = positional[:1] if which == "first-two" and not destinations else []
    else:
        chosen = {"all": positional, "first-two": positional[:2]}.get(which, positional[:1])
    return chosen + [value for _, value in named]


def _bash_parse(command: Command):
    """(operands, -t target directory or None) for a known file command, else None."""
    if command.program not in _BASH_COMMANDS:
        return None
    operands, target_dir = [], None
    args = list(command.args)
    while args:
        arg = args.pop(0)
        if arg == "--":
            operands.extend(args)
            break
        if arg.startswith("-") and len(arg) > 1:
            name, has_value, value = arg.partition("=")
            if name in _BASH_VALUE_OPTIONS and not has_value and args:
                value = args.pop(0)
            if name in ("-t", "--target-directory"):
                target_dir = value
            continue
        operands.append(arg)
    return operands, target_dir


def _bash_targets(command: Command) -> list[str]:
    parsed = _bash_parse(command)
    if parsed is None:
        return []
    operands, target_dir = parsed
    if target_dir is not None:
        return [target_dir]
    if _BASH_COMMANDS[command.program] == "last":
        return operands[-1:]
    return operands


def removed_targets(text: str, shell: str) -> list[str]:
    """Paths the commands in text delete or move away; deleting a folder deletes what's inside it."""
    removed = []
    for words in tokenize(text, shell):
        command = normalize(_redirections(words)[0])
        if command is None:
            continue
        if command.program == "git":
            removed += _git_targets(command)[1]
        elif shell == "powershell":
            parsed = _powershell_parse(command)
            if parsed is None:
                continue
            name, named, positional = parsed
            paths = [value for full, value in named if full != "destination"]
            if name == "remove-item":
                removed += positional + paths
            elif name == "move-item":
                removed += paths or positional[:1]
        else:
            parsed = _bash_parse(command)
            if parsed is None:
                continue
            operands, target_dir = parsed
            if command.program in ("rm", "rmdir"):
                removed += operands
            elif command.program == "mv":
                removed += operands if target_dir is not None else operands[:-1]
    return removed


_GIT_VALUE_OPTIONS = {"-s", "--source", "--pathspec-from-file"}


def _git_targets(command: Command) -> tuple[list[str], list[str]]:
    """(written, removed) paths for git's own file commands; the same in both shells."""
    if not command.args:
        return [], []
    subcommand, args = command.args[0], list(command.args[1:])
    if subcommand == "checkout":
        # Only after `--` are the words certainly paths (`git checkout main` switches branches);
        # `.` can't be a branch. Restoring a folder overwrites what's inside it, so the paths
        # also go through the folder check, like deletes.
        paths = args[args.index("--") + 1 :] if "--" in args else [arg for arg in args if arg == "."]
        return paths, paths
    if subcommand not in ("rm", "mv", "restore"):
        return [], []
    operands = []
    while args:
        arg = args.pop(0)
        if arg == "--":
            operands += args
            break
        if arg.startswith("-") and len(arg) > 1:
            name, has_value, _ = arg.partition("=")
            if name in _GIT_VALUE_OPTIONS and not has_value and args:
                args.pop(0)
            continue
        operands.append(arg)
    if subcommand == "rm":
        return [], operands
    if subcommand == "mv":
        return operands[-1:], operands[:-1]
    return operands, operands  # restore: overwrites, including everything in a folder

"""Find the project root and load `.claude/kit.toml`.

Validation is strict (decision 24): an unknown key or a wrong type is an error naming the key, so a
typo can't silently switch a rule off.
"""

import re
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from . import commands, globs, lane_owners

CONFIG_REL = Path(".claude") / "kit.toml"

_TOP_LEVEL = {"project", "checks", "lanes", "protected"}
_PROJECT_KEYS = {
    "name": str,
    "description": str,
    "test_command": str,
    "integration_branch": str,
    "merge_mode": str,
    "worktree_root": str,
    "ownership": str,
    "shared_paths": list,
}
_CHECKS_KEYS = {"rules": list}
_PROTECTED_KEYS = {"paths": list, "commands": list, "secrets": list, "guard_kit": bool}

# Used when [protected] leaves a key out, so a project that never wrote the table is still guarded.
# `git clean -f` rather than `-fdx`: every flag in a pattern must be present, and `-fd` destroys too.
DEFAULT_COMMANDS = [
    "git push --force",
    "git push -f",
    "git reset --hard",
    "git clean -f",
    "git commit --no-verify",
    "git commit -n",
]
# Every .env variant except the committed example: a `!` deny rule carves it out (decision 82).
DEFAULT_SECRETS = [".env", ".env.*", "!.env.example"]
# Every lane writes its own files here (ARCHITECTURE §8), so they belong to no single lane.
DEFAULT_SHARED_PATHS = [
    "docs/changelog.d/**",
    "docs/backlog/**",
    "docs/plans/**",
    "docs/design/decisions-log.md",
    "docs/health/**",
]
_RULE_KEYS = {
    "id": (str, True),
    "pattern": (str, True),
    "paths": (list, True),
    "message": (str, True),
    "exclude": (list, False),
    "ignore_comments": (bool, False),
}


class ConfigError(Exception):
    """kit.toml exists but can't be used. The message names the file, key and problem."""


class ConfigMissing(ConfigError):
    """No kit.toml: the kit isn't set up in this project."""


@dataclass(frozen=True)
class Rule:
    id: str
    regex: re.Pattern
    paths: list
    message: str
    exclude: list = field(default_factory=list)
    ignore_comments: bool = True


@dataclass(frozen=True)
class Protected:
    paths: list = field(default_factory=list)
    commands: list = field(default_factory=lambda: list(DEFAULT_COMMANDS))
    secrets: list = field(default_factory=lambda: list(DEFAULT_SECRETS))
    guard_kit: bool = True


@dataclass(frozen=True)
class Lane:
    name: str
    owns: list
    scope: str = ""
    resources: dict = field(default_factory=dict)


@dataclass(frozen=True)
class LaneSettings:
    """The `[project]` keys lanes use, with their defaults filled in."""

    integration_branch: str = "main"
    merge_mode: str = "pr"
    worktree_root: str = ".claude/worktrees"
    ownership: str = "ask"
    shared_paths: list = field(default_factory=lambda: list(DEFAULT_SHARED_PATHS))


@dataclass(frozen=True)
class Config:
    project: dict
    rules: list
    raw: dict
    protected: Protected = field(default_factory=Protected)
    lanes: list = field(default_factory=list)
    lane_settings: LaneSettings = field(default_factory=LaneSettings)


def find_root(start: Path) -> Path:
    """The git top level containing start (a lane worktree is its own top level).

    Outside git, the nearest folder above start that has .claude/kit.toml; failing that, start.
    """
    start = Path(start).resolve()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return Path(result.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    for folder in (start, *start.parents):
        if (folder / CONFIG_REL).is_file():
            return folder
    return start


def load(root: Path) -> Config:
    path = Path(root) / CONFIG_REL
    if not path.is_file():
        raise ConfigMissing(f"{CONFIG_REL.as_posix()} not found in {root}")
    # utf-8-sig: Windows PowerShell 5.1 writes a byte-order mark that TOML rejects.
    return parse(path.read_text(encoding="utf-8-sig"))


def lanes_only(text: str, named: str) -> Config | None:
    """Only the lanes and lane settings of a kit.toml, for an older version read from git (decision 96).

    None when no lane there is `named`: nothing is validated then, as for a branch that isn't a lane's.
    Rules, [protected] and other [project] keys aren't read: a version the current kit would reject
    there (a check tightened since) must not block the commit that repairs it. The lane keys are
    still validated, so the caller can fail closed on them.
    """
    try:
        raw = tomllib.loads(text.removeprefix("﻿"))
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"not valid TOML: {error}") from None
    entries = raw.get("lanes", [])
    if not isinstance(entries, list) or not any(isinstance(e, dict) and e.get("name") == named for e in entries):
        return None
    project = raw.get("project", {})
    _check_table(project, "[project]")
    lane_keys = {key: kind for key, kind in _PROJECT_KEYS.items() if key in LaneSettings.__dataclass_fields__}
    _check_keys({key: value for key, value in project.items() if key in lane_keys}, lane_keys, "[project]")
    lane_settings = _lane_settings(project)
    return Config(
        project=project,
        rules=[],
        raw=raw,
        lanes=_lanes(raw.get("lanes", []), lane_settings),
        lane_settings=lane_settings,
    )


def parse(text: str, where: str = CONFIG_REL.as_posix()) -> Config:
    """A config from kit.toml's text: also used for an older version read from git."""
    try:
        raw = tomllib.loads(text.removeprefix("﻿"))
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{where}: not valid TOML: {error}") from None

    _check_keys(raw, dict.fromkeys(_TOP_LEVEL, object), "top level")
    project = raw.get("project", {})
    _check_table(project, "[project]")
    _check_keys(project, _PROJECT_KEYS, "[project]")
    checks = raw.get("checks", {})
    _check_table(checks, "[checks]")
    _check_keys(checks, _CHECKS_KEYS, "[checks]")
    rules = [_rule(entry, number) for number, entry in enumerate(checks.get("rules", []), start=1)]

    seen = set()
    for rule in rules:
        if rule.id in seen:
            raise ConfigError(f"{CONFIG_REL.as_posix()}: duplicate rule id {rule.id!r}")
        seen.add(rule.id)
    lane_settings = _lane_settings(project)
    return Config(
        project=project,
        rules=rules,
        raw=raw,
        protected=_protected(raw.get("protected", {})),
        lanes=_lanes(raw.get("lanes", []), lane_settings),
        lane_settings=lane_settings,
    )


_CHOICES = {"merge_mode": ("pr", "local"), "ownership": ("ask", "off")}
# Lane names become folder names and the `<lane>/` prefix of task branches (decision 42).
_LANE_NAME = re.compile(r"[a-z0-9][a-z0-9-]*\Z")
_LANE_KEYS = {"name": str, "scope": str, "owns": list, "resources": dict}
_WINDOWS_RESERVED = {"con", "prn", "aux", "nul", *(f"com{n}" for n in range(1, 10)), *(f"lpt{n}" for n in range(1, 10))}


def _lane_settings(project: dict) -> LaneSettings:
    where = "[project]"
    for key in ("integration_branch", "worktree_root"):
        if key in project and not project[key].strip():
            _fail(f"{where}: {key!r} must not be empty")
    for key, choices in _CHOICES.items():
        if key in project and project[key] not in choices:
            _fail(f"{where}: {key!r} must be one of {', '.join(map(repr, choices))}, not {project[key]!r}")
    _globs(project, "shared_paths", where)
    unknown = set(re.findall(r"\{[^}]*\}", project.get("worktree_root", ""))) - {"{project}"}
    if unknown:
        _fail(
            f"{where}: 'worktree_root' has unknown placeholder(s) {', '.join(sorted(unknown))}; only {{project}} exists"
        )
    defaults = LaneSettings()
    return LaneSettings(
        integration_branch=project.get("integration_branch", defaults.integration_branch),
        merge_mode=project.get("merge_mode", defaults.merge_mode),
        worktree_root=project.get("worktree_root", defaults.worktree_root),
        ownership=project.get("ownership", defaults.ownership),
        shared_paths=list(project.get("shared_paths", defaults.shared_paths)),
    )


def _lanes(entries, settings: LaneSettings) -> list:
    if not isinstance(entries, list):
        _fail("'lanes' must be an array of tables ([[lanes]])")
    lanes = []
    for number, entry in enumerate(entries, start=1):
        where = f"[[lanes]] #{number}"
        _check_table(entry, where)
        if isinstance(entry.get("name"), str):
            where = f"[[lanes]] {entry['name']!r}"
        _check_keys(entry, _LANE_KEYS, where)
        if "name" not in entry:
            _fail(f"{where}: missing required key 'name'")
        name = entry["name"]
        if not _LANE_NAME.match(name):
            _fail(f"{where}: name {name!r} must be lowercase letters, digits and '-', starting with a letter or digit")
        if name in _WINDOWS_RESERVED:
            _fail(f"{where}: name {name!r} is a reserved device name on Windows, which can't create that folder")
        if name == settings.integration_branch:
            _fail(f"{where}: a lane can't be named after the integration branch ({name!r})")
        if any(lane.name == name for lane in lanes):
            _fail(f"{where}: duplicate lane name {name!r}")
        owns = _globs(entry, "owns", where)
        if not owns:
            _fail(f"{where}: 'owns' must list at least one glob")
        resources = entry.get("resources", {})
        for key, value in resources.items():
            if not isinstance(value, (str, int, float, bool)):
                _fail(f"{where}: 'resources' value {key!r} must be a string, number or boolean")
        lanes.append(Lane(name=name, owns=list(owns), scope=entry.get("scope", ""), resources=dict(resources)))
    twin = lane_owners.same_pattern(lanes)
    if twin:
        # Neither is more specific, so the file has no owner (decision 97): nobody has decided yet.
        first, second, pattern, other = twin
        same = repr(pattern) if pattern == other else f"{pattern!r} ({other!r} is the same pattern)"
        _fail(f"lanes {first!r} and {second!r} both own {same}; give it to one lane or put it in shared_paths")
    return lanes


def _globs(table: dict, key: str, where: str) -> list:
    values = _strings(table, key, where)
    for value in values:
        try:
            globs.validate(value)
        except ValueError as error:
            _fail(f"{where}: {key!r}: {error}")
    return values


def _protected(table) -> Protected:
    where = "[protected]"
    _check_table(table, where)
    _check_keys(table, _PROTECTED_KEYS, where)
    for key in ("paths", "secrets"):
        bare_before, seen = [], set()
        for value in _strings(table, key, where):
            # A repeat would be dropped from the deny rules, while the hook would count it again.
            if key == "secrets" and globs.normalize(value) in seen:
                _fail(f"{where}: 'secrets': {value!r} is listed twice")
            seen.add(globs.normalize(value))
            if value.startswith("!"):
                _exemption(key, value[1:], bare_before, where)
                value = value[1:]
            elif globs.is_bare(value):
                bare_before.append(value)
            # Patterns are project-relative: the same text becomes a root-anchored deny rule.
            if value.startswith(("//", "~")) or ".." in value.replace("\\", "/").split("/"):
                _fail(f"{where}: {key!r}: {value!r} must be a path inside the project")
            try:
                globs.validate(value)
            except ValueError as error:
                _fail(f"{where}: {key!r}: {error}")
    for value in _strings(table, "commands", where):
        try:
            commands.parse_pattern(value)
        except ValueError as error:
            _fail(f"{where}: 'commands': {value!r}: {error}")
    defaults = Protected()
    return Protected(
        paths=list(table.get("paths", defaults.paths)),
        commands=list(table.get("commands", defaults.commands)),
        secrets=list(table.get("secrets", defaults.secrets)),
        guard_kit=table.get("guard_kit", defaults.guard_kit),
    )


def _exemption(key: str, name: str, bare_before: list, where: str) -> None:
    """A `!` exemption must be one Claude Code would honour (decision 92); one it ignores would
    leave the owner believing a file is readable, or the hook and the deny rules disagreeing."""
    pattern = f"!{name}"
    if key != "secrets":
        _fail(
            f"{where}: {key!r}: {pattern!r}: exemptions are allowed only in 'secrets'; "
            "remove the path from 'paths' instead"
        )
    if not name.strip():
        _fail(f"{where}: 'secrets': {pattern!r} names no file")
    if not globs.is_bare(name):
        _fail(
            f"{where}: 'secrets': {pattern!r} must be a bare file name: Claude Code can't carve an "
            "exemption out of a rule with a folder in it"
        )
    # A wildcard exemption may cancel part of any earlier name; a plain one must match one of them.
    if not any(globs.WILDCARD.search(name) or globs.matches(name, earlier) for earlier in bare_before):
        _fail(
            f"{where}: 'secrets': {pattern!r} has nothing before it to carve out of; list it after "
            "a bare file name it matches, such as '.env.*' (a name with a folder or a trailing / "
            "can't be carved)"
        )


def _strings(table: dict, key: str, where: str) -> list:
    values = table.get(key, [])
    if not all(isinstance(value, str) for value in values):
        _fail(f"{where}: {key!r} must be a list of strings")
    return values


def _rule(entry, number: int) -> Rule:
    where = f"[[checks.rules]] #{number}"
    _check_table(entry, where)
    if isinstance(entry.get("id"), str):
        where = f"[[checks.rules]] {entry['id']!r}"
    _check_keys(entry, {key: kind for key, (kind, _) in _RULE_KEYS.items()}, where)
    for key, (_, required) in _RULE_KEYS.items():
        if required and key not in entry:
            _fail(f"{where}: missing required key {key!r}")
    for key in ("id", "pattern", "message"):
        if not entry[key].strip():
            _fail(f"{where}: {key!r} must not be empty")
    for key in ("paths", "exclude"):
        values = entry.get(key, [])
        if not all(isinstance(value, str) for value in values):
            _fail(f"{where}: {key!r} must be a list of strings")
        for value in values:
            try:
                globs.validate(value)
            except ValueError as error:
                _fail(f"{where}: {key!r}: {error}")
    if not entry["paths"]:
        _fail(f"{where}: 'paths' must list at least one glob")
    try:
        regex = re.compile(entry["pattern"])
    except re.error as error:
        _fail(f"{where}: 'pattern' is not a valid regular expression: {error}")
    return Rule(
        id=entry["id"],
        regex=regex,
        paths=list(entry["paths"]),
        message=entry["message"],
        exclude=list(entry.get("exclude", [])),
        ignore_comments=entry.get("ignore_comments", True),
    )


def _check_table(value, where: str) -> None:
    if not isinstance(value, dict):
        _fail(f"{where} must be a table")


def _check_keys(table: dict, allowed: dict, where: str) -> None:
    for key, value in table.items():
        if key not in allowed:
            _fail(f"{where}: unknown key {key!r} (allowed: {', '.join(sorted(allowed))})")
        kind = allowed[key]
        if kind is not object and not isinstance(value, kind):
            _fail(f"{where}: {key!r} must be a {kind.__name__}, not {type(value).__name__}")


def _fail(message: str):
    raise ConfigError(f"{CONFIG_REL.as_posix()}: {message}")

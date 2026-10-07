"""Permission rules generated from `[protected]` into `.claude/settings.json` (decisions 15, 29-31, 82, 92).

Deny rules are the primary protection: Claude Code enforces them for its own file tools and the
shell commands it recognizes. `settings.json` has no comments to mark which rules are ours, so the
rules the kit wrote are recorded in `.claude/kit/generated-rules.json`; sync only adds rules and
removes recorded ones, and never touches a rule the owner wrote.
"""

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .findings import Finding
from .globs import is_bare, normalize
from .protected import KIT_GUARD

SETTINGS_REL = Path(".claude") / "settings.json"
RECORD_REL = Path(".claude") / "kit" / "generated-rules.json"
LISTS = ("deny", "ask")
CHECK = "settings"
BOM = b"\xef\xbb\xbf"


class SettingsError(Exception):
    """settings.json can't be read safely; it is left untouched."""


def _anchored(pattern: str) -> str:
    """A kit.toml glob as a root-anchored rule path with the same meaning.

    Claude Code anchors `/path` at the session's working directory (the worktree in a lane), while
    a bare `dir/**` in a deny rule matches that folder at any depth, so every rule gets the `/` form.
    A glob without an inner slash matches at any depth in kit.toml, hence `/**/`.
    """
    pattern = normalize(pattern)
    anchored = "/" in pattern.rstrip("/")
    pattern = pattern.lstrip("/")
    if pattern.endswith("/"):
        pattern += "**"
    return "/" + pattern if anchored else "/**/" + pattern


def _secret(pattern: str) -> str:
    """Bare names stay bare (Claude Code matches them at any depth, decision 31); others anchor."""
    pattern = normalize(pattern)
    return pattern if is_bare(pattern) else _anchored(pattern)


def expected_rules(protected) -> dict:
    deny = [f"Edit({_anchored(path)})" for path in protected.paths]
    for secret in protected.secrets:
        deny += [f"Read({_secret(secret)})", f"Edit({_secret(secret)})"]
    for command in protected.commands:
        # A trailing " *" also matches the bare command. Forms with options in between are the
        # hook's job: Claude Code's prefix rules don't match past options.
        deny += [f"Bash({command} *)", f"PowerShell({command} *)"]
    ask = [f"Edit({_anchored(path)})" for path in KIT_GUARD] if protected.guard_kit else []
    return {"deny": _unique(deny), "ask": _unique(ask)}


def _unique(items) -> list:
    return list(dict.fromkeys(items))


def _is_exemption(rule: str) -> bool:
    return "(!" in rule


def _around(exemption: str, expected: list) -> tuple[list, list]:
    """The kit's rules of the same tool listed before and after an exemption in [protected].secrets.

    Claude Code carves an exemption only out of the rules listed before it in the same list, and
    a `Read(!x)` only out of `Read` rules (decision 92). The order in kit.toml is the meaning: a
    name listed after the exemption denies the file again, so it must stay after it.
    """
    tool = exemption.partition("(")[0] + "("
    index = expected.index(exemption)
    same = [(i, rule) for i, rule in enumerate(expected) if rule.startswith(tool) and not _is_exemption(rule)]
    return [rule for i, rule in same if i < index], [rule for i, rule in same if i > index]


def _misplaced(rules: list, expected: list) -> list:
    """The kit's exemptions whose position in rules doesn't keep kit.toml's order."""
    misplaced = []
    for rule in expected:
        if not _is_exemption(rule) or rule not in rules:
            continue
        before, after = _around(rule, expected)
        at = rules.index(rule)
        if any(other in rules and rules.index(other) > at for other in before) or any(
            other in rules and rules.index(other) < at for other in after
        ):
            misplaced.append(rule)
    return misplaced


def _place(kept: list, added: list, expected: list) -> tuple[list, list]:
    """kept plus added, in an order with kit.toml's meaning, and the exemptions that had to move.

    A new name goes in front of an exemption already there that should cancel it, so an owner's
    rule after the exemption stays after it; anything else is appended. An exemption still out of
    order (rules reordered by hand) moves to just after the names it cancels, and names that should
    follow it move to just after it. Only positions change, never the rules.
    """
    rules = list(kept)
    for rule in added:
        targets = [
            other
            for other in rules
            if _is_exemption(other) and other in expected and rule in _around(other, expected)[0]
        ]
        if targets and not _is_exemption(rule):
            rules.insert(min(rules.index(other) for other in targets), rule)
        else:
            rules.append(rule)
    moved = _misplaced(rules, expected)
    for exemption in moved:
        before, after = _around(exemption, expected)
        rules.remove(exemption)
        at = max((rules.index(other) + 1 for other in before if other in rules), default=0)
        rules.insert(at, exemption)
        for other in reversed(after):  # each goes right after it, so the last one first
            if other in rules and rules.index(other) < rules.index(exemption):
                rules.remove(other)
                rules.insert(rules.index(exemption) + 1, other)
    return rules, moved


def read_json(path: Path, what: str) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError) as error:
        raise SettingsError(f"{what}: can't read it ({error}); left untouched") from None
    if not isinstance(data, dict):
        raise SettingsError(f"{what}: expected a JSON object; left untouched")
    return data


def _rule_lists(data: dict, what: str) -> dict:
    permissions = data.get("permissions", {})
    if not isinstance(permissions, dict):
        raise SettingsError(f"{what}: 'permissions' must be an object; left untouched")
    lists = {}
    for name in LISTS:
        rules = permissions.get(name, [])
        if not isinstance(rules, list) or not all(isinstance(rule, str) for rule in rules):
            raise SettingsError(f"{what}: 'permissions.{name}' must be a list of strings; left untouched")
        lists[name] = rules
    return lists


@dataclass(frozen=True)
class Style:
    """How the owner's settings.json is formatted, so a sync changes only the rules."""

    indent: str | int = 2
    newline: str = "\n"
    bom: bool = False


def style_of(path: Path) -> Style:
    if not path.is_file():
        return Style()
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig", "replace")
    found = re.search(r"\n([ \t]+)\S", text)
    indent = 2 if not found else ("\t" if found.group(1).startswith("\t") else len(found.group(1)))
    newline = "\r\n" if "\r\n" in text else "\n"
    return Style(indent=indent, newline=newline, bom=raw.startswith(BOM))


@dataclass
class Sync:
    settings: dict
    record: dict
    added: dict = field(default_factory=dict)
    removed: dict = field(default_factory=dict)
    moved: dict = field(default_factory=dict)
    style: Style = field(default_factory=Style)
    record_changed: bool = False

    @property
    def settings_changed(self) -> bool:
        return any(self.added.values()) or any(self.removed.values()) or any(self.moved.values())

    @property
    def changed(self) -> bool:
        return self.settings_changed or self.record_changed


def plan_sync(root: Path, config) -> Sync:
    settings = read_json(root / SETTINGS_REL, SETTINGS_REL.as_posix())
    current = _rule_lists(settings, SETTINGS_REL.as_posix())
    recorded = _rule_lists({"permissions": read_json(root / RECORD_REL, RECORD_REL.as_posix())}, RECORD_REL.as_posix())
    expected = expected_rules(config.protected)

    result = Sync(settings=settings, record={}, style=style_of(root / SETTINGS_REL))
    permissions = settings.setdefault("permissions", {})
    for name in LISTS:
        stale = [rule for rule in recorded[name] if rule not in expected[name]]
        kept = [rule for rule in current[name] if rule not in stale]
        added = [rule for rule in expected[name] if rule not in kept]
        result.removed[name] = [rule for rule in current[name] if rule in stale]
        result.added[name] = added
        rules, result.moved[name] = _place(kept, added, expected[name])
        if rules or name in permissions:
            permissions[name] = rules
        # Only rules this kit wrote: a rule the owner already had stays theirs (decision 29).
        result.record[name] = [rule for rule in expected[name] if rule in recorded[name] or rule in added]
    # A stale record must be dropped even when settings.json needs nothing (the owner removed the
    # rule by hand): kept, it would later flag, and remove, the same rule the owner re-adds.
    result.record_changed = result.record != recorded
    return result


def apply_sync(root: Path, sync: Sync) -> None:
    if sync.settings_changed:
        write_json(root / SETTINGS_REL, sync.settings, sync.style)
    if sync.record_changed or sync.settings_changed:
        write_json(root / RECORD_REL, sync.record, Style())


def write_json(path: Path, data: dict, style: Style) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=style.indent, ensure_ascii=False) + "\n"
    # Bytes, not text mode (which writes CRLF on Windows), in the owner's style.
    raw = (BOM if style.bom else b"") + text.replace("\n", style.newline).encode("utf-8")
    temporary = path.with_name(path.name + ".kit-tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, path)  # atomic: a failed write never leaves half a settings.json


def describe(sync: Sync) -> str:
    lines = []
    for verb, changes in (("added", sync.added), ("removed", sync.removed), ("moved", sync.moved)):
        for name in LISTS:
            lines += [f"  {SETTINGS_REL.as_posix()}: {verb} {name}: {rule}" for rule in changes.get(name, [])]
    if sync.record_changed and not sync.settings_changed:
        lines.append(f"  {RECORD_REL.as_posix()}: dropped rules the kit no longer generates")
    return "\n".join(lines)


def check(root: Path, config) -> list[Finding]:
    """Drift between [protected] and settings.json: expected rules missing, recorded rules stale."""
    settings = read_json(root / SETTINGS_REL, SETTINGS_REL.as_posix())
    current = _rule_lists(settings, SETTINGS_REL.as_posix())
    recorded = _rule_lists({"permissions": read_json(root / RECORD_REL, RECORD_REL.as_posix())}, RECORD_REL.as_posix())
    expected = expected_rules(config.protected)
    where = SETTINGS_REL.as_posix()
    findings = []
    for name in LISTS:
        for rule in expected[name]:
            if rule not in current[name]:
                message = f"missing {name} rule {rule}; run `kit settings sync`"
                findings.append(Finding(path=where, line=0, check=CHECK, message=message))
        for rule in recorded[name]:
            if rule not in expected[name] and rule in current[name]:
                message = f"{name} rule {rule} is no longer in [protected]; run `kit settings sync`"
                findings.append(Finding(path=where, line=0, check=CHECK, message=message))
        for rule in _misplaced(current[name], expected[name]):
            message = (
                f"{name} rule {rule} is out of order with the rules [protected].secrets puts around it, "
                "so it cancels the wrong ones; run `kit settings sync`"
            )
            findings.append(Finding(path=where, line=0, check=CHECK, message=message))
    return findings

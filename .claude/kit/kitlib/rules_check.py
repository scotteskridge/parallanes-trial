"""Forbidden-pattern rules from `[[checks.rules]]` in kit.toml, applied line by line."""

import posixpath

from .comments import split_lines, strip_comments
from .findings import Finding
from .globs import matches_any, normalize

CHECK = "rules"


def applies(rule, path: str) -> bool:
    return matches_any(path, rule.paths) and not matches_any(path, rule.exclude)


def covered(config, path: str) -> bool:
    """Whether any rule applies to path; callers skip reading files nothing covers."""
    return any(applies(rule, normalize(path)) for rule in config.rules)


def check(config, files) -> list[Finding]:
    """Findings for files, an iterable of (project-relative path, text) pairs."""
    findings = []
    for path, text in files:
        path = normalize(path)
        rules = [rule for rule in config.rules if applies(rule, path)]
        if not rules:
            continue
        suffix = posixpath.splitext(path)[1]
        raw_lines = split_lines(text)
        stripped = strip_comments(text, suffix)
        for rule in rules:
            lines = stripped if rule.ignore_comments else raw_lines
            for number, line in enumerate(lines, start=1):
                if rule.regex.search(line):
                    findings.append(Finding(path=path, line=number, check=CHECK, message=rule.message, rule=rule.id))
    return sorted(findings)

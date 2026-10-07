"""What a check found, and how it is shown to people and agents."""

from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class Finding:
    path: str
    line: int
    check: str
    message: str
    rule: str = ""


def format_findings(findings) -> str:
    """One `path:line: [check/rule] message` line per finding, sorted by location.

    Line 0 means the finding is about the whole file (a protected path changed): no line is shown.
    """
    lines = []
    for finding in sorted(findings):
        tag = f"{finding.check}/{finding.rule}" if finding.rule else finding.check
        where = f"{finding.path}:{finding.line}:" if finding.line else f"{finding.path}:"
        lines.append(f"{where} [{tag}] {finding.message}")
    return "\n".join(lines)

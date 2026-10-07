"""Who owns a file that more than one lane's `owns` matches (decision 97).

Shared paths come first: every lane may change them. Otherwise the lane whose matching pattern is
most specific owns the file (`specificity`). Order in kit.toml never matters, so a split doesn't
silently depend on line order. The same pattern in two lanes is an error when kit.toml loads
(config); two different patterns can still tie on a real file, and then no lane owns it until one is
made more specific. The rule is lanekeeper's (docs/survey-lanekeeper.md), refined in review; no code
was borrowed. The ownership hook, the boundary check and the overlap lists all use it.
"""

import os
import re
from dataclasses import dataclass

from . import gitfiles, globs

POLICY = ".claude/kit.toml"
_WILDCARDS = re.compile(r"\*\*|\*|\?|\[[^\]]*\]")


def canonical(pattern: str) -> str:
    """The pattern written out in full, so patterns that match the same files compare equal.

    globs anchors a pattern only when it has a slash before its end: `main.py` and `src/` match at
    any depth (`**/main.py`, `**/src/**`), while `/main.py` and `src/**` start at the root.
    """
    pattern = globs.normalize(pattern)
    anchored = "/" in pattern.rstrip("/")
    if pattern.endswith("/"):
        pattern += "**"
    pattern = pattern.lstrip("/")
    if not anchored:
        pattern = "**/" + pattern
    while "**/**" in pattern:
        pattern = pattern.replace("**/**", "**")
    if pattern == "**/*" or pattern.endswith("/**/*"):  # `src/**/*` is every file under src/, as `src/**` is
        pattern = pattern[:-2]
    return pattern


def specificity(pattern: str) -> tuple[int, bool, int, int, int]:
    """Larger is more specific: compared in order, the first difference decides.

    Wildcard-free segments (`src/core/**` over `src/**`); then rooted over any depth (`src/**` over
    `**/conftest.py`); then more literal characters (`src/**/*_test.py` over `src/**`); then fewer
    `**` (`src/*` over `src/**`); then fewer other wildcards. Length alone isn't used: `src/**` is
    longer than `src/*` but matches more (review round 1). A heuristic: a pattern it ranks wrongly
    in an odd case is settled by rewording it, and a tie is reported, never decided silently.
    """
    pattern = canonical(pattern)
    parts = pattern.split("/")
    literal = sum(1 for part in parts if not _WILDCARDS.search(part))
    found = _WILDCARDS.findall(pattern)
    double = found.count("**")  # inside a segment too: `src/a**` crosses folders (review round 2)
    characters = len(_WILDCARDS.sub("", pattern).replace("/", ""))
    return literal, parts[0] != "**", characters, -double, -(len(found) - double)


@dataclass(frozen=True)
class Claim:
    owner: str | None  # None: no lane claims the file, or a tie
    pattern: str | None  # the owner's most specific matching pattern
    losers: tuple = ()  # (lane, its best pattern) for the other lanes that match, most specific first
    tied: tuple = ()  # (lane, pattern) for every lane in a tie, by lane name


class Owners:
    """The rule for one config, compiled once: `lanes status` judges every tracked file with it."""

    def __init__(self, config):
        self.shared = globs.file_matcher(config.lane_settings.shared_paths)
        self.lanes = []
        for lane in config.lanes:
            ranked = sorted(lane.owns, key=specificity, reverse=True)
            self.lanes.append(
                (
                    lane.name,
                    globs.file_matcher(lane.owns),
                    [(p, specificity(p), globs.file_matcher([p])) for p in ranked],
                )
            )

    def claim(self, path: str, candidates=None) -> Claim:
        """Which lane owns path, by `owns` alone (shared paths are the caller's first question)."""
        best = []
        for name, matches, ranked in self.lanes if candidates is None else candidates:
            if matches(path):
                pattern, score = next((p, score) for p, score, one in ranked if one(path))
                best.append((score, name, pattern))
        if not best:
            return Claim(None, None)
        top = max(score for score, _, _ in best)
        winners = sorted((name, pattern) for score, name, pattern in best if score == top)
        if len(winners) > 1:
            return Claim(None, None, tied=tuple(winners))
        losers = tuple((name, pattern) for score, name, pattern in sorted(best, reverse=True) if score != top)
        return Claim(winners[0][0], winners[0][1], losers)

    def overlapping(self, path: str) -> list:
        """The lanes that match path, when it isn't shared and more than one does; else []."""
        if self.shared(path):
            return []
        matching = [entry for entry in self.lanes if entry[1](path)]
        return matching if len(matching) > 1 else []


def claim(config, path: str) -> Claim:
    return Owners(config).claim(path)


def why_not(config, lane, path: str) -> str | None:
    """Why lane may not change path, or None when it may (shared, or the lane owns it)."""
    owners = Owners(config)
    if owners.shared(path):
        return None
    found = owners.claim(path)
    if found.owner == lane.name:
        return None
    if found.tied:
        names = " and ".join(repr(name) for name, _ in found.tied)
        patterns = ", ".join(pattern for _, pattern in found.tied)
        return f"lanes {names} claim it equally ({patterns}); make one pattern in {POLICY} more specific"
    if found.owner is None:
        return "no lane owns it"
    mine = dict(found.losers).get(lane.name)
    if mine is None:
        return f"owned by lane {found.owner!r}"
    return f"{mine} matches it, but lane {found.owner!r} owns it: {found.pattern} is more specific"


def same_pattern(lanes) -> tuple[str, str, str, str] | None:
    """(lane, other lane, its pattern, the other's) for the first pattern two lanes both list."""
    seen = {}
    for lane in lanes:
        for pattern in lane.owns:
            key = canonical(pattern)
            key = key.lower() if os.name == "nt" else key  # matching ignores case there (globs)
            first = seen.setdefault(key, (lane.name, pattern))
            if first[0] != lane.name:
                return first[0], lane.name, first[1], pattern
    return None


def overlaps(config, paths) -> tuple[list[str], list[str]]:
    """(notes, problems) about the files more than one lane claims, grouped by outcome.

    A note says which lane wins; a problem is a tie, which no lane owns until someone decides.
    """
    owners = Owners(config)
    groups: dict = {}
    for path in paths:
        matching = owners.overlapping(path)
        if matching:
            groups.setdefault(owners.claim(path, matching), []).append(path)
    notes, problems = [], []
    for found, grouped in groups.items():
        count = f"{len(grouped)} file{'' if len(grouped) == 1 else 's'}"
        example = f"e.g. {min(grouped)}"
        if found.tied:
            who = " and ".join(f"{pattern} ({name})" for name, pattern in found.tied)
            settle = f"no lane owns it until one pattern in {POLICY} is more specific"
            problems.append(f"{who} claim {count} equally, {example}: {settle}")
        else:
            others = ", ".join(f"{pattern} ({name})" for name, pattern in found.losers)
            notes.append(f"{found.pattern} ({found.owner}) wins over {others}: {count}, {example}")
    return sorted(notes), sorted(problems)


def tracked_overlaps(root, config) -> tuple[list[str], list[str]]:
    """overlaps() for the files git tracks in root; a git failure is a problem line, not a traceback."""
    if len(config.lanes) < 2:
        return [], []
    try:
        paths = gitfiles.tracked(root)
    except gitfiles.GitError as error:
        return [], [f"files two lanes claim not checked: {error}"]
    return overlaps(config, paths)

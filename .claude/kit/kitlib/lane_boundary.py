"""The lane-boundary check (decision 96): a lane's change lands only in its own and the shared paths.

The ownership hook asks before an out-of-lane edit and fails open (decision 41); this check is the
backstop when the work lands, in `kit lanes finish`, the pre-commit hook and CI, and it fails closed.
Rules taken from lanekeeper's merge check (docs/survey-lanekeeper.md); no code was borrowed.
Paths come from kitlib.gitfiles, where a rename already counts as a change to both names and a
base that can't be diffed is an error, never a clean result.
"""

import os

from kitlib import gitfiles, globs, lane_owners
from kitlib.config import ConfigError, lanes_only
from kitlib.findings import Finding

CHECK = "lanes"
# For a human landing a cross-lane change on purpose; an agent setting it is blocked (kitlib.commands).
# Only where the person runs the kit: CI has no override, so a PR's way through is a non-lane branch.
ALLOW_VARIABLE = "KIT_ALLOW_CROSS_LANE"
ADVICE = (
    f"To land a cross-lane change on purpose, a person uses a branch that isn't a lane's, or sets "
    f"{ALLOW_VARIABLE}=1 locally; an agent stops and asks."
)
# The lane policy itself: a lane that could change it could widen its own paths inside its own change.
POLICY = lane_owners.POLICY


def lanes_before(root, config, base: str | None, lane_name: str):
    """(the config whose lanes judge the change, that lane), or None when there's no such lane.

    kit.toml as it was at base, not as the change left it, so a lane that renames or drops itself (or
    widens `owns`) is judged by the lanes it started from. No base (a brand-new project) or no
    kit.toml there: the current one. Only that lane's file version is validated, so an old kit.toml
    never blocks a branch that isn't a lane's at the base.
    """
    judge = config
    text = gitfiles.show(root, base, POLICY) if base else None
    if text is not None:
        try:
            judge = lanes_only(text, lane_name)
        except ConfigError as error:  # fail closed, but say which version is wrong: not the file on disk
            where = "HEAD" if base == "HEAD" else f"commit {base[:12]}"
            detail = str(error).removeprefix(POLICY + ": ")
            raise ConfigError(f"{POLICY} at {where}: its lanes don't load, so nothing was checked: {detail}") from None
        if judge is None:
            return None
    lane = next((lane for lane in judge.lanes if lane.name == lane_name), None)
    return (judge, lane) if lane else None


def lane_for_branch(config, branch: str | None):
    """The lane whose `<lane>/<task>` branch this is, or None: other branches aren't lane work."""
    if not branch or "/" not in branch:
        return None
    name = branch.split("/", 1)[0]
    return next((lane for lane in config.lanes if lane.name == name), None)


def ci_branch() -> str | None:
    """The pull request's branch in GitHub Actions, which checks out a detached merge commit."""
    return os.environ.get("GITHUB_HEAD_REF") or None


def check(config, lane, paths) -> list[Finding]:
    findings = []
    for path in paths:
        path = globs.normalize(path)
        if globs.matches_any_file(path, [POLICY]):
            why = "the lane policy belongs to no lane"
        else:
            why = lane_owners.why_not(config, lane, path)  # the hook's rule too (decision 97)
            if why is None:
                continue
        findings.append(Finding(path=path, line=0, check=CHECK, message=f"outside lane {lane.name!r}: {why}"))
    return sorted(findings)


def allowed_by_human() -> bool:
    return os.environ.get(ALLOW_VARIABLE) == "1"

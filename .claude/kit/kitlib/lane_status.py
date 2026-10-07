"""`kit lanes status`: every lane at a glance, from local git data plus `gh` when it can (decision 43)."""

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import lane_merged, lane_owners
from .lanes import (
    ahead_behind,
    branch_of,
    changes,
    git,
    integration_tip,
    lane_folder,
    main_checkout,
    registered_worktrees,
    same_path,
    toplevel,
    unpushed_count,
    upstream_gone,
)

UNKNOWN = "PR: unknown"


@dataclass
class LaneStatus:
    name: str
    folder: Path
    state: str  # "ok", "not created", "missing"
    branch: str | None = None  # None: detached
    ahead: int = 0
    behind: int = 0
    changed: int = 0  # tracked files: unfinished work
    untracked: int = 0  # not unfinished work: test reports and the like (decision 52)
    unpushed: int | None = None  # None: no upstream
    gone: bool = False  # pushed once, but the remote branch is gone
    pr: str = UNKNOWN
    here: bool = False


@dataclass
class Status:
    main: Path
    main_branch: str | None
    tip: str | None
    lanes: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    notes: list = field(default_factory=list)


def status(start: Path, config, offline: bool = False) -> Status:
    main = main_checkout(start)
    tip = integration_tip(main, config)
    result = Status(main=main, main_branch=branch_of(main), tip=tip)
    integration = config.lane_settings.integration_branch
    if config.lane_settings.merge_mode == "local" and result.main_branch == integration:
        # `git push . HEAD:<integration>` (plan 05) refuses while the branch is checked out (decision 38).
        result.warnings.append(
            f"local mode: the main checkout has {integration} checked out, so lanes can't fast-forward it. "
            f"Run there: git switch --detach {integration}"
        )
    top = toplevel(Path(start))
    gh = None if offline else shutil.which("gh")
    registered = registered_worktrees(main)  # once, not once per lane: each git call costs ~35 ms on Windows
    for lane in config.lanes:
        folder = lane_folder(main, config, lane)
        if not any(same_path(path, folder) for path in registered):
            result.lanes.append(LaneStatus(lane.name, folder, "not created"))
            continue
        if not folder.is_dir():
            result.lanes.append(LaneStatus(lane.name, folder, "missing"))
            continue
        changed, untracked = changes(folder)
        entry = LaneStatus(lane.name, folder, "ok", branch=branch_of(folder), changed=changed, untracked=len(untracked))
        entry.here = top is not None and same_path(top, folder)
        if tip:
            entry.ahead, entry.behind = ahead_behind(folder, tip)
        if entry.branch:
            entry.unpushed = unpushed_count(folder)
            entry.gone = entry.unpushed is None and upstream_gone(folder)
            if gh:
                entry.pr = pr_state(folder, entry.branch, tip)
                if entry.pr == UNKNOWN:
                    gh = None  # gh failed or hung: don't make every other lane wait for it too
        result.lanes.append(entry)
    # Decision 97: who wins a file two lanes claim is a note (a normal split); a tie is a problem.
    notes, problems = lane_owners.tracked_overlaps(main, config)
    result.notes += notes
    result.warnings += problems
    return result


def pr_state(folder: Path, branch: str, tip: str | None) -> str:
    """The newest PR for this branch's own work, or "PR: unknown" whenever gh can't tell (decision 43).

    Matched by commit, not just by name (decision 46): a reused task slug must not show the earlier
    branch's PR. Found in plan 05's live check.
    """
    prs, error = lane_merged.pull_requests(folder, branch, "all", timeout=10)
    if error:
        return UNKNOWN
    head = git(folder, "rev-parse", "HEAD").strip()
    for pr in prs[:10]:  # gh lists the newest first; a long-lived slug mustn't cost hundreds of git calls
        shared = lane_merged.shares_work(folder, pr["headRefOid"], head, tip)
        if shared:
            return f"PR #{pr['number']} {pr['state']}"
        if shared is None and pr["state"] == "OPEN":
            # An open PR follows origin's branch (pushed from elsewhere, or GitHub's "Update branch"):
            # saying "none" could prompt a duplicate PR.
            return f"PR #{pr['number']} OPEN (head not fetched)"
    return "PR: none"


def format_status(result: Status) -> str:
    main = result.main_branch or "detached HEAD"
    lines = [f"Main checkout: {result.main} · {main}"]
    lines += [f"  ! {warning}" for warning in result.warnings]
    for lane in result.lanes:
        try:
            shown = Path(os.path.relpath(lane.folder, result.main)).as_posix()
        except ValueError:  # another drive on Windows
            shown = str(lane.folder)
        where = f"{lane.name} {shown}" + (" (this folder)" if lane.here else "")
        if lane.state == "not created":
            lines.append(f"{where} · not created (kit lanes create {lane.name})")
            continue
        if lane.state == "missing":
            lines.append(f"{where} · folder missing (git worktree prune, then kit lanes create {lane.name})")
            continue
        parts = [where]
        parts.append(lane.branch if lane.branch else "detached (between tasks)")
        if result.tip:
            parts.append(f"{lane.ahead} ahead, {lane.behind} behind {result.tip}")
        if lane.changed:
            parts.append(f"{lane.changed} changed")
        if lane.untracked:
            parts.append(f"{lane.untracked} untracked")
        if lane.branch:
            if lane.gone:
                parts.append("pushed branch gone from origin")
            else:
                parts.append("not pushed" if lane.unpushed is None else f"{lane.unpushed} unpushed")
            parts.append(lane.pr)
        lines.append(" · ".join(parts))
    lines += [f"Note: {note}" for note in result.notes]
    return "\n".join(lines)

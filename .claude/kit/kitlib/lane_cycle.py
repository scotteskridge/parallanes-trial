"""`kit lanes start / sync / finish`: one task's cycle inside a lane (decisions 11, 12, 46-51).

Each command runs only in a lane folder and acts on that lane's worktree. It returns short lines an
agent can quote; a refusal is a LaneError whose message says why and what to do next.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

from kitlib import gitfiles, lane_boundary, lane_merged, lane_pr, lanes
from kitlib.config import ConfigError
from kitlib.findings import format_findings
from kitlib.lanes import LaneError, Unfinished

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,49}$")  # the lane-name pattern, at most 50 characters
IN_PROGRESS = {
    "rebase-merge": "rebase",
    "rebase-apply": "rebase",
    "MERGE_HEAD": "merge",
    "CHERRY_PICK_HEAD": "cherry-pick",
}


# ---- the three commands --------------------------------------------------------------------------


def start(folder: Path, config, task: str, abandon: bool = False) -> list[str]:
    lane, top, _ = _here(folder, config)
    if not SLUG.match(task):
        raise LaneError(
            f"task {task!r}: use lowercase letters, digits and hyphens, at most 50 characters (e.g. fix-login)"
        )
    _nothing_in_progress(top)
    note = _clean(top)
    new = f"{lane.name}/{task}"
    if _exists(top, f"refs/heads/{new}"):
        raise LaneError(f"branch {new} already exists: pick another task name")
    current = lanes.branch_of(top)
    if current is not None:
        _check_task_branch(current, lane)
    tip = _fetch_tip(top, config)
    if _exists(top, f"refs/remotes/origin/{new}"):
        # GitHub keeps head branches unless told to delete them; reusing the name would sync and
        # push against the old branch's history.
        raise LaneError(
            f"origin/{new} still exists (an earlier branch with this name): pick another task name"
            + ("" if config.lane_settings.merge_mode == "pr" else ", or `git fetch --prune` if it's gone from origin")
        )
    lines = []
    if current is None:
        here = _rev(top, "HEAD")
        if not lanes.is_ancestor(top, here, tip) and not _on_some_ref(top, here):
            # Commits made between tasks belong to no branch: switching away would orphan them.
            if not abandon:
                raise LaneError(
                    f"this lane has commits on no branch (HEAD {here[:12]}) that a new task would leave behind. "
                    f"Keep them with `git branch {lane.name}/<name>`, "
                    f"or drop them on purpose: kit lanes start {task} --abandon"
                )
            lines.append(
                f"Abandoned commits on no branch at {here}. To get them back: git branch {lane.name}/recovered {here}"
            )
    else:
        done, why = lane_merged.merged(top, config, current, tip)
        if not done and not abandon:
            raise LaneError(f"{why}. To drop {current} on purpose: kit lanes start {task} --abandon")
        sha = _rev(top, "HEAD")
        _git(top, "switch", "-q", "--detach", tip)
        _git(top, "branch", "-q", "-D", current)  # proved merged above, or abandoned on request
        lines.append(
            f"Deleted {current}: {why}."
            if done
            else f"Abandoned {current} at {sha}. To get it back: git branch {current} {sha}"
        )
    # --no-track: otherwise git makes origin/<integration> the upstream and "pushed?" checks lie (decision 47).
    _git(top, "switch", "-q", "--no-track", "-c", new, tip)
    lines.append(f"On {new}, from {tip} ({_rev(top, 'HEAD')[:12]}).")
    leftovers = [
        name
        for name in _git(top, "for-each-ref", "--format=%(refname:short)", f"refs/heads/{lane.name}/").split()
        if name != new
    ]
    if leftovers:
        lines.append(f"Other {lane.name}/ branches, left alone: {', '.join(leftovers)}")
    return lines + note


def sync(folder: Path, config) -> list[str]:
    lane, top, _ = _here(folder, config)
    _nothing_in_progress(top)
    branch = _task_branch(top, lane)
    note = _clean(top)
    return _bring_in(top, branch, _fetch_tip(top, config)) + note


def finish(folder: Path, config, title: str | None = None, body_file: str | None = None) -> list[str]:
    lane, top, main = _here(folder, config)
    _nothing_in_progress(top)
    branch = _task_branch(top, lane)
    _say(_clean(top))  # untracked files stay out of what lands; say so before the tests add more
    command = config.project.get("test_command", "").strip()
    if not command:
        raise LaneError(
            "no test_command in .claude/kit.toml: finish runs the tests before anything lands, so set it first"
        )
    body, body_text = None, None
    if body_file == "-":
        # Read now, before the tests run: /wrap-up passes the body on stdin so it needs no file,
        # and a file outside the lane's paths would make the ownership hook ask (plan 07).
        # LF only: a PowerShell or Windows text pipe sends CRLF.
        try:
            body_text = sys.stdin.buffer.read().decode("utf-8-sig").replace("\r\n", "\n")
        except UnicodeDecodeError as error:
            raise LaneError(
                f"--body-file -: the PR body on stdin isn't UTF-8 ({error.reason} at byte {error.start})"
            ) from None
        if not body_text.strip():
            raise LaneError("--body-file -: no PR body on stdin")
    elif body_file:
        body = os.path.abspath(body_file)
        if not Path(body).is_file():
            raise LaneError(f"body file {body_file} not found")
    local = config.lane_settings.merge_mode == "local"
    integration = config.lane_settings.integration_branch
    if local:
        _nobody_holds(main, integration)
    tip = _fetch_tip(top, config)
    if lanes.ahead_behind(top, tip)[0] == 0:
        raise LaneError(f"nothing to finish: {branch} has no commits that aren't in {tip}")
    _within_lane(top, config, lane, tip)
    tested_on = _test_what_lands(top, branch, tip, command)
    if local:
        return _land_locally(top, main, config, branch, tested_on, command)
    return lane_pr.open_pr(top, integration, branch, tip, title, body, body_text)


# ---- steps ---------------------------------------------------------------------------------------


def _within_lane(top: Path, config, lane, tip: str) -> None:
    """Refuse a change outside the lane's own and shared paths (decision 96), before the tests run.

    The merge-base diff, as the pull request will show it: only this branch's own changes, judged by
    the lanes as they were at the merge base (a lane can't widen itself in its own change).
    """
    try:
        paths = gitfiles.touched_since(top, tip)
        base = gitfiles.merge_base(top, tip)
    except gitfiles.GitError as error:
        raise LaneError(f"can't tell what this branch changed, so nothing was checked: {error}") from None
    try:
        found = lane_boundary.lanes_before(top, config, base, lane.name)
    except ConfigError as error:
        raise LaneError(str(error)) from None  # it already names the commit and says nothing was checked
    # A lane missing at the base was added by this branch: judged by today's lanes, and its
    # kit.toml change is a finding, so this is stricter than the base, never looser.
    judge, before = found or (config, lane)
    findings = lane_boundary.check(judge, before, paths)
    if not findings:
        return
    pr_mode = config.lane_settings.merge_mode == "pr"
    if lane_boundary.allowed_by_human() and not pr_mode:
        _say([f"{len(findings)} cross-lane change(s) allowed by {lane_boundary.ALLOW_VARIABLE}=1."])
        return
    why = "this branch changes files outside its lane:\n" + format_findings(findings) + "\n"
    if lane_boundary.allowed_by_human():  # PR mode: CI has no override, so a push would only go red
        why += f"{lane_boundary.ALLOW_VARIABLE} doesn't reach CI: land this from a branch that isn't a lane's."
        raise LaneError(why)
    raise LaneError(why + lane_boundary.ADVICE)


def _test_what_lands(top: Path, branch: str, tip: str, command: str) -> str:
    """Sync, then test exactly the commit that will be pushed or fast-forwarded. Returns the tip's
    commit it was synced with, so a later refusal can tell whether the tip moved meanwhile."""
    tip_sha = _rev(top, tip)
    _say(_bring_in(top, branch, tip))  # printed now, so a later failure doesn't hide that it happened
    if lanes.ahead_behind(top, tip)[0] == 0:
        # The rebase dropped every commit: the same changes had already landed. The branch was
        # rewritten, so this isn't "refused, nothing changed" (exit 2).
        raise Unfinished(
            f"nothing left to finish: {branch} was rebased onto {tip} and is now empty, its changes are "
            "already in. Start the next task."
        )
    tested = _rev(top, "HEAD")
    _run_tests(top, command)
    # Tracked changes only: test runners write reports and caches (junit.xml, coverage) that aren't
    # part of what lands; untracked files were ruled out before the tests by _clean.
    tracked = _git(top, "status", "--porcelain", "--untracked-files=no").strip()
    if lanes.branch_of(top) != branch or _rev(top, "HEAD") != tested or tracked:
        raise Unfinished(
            f"the test command changed the lane (it should leave {branch} at {tested[:12]}, clean): "
            "nothing was pushed or merged. Look at what it did, then run `kit lanes finish` again."
        )
    return tip_sha


def _bring_in(top: Path, branch: str, tip: str) -> list[str]:
    """Rebase a branch that was never pushed; merge one that was, so nothing under review is rewritten."""
    behind = lanes.ahead_behind(top, tip)[1]
    if not behind:
        return [f"{branch} is up to date with {tip}."]
    pushed = _exists(top, f"refs/remotes/origin/{branch}")
    verb = "merge" if pushed else "rebase"
    result = lanes.run_git(top, "merge", "-q", "--no-edit", tip) if pushed else lanes.run_git(top, "rebase", "-q", tip)
    if result.returncode != 0:
        conflicts = _git(top, "diff", "--name-only", "--diff-filter=U").split()
        if not conflicts:
            raise LaneError(f"git {verb} {tip} failed: {(result.stderr or result.stdout).strip()}")
        # Left in progress on purpose: resolving the conflict is the work (decision 48). The lane is
        # mid-way, not untouched, so this is "unfinished" (exit 1), not a refusal.
        raise Unfinished(
            f"conflict while bringing {tip} into {branch} ({verb}): {', '.join(conflicts)}. "
            f"Fix those files, `git add` them, then `git {verb} --continue`; to give up instead: "
            f"`git {verb} --abort`."
        )
    return [f"{'Merged' if pushed else 'Rebased onto'} {tip}: {behind} new commit(s)."]


def _run_tests(top: Path, command: str) -> None:
    print(f"Running the tests: {command}", flush=True)
    sys.stderr.flush()
    try:
        # Through the shell: real test commands chain (`npm test && ...`); the value comes from the
        # committed, protected kit.toml (decision 50). Output streams straight to the terminal.
        result = subprocess.run(command, shell=True, cwd=top)
    except OSError as error:
        raise Unfinished(f"can't run the tests ({error}): nothing was pushed or merged") from None
    if result.returncode != 0:
        raise Unfinished(
            f"tests failed (exit {result.returncode}): nothing was pushed or merged. "
            "Fix them, commit, and run `kit lanes finish` again."
        )


def _land_locally(top: Path, main: Path, config, branch: str, tip_sha: str, command: str) -> list[str]:
    integration = config.lane_settings.integration_branch
    for attempt in (1, 2):
        pushed = lanes.run_git(top, "push", "-q", ".", f"HEAD:refs/heads/{integration}")  # a fast-forward or nothing
        if pushed.returncode == 0:
            break
        moved = _exists(top, f"refs/heads/{integration}") and _rev(top, f"refs/heads/{integration}") != tip_sha
        if attempt == 2 or not moved:
            # Only a race (another lane landed first) is worth a retry; anything else is reported as is.
            raise Unfinished(f"the tests passed, but {integration} couldn't be fast-forwarded: {pushed.stderr.strip()}")
        _nobody_holds(main, integration)
        _say([f"{integration} moved while the tests ran (another lane finished): syncing and testing again."])
        tip_sha = _test_what_lands(top, branch, _fetch_tip(top, config), command)
    sha = _rev(top, "HEAD")
    _git(top, "switch", "-q", "--detach", integration)
    # -D, not -d: -d judges against the branch's upstream (a backup push), but the push above
    # just put this exact commit into the integration branch.
    _git(top, "branch", "-q", "-D", branch)
    return [
        f"{integration} fast-forwarded to {sha[:12]}; {branch} deleted. Between tasks: next, kit lanes start <task>."
    ]


# ---- checks and git helpers ----------------------------------------------------------------------


def _here(folder: Path, config):
    lane, top, main = lanes.find_current(Path(folder), config)
    if lane is None:
        names = ", ".join(lane.name for lane in config.lanes) or "none"
        raise LaneError(
            f"not a lane folder: run this inside {config.lane_settings.worktree_root}/<lane> (lanes: {names})"
        )
    return lane, top, main


def _nothing_in_progress(top: Path) -> None:
    paths = _git(
        top, "rev-parse", "--path-format=absolute", *[arg for name in IN_PROGRESS for arg in ("--git-path", name)]
    )
    for name, path in zip(IN_PROGRESS, paths.splitlines(), strict=True):
        if Path(path).exists():
            kind = IN_PROGRESS[name]
            raise LaneError(
                f"a {kind} is in progress here: "
                f"finish it (`git {kind} --continue`) or undo it (`git {kind} --abort`) first"
            )


def _clean(top: Path) -> list[str]:
    """Refuse tracked changes; return a note for untracked files.

    Untracked files don't block (owner's call): test runners leave reports behind, and refusing
    would push an agent to `git add -A` them into the branch. git itself still refuses a switch
    that would overwrite one.
    """
    tracked, untracked = lanes.changes(top)
    if tracked:
        raise LaneError(f"{tracked} uncommitted change(s) to tracked files in this lane: commit or stash them first")
    if not untracked:
        return []
    shown = ", ".join(untracked[:5]) + (f" and {len(untracked) - 5} more" if len(untracked) > 5 else "")
    # The tests can see these files but they won't land: a forgotten `git add` must not look fine.
    return [
        f"Note: untracked, so the tests see them but they won't land: {shown}. "
        "Commit any that belong to the task (git add <file>); put generated ones in .gitignore."
    ]


def _task_branch(top: Path, lane) -> str:
    branch = lanes.branch_of(top)
    if branch is None:
        raise LaneError("between tasks: no task branch here. Start one with: kit lanes start <task>")
    _check_task_branch(branch, lane)
    return branch


def _check_task_branch(branch: str, lane) -> None:
    if not branch.startswith(lane.name + "/"):
        raise LaneError(
            f"{branch!r} isn't a {lane.name}/<task> branch, so the kit leaves it alone: switch away from it first"
        )


def _nobody_holds(main: Path, integration: str) -> None:
    """git refuses to fast-forward a branch that any worktree has checked out (decision 38)."""
    entries = _git(main, "worktree", "list", "--porcelain", "-z").split("\0\0")
    for entry in entries:
        fields = entry.strip("\0").split("\0")
        if f"branch refs/heads/{integration}" in fields and fields[0].startswith("worktree "):
            folder = fields[0][len("worktree ") :]
            if not Path(folder).is_dir():
                raise LaneError(
                    f"local mode: git still records {folder} (now gone) as having {integration} checked out. "
                    "Run: git worktree prune (after `git worktree unlock` if it is locked)"
                )
            raise LaneError(
                f"local mode: {folder} has {integration} checked out, so it can't be fast-forwarded. "
                f"Run there: git switch --detach {integration}"
            )


def _fetch_tip(top: Path, config) -> str:
    """The integration tip, fetched first in PR mode (local mode works offline)."""
    if config.lane_settings.merge_mode == "pr" and "origin" in _git(top, "remote").split():
        # --prune: a head branch GitHub deleted after the merge mustn't look pushed or block its name.
        # run_git's longer timeout: big repos fetch slowly.
        fetched = lanes.run_git(top, "fetch", "-q", "--prune", "origin")
        if fetched.returncode != 0:
            raise LaneError(f"can't fetch origin, so the integration tip would be stale: {fetched.stderr.strip()}")
    tip = lanes.integration_tip(top, config)
    if tip is None:
        raise LaneError(
            f"integration branch {config.lane_settings.integration_branch!r} not found (locally or on origin)"
        )
    return tip


def _on_some_ref(top: Path, commit: str) -> bool:
    # Local branches only: remote-tracking refs can vanish on the next `fetch --prune`, and local
    # mode never fetches, so they may already be stale.
    return bool(_git(top, "for-each-ref", "--count=1", "--contains", commit, "refs/heads").strip())


def _say(lines: list[str]) -> None:
    if lines:
        print("\n".join(lines), flush=True)


def _exists(top: Path, ref: str) -> bool:
    return bool(_git(top, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}", check=False).strip())


def _rev(top: Path, ref: str) -> str:
    return _git(top, "rev-parse", ref).strip()


def _git(top: Path, *args: str, check: bool = True) -> str:
    return lanes.git(top, *args, check=check)

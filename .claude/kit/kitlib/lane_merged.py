"""Was a task branch merged? Proved from git, or from the PR at the branch's exact commit (decision 46).

Never a guess: a squash or rebase merge leaves nothing in local history, so PR mode asks `gh`, and
only a PR whose head commit is the branch tip counts (a reused slug could match an old PR, §15).
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

from kitlib import lanes


def merged(folder: Path, config, branch: str, tip: str) -> tuple[bool, str]:
    """(True, how) when branch is merged into tip; otherwise (False, why not, as advice)."""
    head = lanes.git(folder, "rev-parse", f"refs/heads/{branch}").strip()
    if lanes.is_ancestor(folder, head, tip):
        return True, f"{branch} is in {tip}"
    if config.lane_settings.merge_mode != "pr":
        return False, f"{branch} has commits that aren't in {tip} yet: finish it with `kit lanes finish`"
    prs, error = pull_requests(folder, branch, "all")
    if error:
        return False, f"{branch} isn't in {tip} and its PR can't be checked ({error}), so it may not be merged"
    holding = [pr for pr in prs if _holds(folder, pr, head)]
    integration = config.lane_settings.integration_branch
    landed = [pr for pr in holding if pr["state"] == "MERGED" and pr["baseRefName"] == integration]
    if landed:
        return True, f"{branch} was merged by PR #{landed[0]['number']}"
    at_head = {pr["state"]: pr for pr in holding}
    if "MERGED" in at_head:
        # Only stacked PRs, merged into a parent branch: the work hasn't reached the integration branch.
        pr = at_head["MERGED"]
        return False, f"PR #{pr['number']} merged {branch} into {pr['baseRefName']}, not {integration}"
    if "OPEN" in at_head:
        pr = at_head["OPEN"]
        return False, f"PR #{pr['number']} for {branch} is still open ({pr.get('url', '')}): wait for it to merge"
    if "CLOSED" in at_head:
        pr = at_head["CLOSED"]
        return False, f"PR #{pr['number']} for {branch} was closed without merging ({pr.get('url', '')})"
    if prs:
        numbers = ", ".join(f"#{pr['number']}" for pr in prs)
        return False, (
            f"the PRs named {branch} ({numbers}) are at other commit(s) than its tip {head[:12]}: "
            "commits were added after the PR, or an older branch had the same name"
        )
    return False, f"there is no PR for {branch} at {head[:12]}"


def _holds(folder: Path, pr: dict, head: str) -> bool:
    """The PR's head is the branch tip, or a newer commit built on it (GitHub's "Update branch", a
    web edit): either way every local commit went into that PR. A head git doesn't have is fetched
    from GitHub's `refs/pull/<n>/head` (the head branch may be deleted); if that fails, no claim."""
    pr_head = pr["headRefOid"]
    if pr_head == head:
        return True
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", pr_head):  # gh output goes no further into git unchecked
        return False
    if not _have(folder, pr_head):
        if pr["state"] != "MERGED":
            return False  # only a merge would let the branch go; an open or closed PR refuses either way
        try:
            lanes.run_git(folder, "fetch", "-q", "origin", f"refs/pull/{pr['number']}/head", timeout=60)
        except lanes.LaneError:
            return False  # best effort: a hung or failed fetch makes no claim
        if not _have(folder, pr_head):
            return False
    return lanes.is_ancestor(folder, head, pr_head)


def shares_work(folder: Path, pr_head: str, head: str, tip: str | None) -> bool | None:
    """For display (`lanes status`): the PR is at this tip, behind it (commits not pushed yet) or
    ahead of it (pushed from elsewhere). None: its head isn't here to compare (not fetched).

    A PR head already in the integration tip only counts at exactly this head: after a merge-commit
    merge, every new branch contains it, and a reused task slug would show the old PR. Likewise a
    branch with no commits of its own can't be "behind" a PR. Local data only: status stays fast.
    """
    if pr_head == head:
        return True
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", pr_head):
        return False
    if not _have(folder, pr_head):
        return None
    if tip and (lanes.is_ancestor(folder, pr_head, tip) or lanes.is_ancestor(folder, head, tip)):
        return False
    return lanes.is_ancestor(folder, pr_head, head) or lanes.is_ancestor(folder, head, pr_head)


def _have(folder: Path, commit: str) -> bool:
    return bool(lanes.git(folder, "rev-parse", "--verify", "-q", f"{commit}^{{commit}}", check=False).strip())


def pull_requests(folder: Path, branch: str, state: str, timeout: int = 30) -> tuple[list[dict], str | None]:
    """(PRs whose head branch is branch, None), or ([], what went wrong). Never raises for gh trouble."""
    gh = shutil.which("gh")
    if gh is None:
        return [], "gh is not installed"
    try:
        result = subprocess.run(
            [
                gh,
                "pr",
                "list",
                "--head",
                branch,
                "--state",
                state,
                "--limit",
                "100",
                "--json",
                "number,state,headRefOid,baseRefName,url",
            ],
            cwd=folder,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return [], f"gh: {error}"
    if result.returncode != 0:
        return [], f"gh pr list failed: {_first_line(result.stderr) or 'no message'}"
    try:
        prs = json.loads(result.stdout or "[]")
    except ValueError:
        return [], "gh pr list printed something that isn't JSON"
    if not isinstance(prs, list) or not all(_valid(pr) for pr in prs):
        return [], "gh pr list returned an unexpected shape"
    return prs, None


def _valid(pr) -> bool:
    return (
        isinstance(pr, dict)
        and isinstance(pr.get("number"), int)
        and isinstance(pr.get("state"), str)
        and isinstance(pr.get("headRefOid"), str)
        and isinstance(pr.get("baseRefName"), str)
    )


def _first_line(text: str) -> str:
    return text.strip().splitlines()[0][:200] if text.strip() else ""

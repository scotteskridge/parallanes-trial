"""PR mode's last step of `kit lanes finish`: push the tested branch and open its pull request (decision 49)."""

import re
import shutil
import subprocess
from pathlib import Path

from kitlib import lane_merged, lanes
from kitlib.lanes import Unfinished


def open_pr(
    top: Path,
    integration: str,
    branch: str,
    tip: str,
    title: str | None,
    body: str | None,
    body_text: str | None = None,
) -> list[str]:
    """body: a file for gh's --body-file; body_text: the body itself (from `--body-file -`), sent on stdin."""
    pushed = lanes.run_git(top, "push", "-q", "-u", "origin", branch)  # never --force (decision 48)
    if pushed.returncode != 0:
        raise Unfinished(f"the tests passed, but git push failed: {pushed.stderr.strip()}")
    lines = [f"Pushed {branch} to origin."]
    remote = lanes.git(top, "remote", "get-url", "origin").strip()
    where = compare_url(remote, integration, branch)
    by_hand = f"open the PR yourself: {where}" if where else f"open the PR yourself ({branch} into {integration})"
    prs, error = lane_merged.pull_requests(top, branch, "open")
    if error:
        raise Unfinished(f"{branch} is pushed, but {error}; {by_hand}")
    if prs:
        return lines + [f"PR #{prs[0]['number']} is already open and now has these commits: {prs[0].get('url', '')}"]
    subjects = lanes.git(top, "log", "--reverse", "--format=%s", f"{tip}..HEAD").splitlines()
    args = [
        shutil.which("gh") or "gh",
        "pr",
        "create",
        "--base",
        integration,
        "--head",
        branch,
        "--title",
        title or subjects[0],
    ]
    if body_text is not None:
        args += ["--body-file", "-"]
    elif body:
        args += ["--body-file", body]
    else:
        args += ["--body", "Commits:\n" + "\n".join(f"- {s}" for s in subjects) + "\n\nOpened by `kit lanes finish`."]
    try:
        # Bytes, not text mode: on Windows a text pipe would turn the body's \n into \r\n.
        created = subprocess.run(
            args, cwd=top, input=(body_text or "").encode("utf-8"), capture_output=True, timeout=60
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise Unfinished(f"{branch} is pushed, but gh pr create couldn't run ({error}); {by_hand}") from None
    out, err = (stream.decode("utf-8", errors="replace").strip() for stream in (created.stdout, created.stderr))
    if created.returncode != 0:
        raise Unfinished(f"{branch} is pushed, but gh pr create failed ({err[:300]}); {by_hand}")
    return lines + [f"Opened {out}"]


def compare_url(remote: str, base: str, head: str) -> str | None:
    """GitHub's "open a pull request" page for head, or None for any other host."""
    match = re.match(
        r"^(?:git@github\.com:|(?:https|ssh)://(?:git@)?github\.com/)([^/]+)/(.+?)(?:\.git)?/?$", remote.strip()
    )
    if not match:
        return None
    return f"https://github.com/{match[1]}/{match[2]}/compare/{base}...{head}?expand=1"

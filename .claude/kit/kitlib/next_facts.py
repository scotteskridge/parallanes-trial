"""`kit next`: the facts the `/next` skill turns into an answer (decision 63).

Where this folder is, every lane, the open plans and the backlog. Read-only. The rules live here,
not in the skill's prose, so they can be tested. A file that can't be read is listed under
Problems, never skipped silently; problems don't fail the command, since `/next` passes them on.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from . import lane_status
from .lanes import branch_of, changes, find_current, run_git, same_path

PLANS_REL = Path("docs") / "plans"
BACKLOG_REL = Path("docs") / "backlog"
PLAN_STATUSES = ("Draft", "Approved", "In progress", "Done")
ITEM_STATUSES = ("now", "next", "later", "idea")
ITEM_SIZES = ("S", "M", "L")
ITEM_KEYS = ("status", "lane", "size", "blocked_by")

# The `Here:` labels the skills' step 0 quotes (tests/test_skills.py builds its checks from these).
HERE_LANE = "lane"
HERE_MAIN = "main checkout"
HERE_OTHER_WORKTREE = "a worktree that isn't a lane"  # `git worktree add`, or a Claude Code --worktree session
HERE_NO_LANES = "not a lane"

STATUS_LINE = re.compile(r"^\*\*Status:\*\*[ \t]*(.*?)[ \t]*$", re.MULTILINE)
LEFT_LINE = re.compile(r"^\*\*Left to do:\*\*[ \t]*(.*?)[ \t]*$", re.MULTILINE)
TITLE_LINE = re.compile(r"^# +(.+?)[ \t]*$", re.MULTILINE)


@dataclass
class Plan:
    path: str
    title: str
    status: str
    left: str | None


@dataclass
class Item:
    slug: str
    title: str
    status: str
    lane: str
    size: str
    blocked_by: str | None = None
    blocker_done: bool = False


def _docs(folder: Path) -> list[Path]:
    """The folder's own Markdown files; README.md and _-prefixed files document the folder (as in changelog.py)."""
    if not folder.is_dir():
        return []
    return sorted(
        path for path in folder.glob("*.md") if path.name.lower() != "readme.md" and not path.name.startswith("_")
    )


def _read(path: Path, rel: str, problems: list) -> str | None:
    """The file's text, or None with a problem: one unreadable file mustn't stop every skill's step 0."""
    try:
        return path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    except UnicodeDecodeError as error:
        problems.append(f"{rel}: can't read (not UTF-8: {error.reason} at byte {error.start})")
    except OSError as error:
        problems.append(f"{rel}: can't read ({error.strerror or error})")
    return None


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _title(text: str, fallback: str) -> str:
    match = TITLE_LINE.search(text)
    return match.group(1) if match else fallback


def plans(root: Path) -> tuple[list, list]:
    """Plans in docs/plans/ (not finished/), Draft first; problems for any without a known status."""
    found, problems = [], []
    for path in _docs(Path(root) / PLANS_REL):
        rel = _rel(root, path)
        text = _read(path, rel, problems)
        if text is None:
            continue
        match = STATUS_LINE.search(text)
        if not match:
            problems.append(f"{rel}: no **Status:** line")
            continue
        status = match.group(1)
        if status not in PLAN_STATUSES:
            problems.append(f"{rel}: status {status!r} is not one of {', '.join(PLAN_STATUSES)}")
            continue
        left = LEFT_LINE.search(text)
        found.append(Plan(rel, _title(text, path.stem), status, left.group(1) if left else None))
    found.sort(key=lambda plan: (PLAN_STATUSES.index(plan.status), plan.path))
    return found, problems


def _header(text: str) -> dict | None:
    """The `---` block at the top as {key: value}, or None when there isn't a closed one."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None
    fields = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return fields
        key, sep, value = line.partition(":")
        if not sep:
            return None
        fields[key.strip()] = value.strip()
    return None


def _item_problem(fields: dict, lane_names: list) -> str | None:
    unknown = [key for key in fields if key not in ITEM_KEYS]
    if unknown:
        return f"unknown header field {unknown[0]!r} (allowed: {', '.join(ITEM_KEYS)})"
    if fields.get("status") not in ITEM_STATUSES:
        return f"status {fields.get('status')!r} is not one of {', '.join(ITEM_STATUSES)}"
    if fields.get("size") not in ITEM_SIZES:
        return f"size {fields.get('size')!r} is not one of {', '.join(ITEM_SIZES)}"
    lanes = ["any", *lane_names]
    if fields.get("lane") not in lanes:
        return f"lane {fields.get('lane')!r} is not one of {', '.join(lanes)}"
    return None


def backlog(root: Path, lane_names: list) -> tuple[list, list]:
    """Backlog items (not done/), sorted now → idea; problems for unreadable files, bad headers and
    blockers that name nothing."""
    folder = Path(root) / BACKLOG_REL
    plans_folder = Path(root) / PLANS_REL
    # A blocker is an item's slug or a plan, by name or path (the backlog README); it is done once the
    # item is in done/ or the plan in finished/. Anything else is probably a typo: say so.
    done = {path.stem for path in (*_docs(folder / "done"), *_docs(plans_folder / "finished"))}
    pending = {path.stem for path in (*_docs(folder), *_docs(plans_folder))}
    found, problems = [], []
    for path in _docs(folder):
        rel = _rel(root, path)
        text = _read(path, rel, problems)
        if text is None:
            continue
        fields = _header(text)
        if fields is None:
            problems.append(f"{rel}: no header (a --- block with status, lane, size)")
            continue
        problem = _item_problem(fields, lane_names)
        if problem:
            problems.append(f"{rel}: {problem}")
            continue
        blocked_by = fields.get("blocked_by") or None
        # `docs/plans/x.md` and `x` name the same plan. Only `.md` is dropped (a slug may be `py3.12`),
        # and `\` splits too, so a Windows path means the same on every OS.
        blocker = blocked_by.replace("\\", "/").rsplit("/", 1)[-1].removesuffix(".md") if blocked_by else None
        if blocker and blocker == path.stem:
            problems.append(f"{rel}: blocked_by names the item itself")
        elif blocker and blocker not in done and blocker not in pending:
            problems.append(f"{rel}: blocked_by {blocked_by!r} names no backlog item or plan")
        found.append(
            Item(
                path.stem,
                _title(text, path.stem),
                fields["status"],
                fields["lane"],
                fields["size"],
                blocked_by,
                blocker in done,
            )
        )
    found.sort(key=lambda item: (ITEM_STATUSES.index(item.status), item.slug))
    return found, problems


def has_commits(folder: Path) -> bool:
    return run_git(folder, "rev-parse", "--verify", "--quiet", "HEAD").returncode == 0


@dataclass
class Facts:
    here: str
    lanes: str | None
    plans: list
    items: list
    problems: list


def facts(start: Path, root: Path, config, offline: bool = False) -> Facts:
    """Everything `/next` needs, read from root: a lane reads its own branch's docs, not the main checkout's."""
    lane, top, main = find_current(Path(start), config)
    folder = top or Path(root)
    # A brand-new project has no HEAD yet: say so rather than failing on rev-parse.
    branch = (branch_of(folder) or "detached") if has_commits(folder) else "no commits yet"
    if lane:
        where = f"{HERE_LANE} {lane.name}"
    elif config.lanes and top and same_path(top, main):
        where = HERE_MAIN
    elif config.lanes and top:
        where = HERE_OTHER_WORKTREE
    else:
        where = HERE_NO_LANES
    changed, untracked = changes(folder)
    state = []
    if changed:
        state.append(f"{changed} changed")
    if untracked:
        state.append(f"{len(untracked)} untracked")
    here = " · ".join([f"Here: {where}", branch, *(state or ["clean"])])
    lanes_text = None
    if config.lanes:
        lanes_text = lane_status.format_status(lane_status.status(Path(start), config, offline))
    found_plans, plan_problems = plans(root)
    items, item_problems = backlog(root, [entry.name for entry in config.lanes])
    return Facts(here, lanes_text, found_plans, items, plan_problems + item_problems)


def format_facts(result: Facts) -> str:
    lines = [result.here]
    if result.lanes is None:
        lines.append("Lanes: none configured")
    else:
        lines.append("Lanes:")
        lines += [f"  {line}" for line in result.lanes.splitlines()]
    lines.append("Plans:" if result.plans else "Plans: none open")
    for plan in result.plans:
        parts = [plan.status, plan.path, plan.title]
        if plan.left and plan.status != "Done":
            parts.append(f"left: {plan.left}")
        lines.append("  " + " · ".join(parts))
    lines.append("Backlog:" if result.items else "Backlog: empty")
    for item in result.items:
        parts = [item.status, item.slug, item.title, f"lane {item.lane}", f"size {item.size}"]
        if item.blocked_by:
            parts.append(f"blocked by {item.blocked_by}" + (" (done)" if item.blocker_done else ""))
        lines.append("  " + " · ".join(parts))
    if result.problems:
        lines.append("Problems:")
        lines += [f"  {problem}" for problem in result.problems]
    return "\n".join(lines)

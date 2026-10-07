"""The kit's command line: `kit check`, `kit hook`, `kit lanes`, `kit next`, `kit settings`, `kit changelog`.

Run from the project root as `sh .claude/kit/kit <command>`, which takes Python from python-path
(decision 99). Exit codes. CLI: 0 clean, 1 findings (for `lanes`: unfinished, something is mid-way), 2 usage
or config error (for `lanes`: refused, nothing changed). Hook mode follows Claude
Code's protocol instead: 0 nothing to report, 2 findings for Claude to fix, 1 a kit error that
is shown but never blocks the edit (decision 9). The protected hook is the exception: it fails
closed, so every error is an exit 2 (decision 33).
"""

from __future__ import annotations  # so this file still loads on an old Python and can say so

import argparse
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from kitlib import changelog, gitfiles, hooks, protected, rules_check, settings
    from kitlib.config import ConfigError, find_root, load
    from kitlib.findings import format_findings
    from kitlib.globs import normalize
except BaseException as error:  # noqa: BLE001 - reported by main(), which picks the exit code
    # A Python older than 3.11 (no tomllib) or a broken install. Left uncaught, this would exit 1,
    # which lets a PreToolUse call through: the protected hook must fail closed here too.
    IMPORT_ERROR = error
else:
    IMPORT_ERROR = None

OK, FINDINGS, USAGE = 0, 1, 2
HOOK_ERROR, HOOK_BLOCK = 1, 2  # as in kitlib/hooks.py, which can't be imported when IMPORT_ERROR is set

CHECKS = ("rules", "protected", "settings", "lanes")


class UsageError(Exception):
    pass


def main(argv=None) -> int:
    # Findings can contain any text; a Windows console or pipe would otherwise crash on it.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    argv = sys.argv[1:] if argv is None else argv
    if IMPORT_ERROR is not None:
        return import_failure(argv, IMPORT_ERROR)
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as stop:
        # In hook mode, exit 2 would send usage text to Claude after every edit: report it
        # as a non-blocking hook error instead (a typo in settings.json, decision 9).
        # PreToolUse is the protected guard's event: there, fail closed instead (decision 33).
        if argv[:1] == ["hook"] and stop.code == USAGE:
            return HOOK_BLOCK if _hook_event() == "PreToolUse" else HOOK_ERROR
        raise
    if not hasattr(args, "run"):
        parser.print_help()
        return USAGE
    return args.run(args)


def import_failure(argv, error: BaseException) -> int:
    print(
        f"kit: can't load the kit ({type(error).__name__}: {error}). It needs Python 3.11 or newer; "
        f"this is {sys.version.split()[0]}. Tell the user.",
        file=sys.stderr,
    )
    if argv[:1] != ["hook"]:
        return USAGE
    if argv[1:2] in (["protected"], ["reviewer-bash"]):
        return HOOK_BLOCK
    # The other hooks fail open (decisions 9, 40, 41); an unknown name in PreToolUse may be the guard.
    if argv[1:2] not in (["rules-check"], ["lane-router"], ["ownership"]) and _hook_event() == "PreToolUse":
        return HOOK_BLOCK
    return HOOK_ERROR


def _hook_event() -> str | None:
    """The hook_event_name Claude Code sent on stdin, or None if it can't be read."""
    try:
        payload = json.loads(sys.stdin.read())
    except (ValueError, OSError):
        return None
    return payload.get("hook_event_name") if isinstance(payload, dict) else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kit", description="claude-code-lanes-starter project tools.")
    commands = parser.add_subparsers(title="commands")

    check = commands.add_parser("check", help="run the project's checks on files")
    check.add_argument("name", choices=[*CHECKS, "all"], help="which check to run")
    source = check.add_mutually_exclusive_group()
    source.add_argument("--staged", action="store_true", help="check what is staged for commit")
    source.add_argument("--diff", metavar="BASE", help="check files changed since BASE (e.g. origin/main)")
    check.add_argument("files", nargs="*", help="files to check (default: every tracked file)")
    check.add_argument("--lane", help="the lane whose change this is (default: from the <lane>/<task> branch)")
    check.set_defaults(run=run_check)

    hook = commands.add_parser("hook", help="Claude Code hook entry points (JSON on stdin)")
    hook.add_argument("name", choices=["rules-check", "protected", "lane-router", "ownership", "reviewer-bash"])
    hook.set_defaults(run=run_hook)

    lane = commands.add_parser("lanes", help="parallel lanes: one git worktree per lane")
    lane_commands = lane.add_subparsers(title="lanes commands", dest="lanes_command", required=True)
    create = lane_commands.add_parser("create", help="create a worktree per lane (all lanes when none are named)")
    create.add_argument("names", nargs="*", metavar="lane")
    create.add_argument("--dry-run", action="store_true", help="print what would be created; change nothing")
    status = lane_commands.add_parser("status", help="every lane: folder, branch, ahead/behind, changes, PR")
    status.add_argument("--offline", action="store_true", help="don't ask gh for pull request state")
    remove = lane_commands.add_parser("remove", help="remove a lane's worktree (refuses uncommitted changes)")
    remove.add_argument("name", metavar="lane")
    remove.add_argument(
        "--force", action="store_true", help="also delete ignored files that hold work (.env, local settings)"
    )
    start = lane_commands.add_parser("start", help="new task branch <lane>/<task>, once the previous one is merged")
    start.add_argument("task", help="short name: lowercase letters, digits, hyphens")
    start.add_argument("--abandon", action="store_true", help="drop an unmerged previous task branch on purpose")
    lane_commands.add_parser("sync", help="bring the integration branch in (rebase if unpushed, merge if pushed)")
    finish = lane_commands.add_parser(
        "finish", help="sync, run the tests, then open a PR (or fast-forward in local mode)"
    )
    finish.add_argument("--title", help="PR title (default: the first commit's subject)")
    finish.add_argument(
        "--body-file", help="file holding the PR body, or - to read it from stdin (default: the commit list)"
    )
    lane.set_defaults(run=run_lanes, names=[], dry_run=False, offline=False, force=False)

    upcoming = commands.add_parser("next", help="what's next: this folder, lanes, open plans, backlog (read-only)")
    upcoming.add_argument("--offline", action="store_true", help="don't ask gh for pull request state")
    upcoming.set_defaults(run=run_next)

    perms = commands.add_parser("settings", help="permission rules in .claude/settings.json")
    perms_commands = perms.add_subparsers(title="settings commands")
    sync = perms_commands.add_parser("sync", help="write the deny and ask rules [protected] needs")
    sync.add_argument("--dry-run", action="store_true", help="print the changes; write nothing")
    sync.set_defaults(run=run_settings_sync)

    log = commands.add_parser("changelog", help="changelog fragments")
    log_commands = log.add_subparsers(title="changelog commands")
    build = log_commands.add_parser("build", help="compile docs/changelog.d/ into docs/CHANGELOG.md")
    build.add_argument("--version", required=True, help="release version, e.g. 1.2.0")
    build.add_argument("--date", default=datetime.date.today().isoformat(), help="release date (default: today)")
    build.add_argument("--dry-run", action="store_true", help="print the new section; change nothing")
    build.set_defaults(run=run_changelog_build)
    return parser


# ---- kit check -------------------------------------------------------------------------------


def run_check(args) -> int:
    names = list(CHECKS) if args.name == "all" else [args.name]
    if args.lane and "lanes" not in names:
        print(f"kit: --lane is for `check lanes` (or `all`), not `check {args.name}`", file=sys.stderr)
        return USAGE
    try:
        root = find_root(Path.cwd())
        config = load(root)
        findings = []
        if "rules" in names:
            findings += rules_check.check(config, collect_files(root, config, args))
        if "protected" in names:
            findings += check_protected(root, config, args)
        if "settings" in names:
            findings += settings.check(root, config)  # about the project, not the files given
        if "lanes" in names:
            findings += check_lanes(root, config, args)
    except (ConfigError, gitfiles.GitError, UsageError, settings.SettingsError) as error:
        print(f"kit: {error}", file=sys.stderr)
        return USAGE
    if findings:
        print(format_findings(findings))
        print(f"\n{len(findings)} finding(s). Rules live in .claude/kit.toml.", file=sys.stderr)
        return FINDINGS
    return OK


def touched_paths(root: Path, args) -> list[str] | None:
    """Every path the change adds, changes or deletes; None for a whole-project run, which has no change."""
    if args.staged:
        return gitfiles.touched_staged(root)
    if args.diff:
        return gitfiles.touched_since(root, args.diff)
    if args.files:
        return explicit_paths(root, args.files)
    return None


def check_protected(root: Path, config, args) -> list:
    paths = touched_paths(root, args)
    findings = protected.check(config, paths) if paths else []
    return allowed(findings, protected.allowed_by_human(), "protected path", protected.ALLOW_VARIABLE)


def check_lanes(root: Path, config, args) -> list:
    """A lane's change outside its own and the shared paths (decision 96). Other branches aren't judged."""
    # Imported here, as `kit lanes` does: a fault in lane code must not take the protected hook down.
    from kitlib import lane_boundary

    if not (args.staged or args.diff or args.files):
        return []  # a whole-project run has no change to judge
    if not gitfiles.is_repo(root):
        return []  # named files in a folder that isn't a git repo: no branch, so no lane
    branch = args.lane + "/" if args.lane else gitfiles.current_branch(root) or lane_boundary.ci_branch()
    if not branch or "/" not in branch:
        return []  # can't be a lane's: the base's kit.toml isn't even read (review round 2)
    head = "HEAD" if gitfiles.has_ref(root, "HEAD") else None  # None before a new project's first commit
    base = gitfiles.merge_base(root, args.diff) if args.diff else head
    # The lanes the change started from; a prefix that names no lane there isn't lane work.
    found = lane_boundary.lanes_before(root, config, base, branch.split("/", 1)[0])
    if found is None:
        if args.lane:
            raise UsageError(f"--lane {args.lane}: no such lane in .claude/kit.toml")
        return []
    judge, lane = found
    if args.staged and gitfiles.has_ref(root, "MERGE_HEAD"):
        paths = gitfiles.touched_by_merge_commit(root)  # not what the merged branch brought in
    else:
        paths = touched_paths(root, args)
    findings = lane_boundary.check(judge, lane, paths)
    findings = allowed(findings, lane_boundary.allowed_by_human(), "cross-lane", lane_boundary.ALLOW_VARIABLE)
    if findings:
        print(lane_boundary.ADVICE, file=sys.stderr)
    return findings


def allowed(findings: list, by_human: bool, what: str, variable: str) -> list:
    if findings and by_human:  # said out loud, so an override never passes silently
        print(f"kit: {len(findings)} {what} change(s) allowed by {variable}=1.", file=sys.stderr)
        return []
    return findings


def explicit_paths(root: Path, names) -> list[str]:
    # `vendor\a.py` means the same file on every platform, as in kit.toml globs.
    paths = [relative_to_root(root, Path(normalize(name))) for name in names]
    for name, path in zip(names, paths, strict=True):
        if not (root / path).is_file():
            raise UsageError(f"{name}: not a file")  # a typo must not pass as "clean"
    return paths


def collect_files(root: Path, config, args):
    """(project-relative path, text) for each file some rule covers; binary files are skipped.

    Paths are filtered before anything is read, so large repos only pay for covered files.
    """
    if args.staged:
        for path in gitfiles.staged(root):
            if not rules_check.covered(config, path):
                continue
            text = gitfiles.read_staged(root, path)
            if text is not None:
                yield path, text
        return
    if args.diff:
        paths = gitfiles.changed_since(root, args.diff)
    elif args.files:
        paths = explicit_paths(root, args.files)
    else:
        paths = gitfiles.tracked(root)
    for path in paths:
        if not rules_check.covered(config, path):
            continue
        text = gitfiles.read_worktree(root, path)
        if text is not None:
            yield path, text


def relative_to_root(root: Path, path: Path) -> str:
    absolute = (Path.cwd() / path).resolve()
    try:
        return absolute.relative_to(root.resolve()).as_posix()
    except ValueError:
        raise UsageError(f"{path} is outside the project ({root})") from None


# ---- kit hook ----------------------------------------------------------------------------------


def run_hook(args) -> int:
    return hooks.run(args.name)


# ---- kit lanes ---------------------------------------------------------------------------------


def run_lanes(args) -> int:
    try:
        # Imported here, not at the top, so a fault in the lane code can't take the protected guard down.
        from kitlib import lane_cli
    except Exception as error:  # noqa: BLE001 - say what broke instead of a traceback
        print(f"kit: the lane code failed to load ({type(error).__name__}: {error}). Tell the user.", file=sys.stderr)
        return USAGE
    return lane_cli.run(args)


# ---- kit next ----------------------------------------------------------------------------------


def run_next(args) -> int:
    try:
        # Imported here, as for `kit lanes`: it uses the lane code, which mustn't take the guard down.
        from kitlib import lanes, next_facts
    except Exception as error:  # noqa: BLE001 - say what broke instead of a traceback
        print(f"kit: the lane code failed to load ({type(error).__name__}: {error}). Tell the user.", file=sys.stderr)
        return USAGE
    here = Path.cwd()
    try:
        root = find_root(here)
        result = next_facts.facts(here, root, load(root), args.offline)
    except (ConfigError, lanes.LaneError) as error:
        print(f"kit: {error}", file=sys.stderr)
        return USAGE
    print(next_facts.format_facts(result))
    return OK


# ---- kit settings ------------------------------------------------------------------------------


def run_settings_sync(args) -> int:
    try:
        root = find_root(Path.cwd())
        plan = settings.plan_sync(root, load(root))
    except (ConfigError, settings.SettingsError) as error:
        print(f"kit: {error}", file=sys.stderr)
        return USAGE
    if not plan.changed:
        print(f"{settings.SETTINGS_REL.as_posix()} is up to date.")
        return OK
    if args.dry_run:
        print(f"Would change:\n{settings.describe(plan)}")
        return OK
    settings.apply_sync(root, plan)
    print(f"Changed:\n{settings.describe(plan)}")
    return OK


# ---- kit changelog -------------------------------------------------------------------------------


def run_changelog_build(args) -> int:
    root = find_root(Path.cwd())
    try:
        release = changelog.build(root, args.version, args.date)
    except changelog.ChangelogError as error:
        print(f"kit: {error}", file=sys.stderr)
        return USAGE
    if args.dry_run:
        print(release.section, end="")
        return OK
    changelog.apply(root, release)
    print(f"Released {args.version}: {len(release.fragments)} fragment(s) compiled into docs/CHANGELOG.md.")
    return OK


if __name__ == "__main__":
    sys.exit(main())

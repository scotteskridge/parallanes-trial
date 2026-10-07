"""`kit hook <name>`: Claude Code hook entry points, reading the hook's JSON on stdin.

Each hook has its own failure policy, because each guards something different:
- rules-check (PostToolUse) fails open: a kit problem is shown (exit 1) and never blocks (decision 9).
- protected (PreToolUse) fails closed: in PreToolUse only exit 2 blocks, so every error exits 2 (33).
- lane-router (SessionStart) can't block; on failure it tells the agent the check failed (40).
- ownership (PreToolUse) fails open: it reduces conflicts, it isn't security (41).
- reviewer-bash (PreToolUse, in the reviewer agent's frontmatter) fails closed: it keeps a promise
  that the reviewer is read-only (57).
"""

import json
import os
import sys
from pathlib import Path

from . import gitfiles, protected, rules_check
from .config import ConfigError, ConfigMissing, find_root, load
from .findings import format_findings

HOOK_OK, HOOK_ERROR, HOOK_BLOCK = 0, 1, 2


def run(name: str) -> int:
    if name == "protected":
        return run_protected()
    if name == "lane-router":
        return run_lane_router()
    if name == "reviewer-bash":
        return run_reviewer_bash()
    try:
        payload = json.loads(sys.stdin.read())
        if not isinstance(payload, dict):
            raise ValueError("hook input is not a JSON object")
        return ownership(payload) if name == "ownership" else rules_check_hook(payload)
    except Exception as error:  # noqa: BLE001 - the hook must never crash with a traceback
        print(f"kit hook {name}: {type(error).__name__}: {error}", file=sys.stderr)
        return HOOK_ERROR


def run_protected() -> int:
    """PreToolUse backstop. Fails closed: in PreToolUse only exit 2 blocks, so every error exits 2."""
    try:
        payload = json.loads(sys.stdin.read())
        if not isinstance(payload, dict):
            raise ValueError("hook input is not a JSON object")
        root = find_root(Path(payload.get("cwd") or os.getcwd()))
        try:
            config = load(root)
        except ConfigMissing:
            return HOOK_OK  # the kit isn't set up here: nothing to enforce (decision 33)
        reason = protected.check_tool_call(payload, root, config)
    except ConfigError as error:
        print(
            f"Blocked: the kit's protected-paths guard can't read its config: {error}\n"
            "Fix .claude/kit.toml (or ask the user to) before running commands or editing files.",
            file=sys.stderr,
        )
        return HOOK_BLOCK
    except Exception as error:  # noqa: BLE001 - fail closed, without a traceback
        print(
            f"Blocked: the kit's protected-paths guard failed ({type(error).__name__}: {error}).\n"
            "Tell the user; this is a bug in the kit or its install, not something to work around.",
            file=sys.stderr,
        )
        return HOOK_BLOCK
    if reason is None:
        return HOOK_OK
    print(
        f"Blocked by the kit's protected-paths guard: {reason}.\n"
        "Don't look for another way to do this. If it is needed, ask the user to do it themselves "
        "or to change .claude/kit.toml.",
        file=sys.stderr,
    )
    return HOOK_BLOCK


def run_reviewer_bash() -> int:
    """PreToolUse for the reviewer agent. Fails closed, like the protected guard."""
    try:
        payload = json.loads(sys.stdin.read())
        if not isinstance(payload, dict):
            raise ValueError("hook input is not a JSON object")
        if not payload.get("tool_name"):
            raise ValueError("hook input has no tool_name")
        if payload["tool_name"] != "Bash":
            return HOOK_OK  # the agent's matcher is Bash; other tools aren't this guard's business
        command = (payload.get("tool_input") or {}).get("command")
        if not isinstance(command, str):
            raise ValueError("Bash call without a command")
        from . import reviewer_hook

        reason = reviewer_hook.reason(command)
    except Exception as error:  # noqa: BLE001 - fail closed, without a traceback
        print(f"Blocked: the reviewer's read-only guard failed ({type(error).__name__}: {error}).", file=sys.stderr)
        return HOOK_BLOCK
    if reason is None:
        return HOOK_OK
    print(
        f"Blocked: the reviewer is read-only. {reason}.\n"
        f"Allowed: {reviewer_hook.ALLOWED_TEXT}; every command in a chain must be one of these "
        "(or `cd <folder>`); no redirects or substitutions. Use Read, Grep and Glob for files.",
        file=sys.stderr,
    )
    return HOOK_BLOCK


def rules_check_hook(payload: dict) -> int:
    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not file_path:
        return HOOK_OK
    cwd = Path(payload.get("cwd") or os.getcwd())
    root = find_root(cwd)
    try:
        config = load(root)
    except ConfigMissing:
        return HOOK_OK  # the kit isn't set up here: nothing to enforce
    except ConfigError as error:
        print(f"kit: rules not checked: {error}", file=sys.stderr)
        return HOOK_ERROR

    try:
        rel = (cwd / file_path).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return HOOK_OK  # outside the project
    if not rules_check.covered(config, rel):
        return HOOK_OK
    text = gitfiles.read_worktree(root, rel)
    if text is None:
        return HOOK_OK  # deleted or binary
    findings = rules_check.check(config, [(rel, text)])
    if not findings:
        return HOOK_OK
    print(
        f"Rule violations in {rel} (rules from .claude/kit.toml):\n{format_findings(findings)}\n"
        "Fix the file. If a rule looks wrong, tell the user instead of working around it.",
        file=sys.stderr,
    )
    return HOOK_BLOCK


def run_lane_router() -> int:
    """SessionStart: plain stdout becomes the agent's context. Always exit 0 (decision 40)."""
    try:
        payload = json.loads(sys.stdin.read())
        if not isinstance(payload, dict):
            raise ValueError("hook input is not a JSON object")
        from . import lane_hooks  # here, so a fault in the lane code can't break the other hooks

        text = lane_hooks.router_text(Path(payload.get("cwd") or os.getcwd()))
    except Exception as error:  # noqa: BLE001 - never a traceback; say the check failed instead
        text = (
            f"Lane check failed ({type(error).__name__}: {error}). Lane, branch and drift are unknown: "
            "run `kit lanes status` before starting work, and tell the user if it fails too."
        )
    if text:
        print(text)
    return HOOK_OK


def ownership(payload: dict) -> int:
    """PreToolUse on file tools: an out-of-lane edit asks the human (decision 41)."""
    from . import lane_hooks  # here, so a fault in the lane code can't break the other hooks

    reason = lane_hooks.ownership_reason(payload)
    if reason is None:
        return HOOK_OK
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "ask",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    return HOOK_OK

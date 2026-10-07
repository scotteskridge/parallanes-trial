# Protected paths and commands

What the kit does to keep agents away from files and commands you list in `[protected]` in
`.claude/kit.toml`, and, just as important, what it does **not** stop. Short version: it reliably
stops honest mistakes by Claude Code. It is not a security boundary. The boundary is the server:
CI, required reviews and branch protection.

## The layers

| Layer | Where | Stops | Doesn't stop |
| --- | --- | --- | --- |
| Deny rules (main protection) | `.claude/settings.json`, written by `sh .claude/kit/kit settings sync` | Claude's Edit/Write tools on protected paths; reads and edits of secrets; the shell file commands Claude Code recognizes (`sed`, `tee`, redirections); protected commands in the form written in `kit.toml`, also inside `&&`, `;`, pipes and subshells | Commands with options in between (`git -C . push --force`, `git push origin main --force`); writes by any program or script |
| Hook (backstop) | `sh .claude/kit/kit hook protected`, before every tool call | Protected commands with reordered flags, `git -C`, wrappers (`env`, `sudo`, `timeout`), flag clusters (`-xdf`); edits to protected paths even if `settings.json` drifted; the targets of common file commands (`rm`, `mv`, `cp`, `git rm`, `git mv`, `git restore`, `Set-Content`, `Remove-Item`, `Out-File`, redirections); the agent switching the checks off (`--no-verify`, `KIT_ALLOW_PROTECTED`, `core.hooksPath`) | The misses listed below |
| Pre-commit | `.githooks/pre-commit` → `sh .claude/kit/kit check all --staged` | A commit that changes a protected path or adds a secret file, from anyone; `kit.toml` and `settings.json` drifting apart | `git commit --no-verify` by a human; machines without the hook enabled |
| CI | `sh .claude/kit/kit check all --diff origin/main` | The same, for every pull request | Nothing it checks can be skipped locally, which is why it is the gate |

Where the hook and the deny rules cover the same thing (Claude's file tools, the shell file
commands Claude Code recognizes), the hook is a **drift guard**: it still protects if
`settings.json` is out of date, and it covers PowerShell cmdlets, which Claude Code's docs don't
say the deny rules do.

The command checks follow `[protected].commands`: `--no-verify` is caught because it is in the
default list, and a list you write replaces the defaults. Setting `KIT_ALLOW_PROTECTED` (or
`KIT_ALLOW_CROSS_LANE`, the lane-boundary override) is caught where a command does it
(`KIT_ALLOW_PROTECTED=1 git commit`, `export`, `$env:`); quoting it in a commit message, PR text
or search is fine. One false alarm remains: a heredoc line that starts with
the assignment reads like a command. Write such text to a file and pass the file instead.

The hook **fails closed**: if `kit.toml` can't be read, the Python is too old for the kit, or the
hook itself breaks, Claude's tool calls are blocked with a message saying what to fix. A guard that
silently switches off is worse than a noisy one. The one thing it can't catch is its own absence:
if the Python interpreter recorded at install is gone, the hook never starts, and Claude Code lets
calls through (the deny rules still apply).

## The kit's own configuration

Whoever can edit `.claude/settings.json`, `.claude/kit.toml`, `.claude/kit/` or `.githooks/` can
switch all of this off. So edits to them get an **ask** rule: Claude must get your approval each
time. Claude Code never auto-approves an ask rule, in any mode, `acceptEdits` and
`bypassPermissions` included; in a non-interactive run (`claude -p`), where nobody can answer, the
edit is refused. Ask rules are written for Claude's file tools, and Claude Code doesn't say they
cover `rm` or PowerShell cmdlets, so in `bypassPermissions` mode the hook also blocks shell
commands that write to or delete these files. `guard_kit = false` in `[protected]` turns both off.

## Secrets

`[protected].secrets` lists files Claude may neither read nor edit. The default is `.env` and every
`.env.*`, except `.env.example`, which projects commit: a name starting with `!` is an exemption.
Exemptions follow Claude Code's rules, so `sh .claude/kit/kit` refuses one that would do nothing: it
must be a bare file name (no folder, no trailing `/`), listed after a bare file name it matches
(a wildcard exemption needs only some bare name before it), and only in `secrets`; a name listed
again after it denies the file again. In `settings.json` an exemption also cancels your own
bare-name deny rules listed before it; to deny such a file anyway, add your rule after the
exemption. `sh .claude/kit/kit settings sync` keeps the kit's rules in this order.

## Known misses

Each of these gets past the deny rules and the hook. They are listed so nobody mistakes the kit for
more than it is:

- Shell commands that change the kit's own configuration in modes that run them without asking
  you (`acceptEdits`, `auto`, `dontAsk`, or any mode with an allow rule for the command), and in
  any mode a copy into a folder that replaces a file there (`cp settings.json .claude/`). The ask
  rules cover Claude's file tools; the hook covers shell commands in `bypassPermissions` only.
- Any script or program that opens files itself (`python fix.py`, `node build.js`).
- Commands inside strings: `bash -c "git push --force"`, `pwsh -Command "..."`.
- Git aliases (`git pf`), force pushes by refspec (`git push origin +main`), abbreviated options,
  `git checkout <commit> <path>` without `--`, and paths given to `git -C <dir>` (judged from the
  session's folder, not `<dir>`).
- Write targets of commands the hook doesn't know, paths passed through a pipe
  (`Get-ChildItem vendor | Remove-Item`), and names given separately from the folder
  (`New-Item -Path . -Name .env`).
- Deleting a folder that holds protected files is caught for patterns with a folder in them
  (`rm -rf src` or `rm -rf src/*` when `src/vendor/**` is protected), not for bare file-name
  patterns (`rm -rf src` when `*.lock` is protected).
- Edits to a project from a session whose working folder is outside it (for example the main
  session editing a sibling lane's worktree): the hook and the deny rules both judge paths against
  the session's own project.
- On Windows, whether Claude Code's deny rules cover PowerShell cmdlets isn't documented; the hook
  covers the common ones, best effort.

## A real boundary

- **Sandbox.** Claude Code's sandbox restricts what shell commands and the programs they start can
  write, at the operating-system level. It runs on macOS, Linux and WSL2. It does **not** run on
  native Windows, which is why the deny rules and the hook both exist. On Windows, run Claude Code
  inside WSL2 (then turn the sandbox on), a container (a dev container, for example) or a virtual
  machine to get a real boundary.
- **The server.** Protect `main`: require pull requests and passing CI, and
  refuse force pushes. Add a `CODEOWNERS` entry for each protected path so changes there need an
  owner's review.

## Changing a protected path on purpose

- **You, at a terminal:** `KIT_ALLOW_PROTECTED=1 git commit ...` lets the commit through (bash; in
  PowerShell set `$env:KIT_ALLOW_PROTECTED = "1"` first). The pre-commit output says it was allowed.
  Agents are blocked from setting it.
- **An agent:** it can't, by design. Ask it to explain the change, then make it yourself or remove
  the path from `[protected]` (and run `sh .claude/kit/kit settings sync`).

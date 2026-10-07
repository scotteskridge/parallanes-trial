# Parallel lanes: several agents at once

Lanes let several agent sessions work on worklanes-trial at the same time without stepping on each
other. This guide is for the people running them; the agents get their part from a hook at session
start.

## Concepts

- **Lane:** a long-lived workspace with its own folder (a *git worktree*: a second checkout of the
  same repository), a scope, the paths it owns, and its own resources (ports, editor instances).
  Lanes are defined in `.claude/kit.toml`.
- **Task branch:** each task gets a fresh branch named `<lane>/<task>`, created from the latest
  `main` and deleted once merged. Branches never live longer than one task, so they
  can't drift.
- **Integration branch:** `main`, where finished work lands, through a pull
  request (PR mode, the default) or a local fast-forward (local mode, for solo or offline work).

## Setting up

```
sh .claude/kit/kit lanes create          # one worktree per lane in .claude/kit.toml
sh .claude/kit/kit lanes status          # every lane: folder, branch, ahead/behind, changed, untracked, unpushed, PR
```

Then start one Claude Code session in each lane's folder. Two to four lanes is usually the limit of
what one person can review.

`lanes create` makes each lane folder from the latest `main` (`origin/main` in PR
mode, the local branch in local mode; it never fetches), with no branch checked out until a task
starts. If one lane fails, the others are still created; fix the problem and run it again. It
copies the files listed in `.worktreeinclude` that are gitignored (local settings, `.env`); a rerun
copies only missing ones and never overwrites, so after changing `.env` in the main checkout, update
the lanes' copies yourself.

Lanes need git 2.36 or newer and a normal checkout: in a repository set up with `git init
--separate-git-dir`, git can't trace a lane back to its main checkout, so `lanes create` refuses. It refuses when lane folders
inside the project aren't gitignored, and tells you the line to add to `.gitignore`.

**What each session is told.** When a session starts (or resumes, clears or compacts) in a lane folder, a hook
tells the agent its lane, scope, owned paths, resources and branch, and warns about drift: no task
branch yet, a branch from another lane, already merged, behind `main`, changed
or untracked files, or `.claude/kit.toml` changed on `main`. It uses local git
data only, so "behind" is as of your last fetch.

**Lane folders inside the project.** By default lanes live in `.claude/worktrees/<lane>/`. Claude
Code loads every `CLAUDE.md` from the session's folder up to the drive root, so a lane would also
read the main checkout's copy. `lanes create` prevents that: it lists the main checkout's `CLAUDE.md`,
`.claude/CLAUDE.md` and `AGENTS.md` under `claudeMdExcludes` in the lane's own
`.claude/settings.local.json`, which is gitignored and specific to your machine. The entries are
absolute paths; if your project path contains `[`, `{` or `*`, check with `/memory` in a lane
session that only the lane's own `CLAUDE.md` is loaded. Tools that walk the project folder must skip lane folders too: set pytest's
`norecursedirs` (it already skips folders starting with `.`), and your linters' and editor's
exclude lists. To keep lanes outside the project instead, set `worktree_root = "../{project}-lanes"`
in `kit.toml` before creating them.

**Memory is shared.** Claude Code's auto memory belongs to the repository, not the folder: every
lane reads and writes the same memory as the main checkout. Keep lane-specific notes in the lane's
plan or task files instead.

**The main checkout.** Keep it on a commit that has the kit (`.claude/kit.toml`): the lanes find
it by that file, so while it is on an older commit (say, during `git bisect`) the lane commands
stop with an error and the lane hooks stand down. In PR mode it can stay on `main`. In local mode, lanes
fast-forward `main` directly, which git refuses while any folder has it checked
out; `lanes status` warns and gives the command (`git switch --detach main`). The
kit never moves the main checkout itself.

## The task cycle

```
sh .claude/kit/kit lanes start <task>    # new branch <lane>/<task> from the latest integration branch
  ... /plan-feature or /implement, then /wrap-up ...
sh .claude/kit/kit lanes finish          # tests → push and open a PR (or fast-forward in local mode)
```

`/plan-feature`, `/implement` and `/wrap-up` run these for you; the commands work the same by hand.
They run only inside a lane folder, and refuse while tracked files have uncommitted changes.
Untracked files don't block; each command lists them. The tests can see them, but they won't land:
commit any that belong to the task, and put generated ones (test reports, build output) in `.gitignore`.

- **`start <task>`** first proves the lane's previous task branch was merged: its commits are in
  `main`, or (PR mode) GitHub has a merged PR whose head is exactly that branch's
  last commit, which covers squash merges. An open or closed PR, commits added after the PR, or no
  `gh` to ask: it refuses and says why. `--abandon` drops the branch on purpose and prints its
  commit, so it can be recovered. The task name is lowercase letters, digits and hyphens.
- **`sync`** brings in new `main` commits: a rebase while the branch was never pushed,
  a merge after (nothing under review is rewritten; the kit never force-pushes). On a conflict it
  stops with the rebase or merge in progress and names the files: resolve them, `git add`, then
  `git rebase --continue` (or `git merge --continue`), or `--abort` to back out.
- **`finish`** syncs, runs `test_command` on the result (there is no way to skip it), then in PR mode
  pushes and opens a PR (`--title`, `--body-file`; a re-run only pushes to the open PR), or in local
  mode fast-forwards `main`, deletes the task branch and leaves the lane between tasks.
  If another lane landed first, local mode syncs, re-tests and tries once more. Failing tests, or a
  test command that changes the branch, stop it before anything is pushed or merged.

Exit codes: 0 done; 2 refused, nothing changed (the message says why); 1 unfinished, something is
mid-way (tests failed, a conflict waits, or the push or PR failed): read the message before going on.
"Pushed?" means `origin/<the same branch name>` exists; a branch pushed under another name, or to
another remote, counts as unpushed, and `sync` would rebase it.

## Rules that keep lanes apart

- **One session per lane folder.** Two sessions in one folder share files and mix their edits.
- **Stay in your lane's paths.** An edit outside them asks you first (`ownership = "ask"` in
  `kit.toml`). Shared paths (plans, backlog, changelog fragments) are open to every lane. This
  covers Claude Code's file tools only, not shell commands, and may not prompt in
  `bypassPermissions` mode. Edits from a lane to the main checkout or to another lane's folder
  ask too. When the work lands, the boundary is enforced: `lanes finish`, the pre-commit hook and
  CI (`sh .claude/kit/kit check lanes`) refuse a lane's change to a file it doesn't own (see the next
  rule) outside the shared paths, and any change to `.claude/kit.toml`. To land one on purpose, a person uses a branch that isn't
  a lane's; `KIT_ALLOW_CROSS_LANE=1` gets a local commit or a local-mode finish through, but CI has
  no override, so a pull request needs the non-lane branch. An agent stops and asks instead.
- **When two lanes' patterns match one file, the more specific one owns it.** A lane owning
  `src/**` doesn't own `src/core/a.py` if another lane owns `src/core/**`: its edits there ask, and
  the boundary check refuses them. More specific means more literal folder and file names, then a
  pattern rooted at the project top over one matching at any depth (`conftest.py`, `build/`),
  then more literal characters (`*.md` over `**`), then fewer wildcards. Order in `kit.toml`
  doesn't matter. The same pattern in two lanes doesn't load; two patterns equally specific for a
  file leave it with no owner until you make one more specific. `lanes create` and `lanes status` list both cases. A folder both lanes should change
  belongs in `shared_paths`.
- **No shared append-only files.** Changelog entries are fragments; backlog items are one file
  each. That removes the most common merge conflict.
- **Don't run two tasks at once that edit the same file.** If two lanes need it, do one after the
  other.

## When a merge conflicts

- Code: resolve it in the task branch, run the tests, and say in the PR what you chose.
- Generated files: take either side, then regenerate.
- Binary or editor-owned files (images, scenes, lock files): stop and ask; don't hand-merge.

## Removing a lane

`sh .claude/kit/kit lanes remove <lane>` deletes its worktree. It refuses if there are uncommitted changes, or
ignored files that may hold work (a changed `.env`, local settings, build output; not caches such as
`__pycache__` or `node_modules`); it lists them, and `--force` deletes them anyway. The lane's entry stays in `kit.toml` until you delete it.

## Lanes or agent teams?

Lanes are for **lasting, human-supervised workstreams**: each has an owner, a scope and a review
step. Claude Code's agent teams are for **fanning one task out** to several helpers that report
back. A lane session can still use agent teams or subagents inside its own task.

---
name: plan-feature
description: "Turn a request or a backlog item into an approved plan on a fresh task branch: understand the code, ask the owner what it can't settle, write the plan file, then stop for approval. Use for /plan-feature, before building anything that touches several files or whose approach is unclear."
model: opus
disable-model-invocation: true
argument-hint: "[what to build, or a backlog item's slug]"
allowed-tools: Bash(sh .claude/kit/kit next) Bash(sh .claude/kit/kit next *) Bash(git status *) Read Grep Glob
---
Plan this: $ARGUMENTS

You write a plan and stop. **Build nothing**: building is `/implement`, in a fresh session, after
the owner approves.

## 0. Lane check
Run `sh .claude/kit/kit next --offline`. Its first line says where this folder is:
- `Here: lane <name>`: the plan's task branch comes from `lanes start` (step 3). Keep the plan
  inside this lane's scope and owned paths (the session-start hook listed them).
- `Here: main checkout` (or `a worktree that isn't a lane`): the project has lanes but this isn't
  one. Stop and say which lane the work belongs in, and that it is planned from that lane's folder.
- `Here: not a lane`: the project has no lanes; the task branch comes from git (step 3).
Stop if this folder has changed files (`N changed`; untracked files alone don't count), or a task
branch with work that isn't merged: finish that first (`/wrap-up`). Read `integration_branch` and
`merge_mode` from `.claude/kit.toml` (defaults `main` and `pr`).

## 1. Understand
- If the argument is a backlog slug, read `docs/backlog/<slug>.md`; it is the request.
- Search before you design: find the code, tests and patterns this touches (a subagent for broad
  searches). Read the relevant sections of `docs/design/` by heading, and recent entries of
  `docs/design/decisions-log.md`, so you don't re-argue a settled question.

## 2. Ask
Ask the owner only what the code and docs can't answer: what *done* looks like, constraints, and
choices between real alternatives. At most five questions, each with your recommendation. If the
work is bigger than one plan (more than about eight steps), propose a split and plan the first part.

## 3. Branch
Pick a short task name: lowercase letters, digits and hyphens (e.g. `export-csv`).
- In a lane: `sh .claude/kit/kit lanes start <task>`. If it refuses, show its reason and stop.
  Never add `--abandon` unless the owner says to drop the unmerged branch it names.
- Not a lane: with `merge_mode = "pr"`, `git fetch origin` then
  `git switch --no-track -c <task> origin/<integration branch>`; with `"local"`,
  `git switch -c <task> <integration branch>`.

## 4. Write the plan
Copy `docs/plans/_TEMPLATE.md` to `docs/plans/YYYY-MM-DD-<task>.md` (today's date) and fill
every section. Change files with Edit or Write, never shell redirects, `sed -i` or scripts: the
hooks that guard the lane's paths watch only those tools.
- **Status:** Draft. **Branch / PR:** the branch from step 3. **Left to do:** "approval".
- **Open questions:** everything still undecided, each with a recommendation. Never settle one
  silently.
- **Reuse:** what you found in step 1, by path. **Steps:** tests first. **Tests:** what each
  proves. **Done when:** the template's boxes plus anything this task needs.
- From a backlog item: set its `status: now` and its `lane` (this lane, or `any`).
Follow-up ideas go in new backlog items (from `docs/backlog/_TEMPLATE.md`, `status: idea`), not
into this plan.

## 5. Stop for approval
Show the plan's path, its goal in one line, and the open questions with your recommendations.
Then stop. When the owner approves:
- set **Status:** Approved and **Left to do:** "build"; write each answered question into the
  plan, and any lasting decision at the top of `docs/design/decisions-log.md`;
- ask whether to commit the plan (message: "Plan: <title>", saying why the work is needed);
- tell the owner to start `/implement docs/plans/<plan file>` in a fresh session (`/clear`).

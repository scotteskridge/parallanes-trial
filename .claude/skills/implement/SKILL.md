---
name: implement
description: "Build one approved plan, test-first, on its task branch; stop whenever the plan doesn't settle something. Use for /implement docs/plans/<plan>.md, in a fresh session after the plan is approved."
model: sonnet
disable-model-invocation: true
argument-hint: "[docs/plans/<plan>.md]"
allowed-tools: Bash(sh .claude/kit/kit next) Bash(sh .claude/kit/kit next *) Bash(git status *) Read Grep Glob
---
Build this plan: $ARGUMENTS

## 0. Lane check
Run `sh .claude/kit/kit next --offline`. Its first line says where this folder is:
- `Here: lane <name>`: stay inside this lane's owned paths (the session-start hook listed them;
  an edit outside them asks first). Shared docs (`docs/plans/`, `docs/backlog/`,
  `docs/changelog.d/`, `docs/design/decisions-log.md`, `docs/health/`) are fine.
- `Here: main checkout` (or `a worktree that isn't a lane`): the project has lanes but this isn't
  one. Stop: build from the lane folder the plan's branch belongs to.
- `Here: not a lane`: the project has no lanes; work on the plan's branch here.
The current branch must be the one on the plan's **Branch / PR** line. If it isn't, stop and say
so; never build on the integration branch.

## 1. Read the plan
- No path given: use the plan `kit next` lists as Approved or In progress; if there are several,
  ask which one.
- Its status must be Approved or In progress, and every open question answered. Otherwise stop:
  the owner approves it first (`/plan-feature`).
- Set **Status:** In progress. Read what its *Reuse* section names before writing anything.

## 2. Build, one step at a time
For each step of the plan:
1. Write the tests first. Run the project's test command (`test_command` in `.claude/kit.toml`)
   and see them fail for the reason you expect.
2. Write the code until they pass. Run the whole suite, not just the new tests.
3. Update **Left to do:** to what remains.

Rules while building (the full set is in `AGENTS.md`):
- Change files with Edit or Write, never shell redirects, `sed -i` or scripts: the hooks that
  guard the lane's paths watch only those tools.
- **Never weaken, skip or delete a test, or swallow an exception, to make something pass.** Fix
  the cause, or stop and say so.
- **The plan doesn't settle something?** Stop and ask, with a recommendation. If the owner isn't
  there, build a clearly labelled placeholder (`Placeholder:` in a comment) and say so at the end.
- **Out of scope** ideas and bugs you notice go into new backlog items
  (`docs/backlog/_TEMPLATE.md`, `status: idea`), not into this change.
- The same correction from the owner twice? Note it: `/wrap-up` proposes a rule for it.
- Commit only when the owner asks.

## 3. Hand over
When every step is built:
- run the full test command and paste its result lines (evidence, not claims);
- set **Left to do:** to `/wrap-up`;
- list what you changed, any placeholders and any steps you changed from the plan (and why: these
  go in its *Notes after implementation* at wrap-up);
- tell the owner the next step is `/wrap-up`.

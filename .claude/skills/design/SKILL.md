---
name: design
description: "Settle one design question with the owner: read one section of the design docs, discuss the options, then record the answer in DESIGN.md and the decisions log on the owner's OK. Use for /design <topic or section>, when a plan or the code hits a question the design doesn't answer."
model: opus
disable-model-invocation: true
argument-hint: "[topic, section heading, or question]"
allowed-tools: Bash(sh .claude/kit/kit next) Bash(sh .claude/kit/kit next *) Bash(git status *) Read Grep Glob
---
Design question: $ARGUMENTS

You help the owner decide; the owner decides. This skill changes no branches and no code: its
only edits are to `docs/design/DESIGN.md` and `docs/design/decisions-log.md`, after an OK.

## 0. Lane check
Run `sh .claude/kit/kit next --offline`. Its first line says where this folder is:
- `Here: lane <name>`: fine. `DESIGN.md` isn't a shared path, so the edit in step 4 asks the owner
  once; the decisions log is shared. Both land with this lane's current task branch.
- `Here: main checkout` (or `a worktree that isn't a lane`): fine for discussion; before any edit,
  check the branch as below.
- `Here: not a lane`: fine; check the branch as below.
If this folder isn't on a task branch (it's on the integration branch, `integration_branch` in
`.claude/kit.toml`, default `main`, or detached between tasks), discuss freely but edit nothing:
say to start a task first. In a lane: `sh .claude/kit/kit lanes start <task>`. Without lanes, as
`/plan-feature` step 3 does: with `merge_mode = "pr"`, `git fetch origin` then
`git switch --no-track -c <task> origin/<integration branch>`; with `"local"`,
`git switch -c <task> <integration branch>`. From the main checkout, move to a lane.

## 1. Find the one section
- Search `docs/design/DESIGN.md` for the heading that fits the question (Grep for `^#`), and read
  that section only: never read it whole. Note its labels: **[BUILT]**, **[DIRECTION]**, **[OPEN]**.
- Search `docs/design/decisions-log.md` for earlier entries on the topic, so a settled question
  isn't argued again without saying it was settled.
- If `docs/design/VISION.md` exists, read the principles it lists (it's short).
- No `DESIGN.md` (it's optional): work from the decisions log, the code and the plans.
- Look at the code only as far as the question needs (a subagent for broad searches).

## 2. Discuss
State the question in one sentence. Give two or three real options, each with what it costs and
what it rules out, tied to the vision's principles where they apply. Recommend one and say why.
Then listen: the owner may pick, change the options, or decide it isn't ready.

## 3. Not settled?
If the owner doesn't decide now, offer to mark the point **[OPEN]** in `DESIGN.md` with the options
in one line each, so nobody settles it silently in code. Edit only on a yes.

## 4. Record the decision, on the owner's OK
Change files with Edit or Write, never shell redirects, `sed -i` or scripts: the hooks that guard
the lane's paths watch only those tools.
1. Show the **exact** `DESIGN.md` edit: the changed lines, with the point's new label
   (**[DIRECTION]** when agreed but not built, **[BUILT]** when the code already does it). Apply
   it on OK. With no `DESIGN.md`, skip this, and offer to create it from the section you would
   have written; create it only on a yes.
2. Add an entry at the top of `docs/design/decisions-log.md`, in the format its header shows:
   date, **Decision**, **Why** (with the main option rejected), **Affects** (the section changed).
3. If the decision changes work already planned, name the plan or backlog item it affects, and
   offer to note it there.
Commit nothing yourself: the edits go with the current task's commit (`/wrap-up`), or ask the
owner whether to commit them now.

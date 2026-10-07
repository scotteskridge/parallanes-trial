---
name: next
description: "Say what to work on next in this folder: unfinished work, plans waiting on the owner, open pull requests, other lanes, and the next ready backlog item. Read-only; ends with one recommended prompt. Use for /next, \"what's next\", \"where are we\", \"what should I work on\"."
model: sonnet
effort: low
allowed-tools: Bash(sh .claude/kit/kit next) Bash(sh .claude/kit/kit next *) Bash(git status *) Bash(gh pr list *) Bash(gh pr checks *) Read Grep Glob
---
What to work on next. $ARGUMENTS

**Read-only.** Change no files, branches or pull requests, and start no work: report, then
recommend one prompt for the owner to send. Run commands from the project root.

## 0. Lane check
Run `sh .claude/kit/kit next` (add `--offline` if `gh` is missing or slow). Its first line says
where this folder is:
- `Here: lane <name>`: answer for this lane. Backlog items count when their lane is this lane or
  `any`; other lanes get one line at the end.
- `Here: main checkout` (or `a worktree that isn't a lane`): the project has lanes but this folder
  isn't one. Answer for the whole project, and say that task work happens in a lane folder.
- `Here: not a lane`: the project has no lanes; answer for the whole project.
If the command fails, show its message and stop: the facts below can't be trusted without it.

## 1. Gather
- The rest of `kit next`: lanes (branch, ahead/behind, changed files, PR), plans by status, backlog
  items by status, and **Problems** (files it couldn't read or parse, blockers that name nothing).
- Not in a lane, and the project opens pull requests: `gh pr list --state open --json
  number,title,headRefName,url`, then `gh pr checks <n>` for each. A non-zero exit from
  `gh pr checks` means failing or pending checks: report it. If `gh pr list` itself fails, say
  "PR status unavailable (gh)" and carry on.
- Only when the answer lands on a plan: read its *Open questions* and *Left to do* lines.

## 2. Work out the state, first match wins
1. **A plan with status Draft:** waiting on the owner's approval of the plan and its open questions.
2. **A plan In progress or Approved:** building is under way. If its *Left to do* says `/wrap-up`,
   the next step is `/wrap-up`; otherwise `/implement <plan path>` in a fresh session.
3. **Unfinished work without a pull request:** changed files (untracked ones alone don't count), or
   a task branch ahead of the integration branch with no PR. The next step is `/wrap-up`.
4. **An open pull request** for this lane (or, outside a lane, any): waiting on the owner's review.
   In a lane, the next task can't start until it is merged (`lanes start` checks).
5. **The first ready backlog item:** status `now`, then `next`; not blocked, or its blocker (an item
   or a plan) is marked `(done)`. Size `S`: just ask for it. `M` or `L`: `/plan-feature <slug>`.
6. **Nothing ready:** say so; suggest moving an `idea` or `later` item up, or adding one.

**Blocked** lists items whose blocker isn't done, and what they wait on. A blocker that names
nothing shows under Problems: report it, it is probably a typo. Don't guess dependencies that
aren't written down.

## 3. Answer in about 15 lines, exactly this shape
```
**Where you are:** <lane or folder> · <branch> · <clean | N changed · N untracked> · <in a lane: N ahead / N behind>
**Waiting on you:** <draft plans to approve / PRs to review (CI result)> or "nothing"
**Ready next:** <the step from section 2: one line on what it is>
**Blocked:** <items and what they wait on> or "nothing"
**Other lanes:** <one line each: lane, branch or idle, PR> (omit when there are no lanes)
**Problems:** <each problem kit next listed, with its reason> (omit when none)

**Recommended prompt:**
> <the exact message the owner could send next>
```

The recommended prompt follows the daily loop in `docs/ai/WORKFLOW.md`: approving a plan
("Approved, go with your recommendations", only after reading it), `/implement <plan path>`,
`/wrap-up`, reviewing a PR ("Review PR #N; if approved, say so and I'll merge it"), or
`/plan-feature <slug>`. Never suggest skipping a review or an approval.

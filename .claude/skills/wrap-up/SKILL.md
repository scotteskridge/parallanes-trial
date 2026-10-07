---
name: wrap-up
description: "Finish the current task: run the tests, get the reviewer's report and fix what it finds, write the changelog fragment and plan notes, propose rules for repeated corrections, then on the owner's yes commit and open the pull request (lanes finish). Use for /wrap-up when a task is built."
model: sonnet
disable-model-invocation: true
argument-hint: "[docs/plans/<plan>.md]"
allowed-tools: Bash(sh .claude/kit/kit next) Bash(sh .claude/kit/kit next *) Bash(git status *) Read Grep Glob
---
Wrap up the current task. $ARGUMENTS

## 0. Lane check
Run `sh .claude/kit/kit next --offline`. Its first line says where this folder is:
- `Here: lane <name>`: step 6 finishes with `lanes finish`.
- `Here: main checkout` (or `a worktree that isn't a lane`): the project has lanes but this isn't
  one. Stop: wrap up from the lane folder the task's branch is in.
- `Here: not a lane`: the project has no lanes; step 6 uses git and `gh` directly.
Stop if the current branch is the integration branch. The plan is the one named, or the one
`kit next` lists as In progress; a small task may have none.

## 1. Test
Run the full test command (`test_command` in `.claude/kit.toml`) and keep its result lines. If
anything fails, fix the cause or stop and say so. Never weaken or skip a test.

## 2. Review
Use the `reviewer` subagent (`.claude/agents/reviewer.md`) in the foreground, and wait for its
report before anything else: it reviews what you have, so change nothing while it runs. Give it
the integration branch, the plan path and the test result lines. Then:
- 🔴 fix now: fix each one, with a test that fails without the fix.
- 🟠 fix soon: fix it, or ask the owner whether it can wait (then it becomes a backlog item).
- 🟡 polish: fix the cheap ones; list the rest.
- *Needs the owner*: ask. Never settle a design question yourself.
After substantial fixes, run the tests and the reviewer again, until a round has no 🔴.

## 3. Docs
Change files with Edit or Write, never shell redirects, `sed -i` or scripts: the hooks that guard
the lane's paths watch only those tools. Moves are `git mv`.
- **Changelog fragment:** `docs/changelog.d/<lane>-<task>.md` (outside a lane: `<task>.md`), in
  the format `docs/changelog.d/README.md` describes. Nothing user-visible: no fragment.
- **Plan:** fill *Notes after implementation* (what changed from the plan and why, the review
  rounds), tick its *Done when* boxes, set **Status:** Done, and move it into
  `docs/plans/finished/` with `git mv`.
- **Backlog:** the item this task finished moves to `docs/backlog/done/` with `git mv`.
- **Decisions** made along the way: one entry each at the top of `docs/design/decisions-log.md`.

## 4. Corrections worth a rule
Look back over this session, and ask the owner: did anything need correcting more than once? For
each such thing propose **one** of these, with the exact lines:
- a `.claude/rules/` line, when the author should know it while writing (scoped with `paths:`);
- a check in `.claude/review/project.md` (the next free `P` number), when review should catch it;
- a rule-check pattern in `.claude/kit.toml`, when it's a literal that must never appear.
Write nothing yet: approved rules are written and committed in step 6, after the task's commit.

## 5. Propose
Show: the files changed, the test result lines, the reviewer's verdict and what was fixed, and a
commit message that says *why*. Ask: "Commit and open the pull request?" Wait for a yes.

## 6. Finish, on the owner's yes
1. Stage the task's files by name and commit. Untracked files you didn't create: ask first.
   Then write the rules the owner approved in step 4 and commit them on their own ("Add a rule:
   <what>"), so the task's commit holds only the task. `lanes finish` refuses uncommitted changes
   to tracked files, and a new file left uncommitted won't land.
2. The PR body: the plan link, a short summary, the test result lines, the reviewer's report, and
   a table of findings and their fixes. Pass it on stdin (`--body-file -`), never as a file: a
   file outside the lane's paths makes the ownership hook ask.
3. In a lane, as one command:
   ```
   sh .claude/kit/kit lanes finish --title "<title>" --body-file - <<'EOF'
   <the PR body>
   EOF
   ```
   It syncs, tests again, then pushes and opens the PR (or, in local mode, fast-forwards the
   integration branch; the body is then unused). If it stops on a conflict or a failure, show its
   message and work through it with the owner; never force-push. If it refuses files outside the
   lane, list them: the owner decides whether that work moves to its own lane or they land it
   themselves. Never set `KIT_ALLOW_CROSS_LANE`; it is for a person.
4. Not a lane: with `merge_mode = "pr"`, ask before `git push -u origin HEAD`, then run
   `gh pr create --base <integration branch> --title "<title>" --body-file -` with the same
   heredoc. With `"local"`, stop after the commit and say how to merge it.
5. Give the PR link (or say what was merged), and suggest `/clear` before the next task.

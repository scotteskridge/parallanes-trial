# worklanes-trial: rules for every coding agent

A small reading-list tracker: an Express API in `server/` and a plain HTML/JS front end in
`public/`, with no build step. It is the two-lane trial project for claude-code-lanes-starter.

## Stack
Node.js

The shell starts at the project root: never prefix commands with `cd`.

## Checking your work
- After every change, run `npm test` and report the result lines. Evidence, not claims.
- Read failure messages and stack traces before fixing anything.
- For a bug, write the failing test first.
- **Never weaken, skip or delete a test, or swallow an exception, to make something pass.** Fix the
  cause, or stop and say so.

## Hard rules
- **Search before you create.** Extend what exists, and say what you found.
- **Never hide errors.** No empty catch blocks, no silent fallbacks for states that should be
  impossible: fail loudly.
- **Stay in scope.** One task per session. List follow-up ideas at the end instead of doing them.
- **Never settle an open design question silently.** Ask, or build a clearly labelled placeholder
  (`Placeholder:` in a comment) and say so. Settled decisions go at the top of
  `docs/design/decisions-log.md`.
- **No secrets in the repo.** Keys and tokens live outside it; `.env` is never committed. Check the
  diff for secrets before every commit.
- No new dependencies without asking.
- Comments say *why*, matching the density of the code around them. Standards:
  `docs/CODE-STANDARDS.md`.

## How work flows
1. Anything that touches several files, or where the approach is unclear, gets a plan first in
   `docs/plans/` (from `_TEMPLATE.md`). Stop for approval before building.
2. Each task runs on its own short-lived branch, never directly on `main`.
3. Finishing: tests pass, an independent review, a changelog fragment in `docs/changelog.d/`, then a
   pull request.
4. Future work goes in `docs/backlog/` (one file per item), not into the current task.
5. Commit and push only when asked. Commit messages say *why*.

## Parallel lanes
Several agents may work on this repo at once, each in its own git worktree (a "lane") that owns
part of the code. Stay inside your lane's paths. If files change that you didn't touch, another
session may be working in this folder: stop and tell the user. Details: `docs/ai/parallel-lanes.md`.

## Where things are
- `docs/plans/`: open plans; finished ones in `docs/plans/finished/`.
- `docs/backlog/`: future work, one file per item.
- `docs/design/`: `decisions-log.md` (why we chose); `VISION.md` (why) and `DESIGN.md` (what) if
  present.
- `docs/ai/WORKFLOW.md`: the human guide to this setup.

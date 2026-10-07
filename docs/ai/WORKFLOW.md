# Working with AI agents on worklanes-trial

A guide for the people on this project: how the agent setup works, the daily loop, and why each rule
exists. The agents read `AGENTS.md` and `CLAUDE.md`; this file is for you.

## 1. The idea in one paragraph

AI coding agents are fast and confident, and they drift: they skip tests under pressure, re-invent
helpers that already exist, quietly decide things you meant to decide, and lose track of a task as
the conversation grows. This setup answers each of those with the lightest tool that works: short
written rules for judgement, scripts and hooks for rules that must never break, an independent
reviewer for what slips through, and small tasks so context stays clean.

## 2. What each piece prevents

| Piece | Where | Prevents |
| --- | --- | --- |
| Short always-loaded rules | `AGENTS.md`, `CLAUDE.md` | The agent not knowing how to check its work, or what it must never do |
| Path-scoped rules | `.claude/rules/*.md` | Area knowledge (tests, UI, data) bloating every session; loads only when matching files are touched |
| Plans before code | `docs/plans/` | Building the wrong thing; big unreviewable changes; decisions made silently mid-build |
| Skills | `/plan-feature`, `/implement`, `/wrap-up`, `/next`… | Skipped steps: each workflow is written down once and followed the same way every time |
| Independent reviewer | `reviewer` subagent + `.claude/review/` checklists | The author grading its own work; it reviews only the change, against the rules, the plan and numbered checks, and can't edit anything |
| Hooks | `.claude/settings.json` → `.claude/kit/` | Breaking a hard rule (forbidden patterns, protected files, dangerous git commands) even under pressure |
| Permission deny rules | `.claude/settings.json` | Edits to protected paths and reads of secrets by Claude's own tools ([what they don't stop](protected-paths.md)) |
| One branch per task + PR | `sh .claude/kit/kit lanes start` / `finish` | Drift, untested merges, unreviewed changes reaching `main` |
| Fragments, one file per item | `docs/changelog.d/`, `docs/backlog/` | Merge conflicts between parallel lanes over shared docs |
| CI | `.github/workflows/` | Anything that bypassed the hooks: other tools, humans, skipped steps |

## 3. The daily loop

1. **Pick the task.** `/next` lists what's ready for this lane, what's waiting on you, and what's
   blocked.
2. **Size it.**
   - *Small* (one file, obvious fix): just ask, in a fresh session.
   - *Medium or unclear* (several files, a new behaviour): `/plan-feature`. It asks you questions,
     writes a plan, and stops. Read the plan; edit it if needed; approve it.
   - *Large*: the plan proposes a split. Each part is its own plan.
3. **Build it.** In a fresh session: `/implement docs/plans/<plan>.md`. It works test-first and
   stops if the plan doesn't settle something.
4. **Finish it.** `/wrap-up` runs the tests, calls the reviewer, fixes what must be fixed, writes the
   changelog fragment, and proposes a commit message. On your yes it commits and runs
   `sh .claude/kit/kit lanes finish`, which tests again and opens the pull request (in local mode it
   fast-forwards `main` instead).
5. **Review and merge** the pull request. Then `/clear`, and back to step 1.

**Why plan and build are separate sessions:** the planning conversation is full of options you
rejected. A fresh session that reads only the approved plan builds what you approved, not what was
discussed along the way.

## 4. Prompting: what good looks like

- Say what *done* looks like: "the export button downloads a CSV with these columns" beats "add
  export".
- Point at what exists: "follow the pattern in `reports/pdf.py`".
- Ask for the trade-off, not a survey: "recommend one approach and say what it costs".
- When it's wrong, say what's wrong and why. If you correct the same thing twice, `/wrap-up` will
  propose a rule so it doesn't happen a third time.

## 5. Context hygiene: the habits that matter most

- **One task per session.** `/clear` between tasks. Long sessions get summarized ("compacted"), and
  detail is lost in the summary.
- **Let subagents read.** Broad searches and audits run in subagents, so only their conclusions land
  in your conversation.
- **Keep the always-loaded files short.** Every line of `AGENTS.md` and `CLAUDE.md` is read in every
  session. Budgets: 80 and 40 lines.
- **Read one section, not the whole document.** Design docs are searched by heading.

## 6. Reviewing the agent's work

- Read the plan carefully; it's the cheapest place to catch a mistake.
- Read the reviewer's report before the diff: it points at the risky parts. Each finding cites a
  check (`U4`, `P2`) from `.claude/review/`; a finding marked *needs the owner* is a design
  question for you.
- The reviewer can't edit files or run anything but read-only git: a hook in its definition blocks
  the rest. Claude Code skips that hook in a folder it doesn't trust, so open Claude Code in this
  project once and accept the trust dialog.
- A mistake the reviewer should have caught: add a check to `.claude/review/project.md` (the next
  free `P` number; never reuse a retired one).
- Ask the agent to explain any change you don't understand before merging it.
- Test evidence means pasted result lines, not "tests pass".

## 7. Keeping the setup healthy

- **Rules files** (`.claude/rules/*.md`) must start with `paths:` frontmatter, or they load in every
  session. Keep each under 200 lines. `/onboard` proposes a first set for this codebase.
- **New hard rules:** if something must *never* happen, add it to `.claude/kit.toml` (checked by
  hooks and CI) rather than as more prose.
- **Changes to `AGENTS.md`, `CLAUDE.md` or rules** go through you: the agent proposes exact lines and
  waits.
- Run `/code-health` every few features, or before a milestone.

## 8. Warning signs

| You notice | Likely cause | Do this |
| --- | --- | --- |
| The agent ignores a rule it followed earlier | Session too long; the rule was compacted away | `/clear` and restart from the plan |
| The same mistake twice | A missing rule | Accept `/wrap-up`'s rule proposal, or add a check in `kit.toml` |
| Files changed that this session didn't touch | Two sessions in one folder | Stop one; one session per lane folder |
| A plan keeps growing | The task was bigger than it looked | Split it |
| Tests were edited to pass | Pressure to finish | Reject the change; the hard rule is no weakening tests |

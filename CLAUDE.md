@AGENTS.md

## Claude Code
- **Your lane:** at session start a hook tells you this folder's lane, branch, owned paths and any
  drift. Follow it. If it's missing, run `sh .claude/kit/kit lanes status`.
- **Skills:** `/plan-feature` → `/implement` → `/wrap-up` for a feature; `/next` to pick the next
  task; `/design` for design discussion; `/code-health` for a periodic audit; `/onboard` once after
  install.
- **Hooks enforce some rules automatically.** If one blocks you, fix the cause; never work around
  it. If you think the hook is wrong, say so.
- **Use a subagent for broad searches,** so file dumps stay out of this conversation.
- **Edits to `AGENTS.md`, this file or `.claude/rules/`:** propose the exact lines and wait for an
  OK; never append on your own. Budgets: `AGENTS.md` ≤ 80 lines, this file ≤ 40, each rules file
  ≤ 200.
- When a task is done, suggest `/clear` before the next one.

## Compact instructions
When compacting, keep: the task, the approved plan, the files changed, the latest test results, and
any open questions for the user.

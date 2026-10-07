# Decisions log

Why things were decided, newest first. The current design lives in [DESIGN.md](DESIGN.md) (or the
code); this file keeps the *why* so nobody re-argues a settled question without knowing it was
settled.

Entry format:

```markdown
## YYYY-MM-DD: Short title
**Decision:** what was chosen.
**Why:** the reason, and the main alternative that was rejected.
**Affects:** design sections, plans or code areas.
```

## 2026-10-07: Adopt the multi-lane agent workflow
**Decision:** use the claude-code-lanes-starter kit (0.1.0.dev0): plans before code, one
short-lived branch per task, independent review before merge, parallel lanes for concurrent work.
**Why:** keeps AI-assisted changes small, reviewed and traceable.
**Affects:** `AGENTS.md`, `CLAUDE.md`, `.claude/`, `docs/`.

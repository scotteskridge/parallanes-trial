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

## 2026-10-07: How PATCH /api/books/:id resolves ids and orders its errors
**Decision:** the id is matched with `Number()`, so `/api/books/1.0` (or `0x1`, `1e0`) reaches book
1 and a non-numeric id is a 404. An unknown id gets the 404 before the body is checked, so a bad id
with a bad body is a 404, not a 400.
**Why:** simplest correct behaviour for an in-memory list; a stricter digits-only id check was
considered and not needed yet. Checking the resource first follows the usual REST order.
**Affects:** `server/app.js` (PATCH route).

## 2026-10-07: Adopt the multi-lane agent workflow
**Decision:** use the claude-code-lanes-starter kit (0.1.0.dev0): plans before code, one
short-lived branch per task, independent review before merge, parallel lanes for concurrent work.
**Why:** keeps AI-assisted changes small, reviewed and traceable.
**Affects:** `AGENTS.md`, `CLAUDE.md`, `.claude/`, `docs/`.

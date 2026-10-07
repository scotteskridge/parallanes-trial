# Code health: YYYY-MM-DD (<area>)

**Scope:** <areas audited, and where they came from: lanes or top-level folders>
**Commit:** <the commit audited> · **Checklists:** <the `.claude/review/*.md` files used>
**Summary:** <one or two lines: the state of the code, and the most important finding>

## Findings
One line each, most severe first. Severity: 🔴 fix now · 🟠 fix soon · 🟡 polish
(`docs/CODE-STANDARDS.md`). The check is a checklist ID (`U4`, `P2`) or a kind: duplication,
hidden error, drift, size, untested, stale TODO.

| # | Severity | Check | Where (`path:line`) | What and why | Backlog item |
| --- | --- | --- | --- | --- | --- |
| 1 | 🟠 | U4 | `src/orders/sync.py:88` | An `except Exception: pass` hides failed syncs | `sync-errors-swallowed` |

## By area
### <area name> (`<glob or folder>`)
<two or three lines: what's healthy, what isn't, and anything that didn't fit a finding>

## Not checked
<anything left out, and why: generated code, vendored files, an area too large to read>

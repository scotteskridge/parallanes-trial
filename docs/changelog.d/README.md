# Changelog fragments

Each task branch adds **one new file** here instead of editing `../CHANGELOG.md`, so parallel lanes
never conflict over the changelog. `sh .claude/kit/kit changelog build` compiles the fragments into
[CHANGELOG.md](../CHANGELOG.md) at release time and deletes them.

**Name:** `<lane>-<task>.md`, matching the branch `<lane>/<task>` (branch names contain `/`, file
names can't).

**Content:** one or more of these headings, each with short bullets written for the people who use
the project, not for its developers:

```markdown
### Added
- You can now export a report as CSV.

### Fixed
- Totals no longer double-count refunded orders.
```

Allowed headings: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`
([Keep a Changelog](https://keepachangelog.com/en/1.1.0/)). A task with nothing user-visible writes
no fragment.

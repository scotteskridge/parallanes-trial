---
# Loads when an agent reads or edits the design docs, plans or backlog.
paths:
  - "docs/design/**"
  - "docs/plans/**"
  - "docs/backlog/**"
---
# Design docs, plans and backlog

`VISION.md` and `DESIGN.md` are optional; if one doesn't exist, skip what's said about it here.

- **`docs/design/VISION.md`**: why the project exists and the few principles every feature serves.
  Only the owner changes it.
- **`docs/design/DESIGN.md`**: the current intended design, kept up to date when a question is
  settled. Read one section at a time (search for its heading); don't read it whole.
- **`docs/design/decisions-log.md`**: why each decision was made, newest first. History, not the
  current rule: if it disagrees with `DESIGN.md`, a design edit was missed. Flag it.
- **Open questions:** never settle one in code or in a plan. Ask, or use a labelled placeholder and
  list it in the plan's *Open questions*.
- **When the owner settles a point:** show the exact `DESIGN.md` edit, apply it on OK, then add a
  decisions-log entry (date, the choice, why, the section changed).
- **Plans** (`docs/plans/`) follow `_TEMPLATE.md`, aim for one screen, and stop at Draft until the
  owner approves. More than ~8 steps: propose a split.
- **Backlog** items are one file each in `docs/backlog/`; see its `README.md` for the header fields.
  Finished items move to `docs/backlog/done/`.

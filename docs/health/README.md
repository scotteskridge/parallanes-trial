# Code health reports

One file per audit, named by date, lane and area (`YYYY-MM-DD-<lane>-<area>.md`), written by
`/code-health`: the whole codebase checked by area against the project's rules, with each
finding's severity and place.
Run it every few features or before a milestone.

The reports are a record, not a to-do list: findings worth fixing become items in
[`../backlog/`](../backlog/README.md), and the report names them. Each run adds a new file (a
second run with the same date and area gets `-2`), so lanes don't edit each other's reports.

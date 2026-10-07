# Backlog

Future work, **one file per item**, so parallel lanes can add and finish items without editing the
same file. Copy [_TEMPLATE.md](_TEMPLATE.md) to `<short-slug>.md`. When an item is done, move it to
`done/` (with `git mv`) in the same branch that finished it.

## Header fields

| Field | Values | Meaning |
| --- | --- | --- |
| `status` | `now`, `next`, `later`, `idea` | `now`: being worked on or first in line; `idea`: not yet agreed |
| `lane` | a lane name, or `any` | Which lane does the work |
| `size` | `S`, `M`, `L` | S: under an hour; M: one session; L: needs a plan first |
| `blocked_by` | optional: another item's slug, or a plan's file name (`2026-10-01-schema`) | Why it can't start yet; done once the item is in `done/` or the plan in `../plans/finished/` |

Agents add items here instead of building them in the middle of another task. `/next` reads these
headers to say what's ready.

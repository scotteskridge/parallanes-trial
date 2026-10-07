# Plans

One file per plan, written from [_TEMPLATE.md](_TEMPLATE.md) and named `YYYY-MM-DD-short-slug.md`
(the date the plan was started). Dates and slugs need no shared counter, so lanes planning at the
same time never collide. A plan is written and approved before the code; building it happens in a
separate session. Finished plans (done, rolled back or superseded) move to `finished/`.

There is no index table to keep in step: each plan's `**Status:**` and `**Left to do:**` lines are
the record, and `/next` reads them.

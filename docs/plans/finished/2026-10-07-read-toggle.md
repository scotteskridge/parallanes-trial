# Read toggle on book cards

**Status:** Done
**Left to do:** nothing
**Branch / PR:** `web/read-toggle`
**Builds on:** `PATCH /api/books/:id` (api lane, `docs/changelog.d/api-mark-read.md`); the add form
(`docs/changelog.d/web-add-form.md`)

## Goal
Each book card has a "Read" checkbox showing the book's `read` field; ticking it saves the change.
Read books look muted (greyed title), and a count above the list says e.g. "2 of 5 read".

## Out of scope
- Filtering or sorting by read state.
- Any change to the API.

## Open questions
- Where a failed toggle's message appears. Settled by the owner: the form's error area
  (`#add-book-error`), with the form's rules. See the decisions log.
- What the count shows with no books. Settled by the owner: it is hidden. See the decisions log.

## Reuse
- `public/render.js`: `renderBooks` gains the checkbox and the muted class.
- `public/add-book.js`: same request/response pattern (`addBook`/`submitBook`); `loadBooks` and
  `submitBook` also update the count.
- `public/style.css`: `.form-error` styles the message already.

## Changes
| File | New / Edit | What |
| --- | --- | --- |
| `public/toggle-read.js` | New | `setRead` (PATCH) and `toggleRead` (checkbox change handler) |
| `public/render.js` | Edit | checkbox per card, `read` class, `renderReadCount` |
| `public/add-book.js` | Edit | update the count after load and add |
| `public/app.js` | Edit | one delegated `change` listener on the list |
| `public/index.html` | Edit | `#read-count` above the list |
| `public/style.css` | Edit | card layout for the checkbox, muted title |

## Tests
| Test | Proves |
| --- | --- |
| render: checkbox reflects `read`, card gets `read` class | the card shows the field |
| render: count text and hidden-when-empty | "2 of 5 read" |
| setRead: PATCH body, 200 / 400 / 404 / other | request and response handling |
| toggleRead: success, API error, server error, offline | box restored and message shown on failure |
| loadBooks / submitBook update the count | count stays in step |

## Done when
- [x] Tests above pass; the full suite passes
- [x] Independent review done; every "fix now" finding fixed
- [x] Changelog fragment written; decisions log updated for any decision made

## Notes after implementation
- Owner checked it on port 3002 (toggle, greyed title, count, change kept by the server) and
  confirmed both placeholders.
- Review round 1 (ready, 1 🟠, 4 🟡), all fixed:
  - 🟠 A redraw during a save (say, adding a book) left a stale, clickable box. `toggleRead` now
    keeps the value being saved in `book.pendingRead`. `renderBooks` draws that value, disabled,
    and the box is looked up again when the save ends.
  - 🟡 A successful toggle hid the add form's message. It now hides only the toggle's own message.
  - 🟡 `test-fakes.js` matched `node --test`'s `test-*.js` pattern, so it was renamed `fakes.js`.
  - 🟡 Placeholder comments were reworded once settled.
  - 🟡 Each box is now named "Read: <title>" for screen readers.
- Round 2 (ready, 2 🟡), both fixed. Matching on message text failed when both messages used the
  same wording, so each writer now marks its message with `data-source`. A redraw now shows the
  value being saved, not the old one.
- Round 3: no findings.
- Not in the plan: `public/fakes.js` (the fake `fetch` moved out of `add-book.test.js` to be shared),
  and `add-book.js` marking its messages with `data-source`.

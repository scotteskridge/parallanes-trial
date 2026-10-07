### Added
- Every book now has a `read` field, false for new books. `PATCH /api/books/:id` with `{read: true|false}` marks a book as read or unread and returns it. An unknown id gets a 404, and a `read` that isn't true or false gets a 400, each with an error message.

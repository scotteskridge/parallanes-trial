---
status: idea
lane: api
size: S
---
# Check each book in books.json when the server loads it

The books file can be edited by hand. One entry without a numeric `id` makes `Math.max` return
`NaN`, so every book added afterwards gets the id `NaN`. Other missing or wrong-typed fields would
show up later, in the page or in a route. Found in the review of `api/persist`, which left each
book's fields unchecked on purpose.

**Done when:** a books file with a book that has no integer `id`, no `title` or `author`, or a
`read` that isn't true or false stops the server at startup with an error naming the file and the
book, like a file that isn't valid JSON does.

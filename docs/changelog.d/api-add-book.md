### Added
- The API can now add a book: `POST /api/books` with `{title, author}` returns the new book with its id. A missing or blank title or author gets a 400 with an error message.

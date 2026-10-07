### Added
- Your books now survive a server restart. They are kept in `data/books.json`, created with the two starting books the first time the server runs. Set `BOOKS_FILE` to keep them somewhere else.
- If that file is damaged (not valid JSON, or not a list of books), the server won't start and says which file is the problem; it leaves the file as it is.

// Reads and writes the books file. Synchronous on purpose: the list is small, and a write that
// finishes before the response goes out means a 2xx always means "saved".
import fs from "node:fs";
import path from "node:path";

const startingBooks = [
  { id: 1, title: "The Pragmatic Programmer", author: "Andrew Hunt and David Thomas", read: false },
  { id: 2, title: "A Philosophy of Software Design", author: "John Ousterhout", read: false },
];

// Both the default and a relative BOOKS_FILE resolve against the project root, so the same
// setting names the same file wherever the server is started from.
export function resolveBooksFile(configured, projectRoot) {
  return path.resolve(projectRoot, configured || path.join("data", "books.json"));
}

export function loadBooks(file) {
  let text;
  try {
    text = fs.readFileSync(file, "utf8");
  } catch (err) {
    // Not every fs error carries the path (EISDIR doesn't), so name the file ourselves.
    if (err.code !== "ENOENT") throw new Error(`cannot read ${file}: ${err.message}`, { cause: err });
    // Written at startup rather than on the first change, so the file always exists once the
    // server is up.
    const books = structuredClone(startingBooks);
    saveBooks(file, books);
    return books;
  }
  // A bad file stops the server instead of falling back to the seed, which would overwrite the
  // reader's books on the next change.
  let books;
  try {
    books = JSON.parse(text);
  } catch (err) {
    throw new Error(`${file} is not valid JSON: ${err.message}`, { cause: err });
  }
  if (!Array.isArray(books)) {
    throw new Error(`${file} must hold a JSON list of books`);
  }
  return books;
}

export function saveBooks(file, books) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  // Write a temp file and rename it over the real one, so a crash mid-write can't leave half a file.
  const tmp = `${file}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(books, null, 2) + "\n");
  fs.renameSync(tmp, file);
}

// Builds the book list. `doc` is a parameter so tests can pass a stand-in for `document`.
export function renderBooks(list, books, doc = document) {
  if (books.length === 0) {
    const empty = doc.createElement("li");
    empty.className = "empty";
    empty.textContent = "No books yet";
    list.replaceChildren(empty);
    return;
  }

  const cards = books.map((book) => {
    const card = doc.createElement("li");
    card.className = cardClass(book);
    const title = doc.createElement("strong");
    title.className = "book-title";
    title.textContent = book.title;
    const author = doc.createElement("span");
    author.className = "book-author";
    author.textContent = book.author;
    const toggle = doc.createElement("label");
    toggle.className = "read-toggle";
    const checkbox = doc.createElement("input");
    checkbox.type = "checkbox";
    // `pendingRead` is set by toggleRead while a save runs: a redraw then shows what the user
    // ticked, and doesn't offer a second, overlapping save.
    const saving = book.pendingRead !== undefined;
    checkbox.checked = saving ? book.pendingRead : book.read;
    checkbox.disabled = saving;
    // One change listener on the list handles every box; the value says which book it is.
    checkbox.value = String(book.id);
    // The visible text is just "Read", which says nothing when a screen reader moves between boxes.
    checkbox.ariaLabel = `Read: ${book.title}`;
    toggle.append(checkbox, " Read");
    card.append(title, author, toggle);
    return card;
  });
  list.replaceChildren(...cards);
}

// Shared with toggle-read.js, which updates one card in place instead of re-rendering the list
// (re-rendering would drop keyboard focus from the box just toggled).
export function cardClass(book) {
  return book.read ? "book-card read" : "book-card";
}

// Hidden when there are no books, since the empty state already says so.
export function renderReadCount(count, books) {
  const read = books.filter((book) => book.read).length;
  count.textContent = `${read} of ${books.length} read`;
  count.hidden = books.length === 0;
}

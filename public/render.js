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
    card.className = "book-card";
    const title = doc.createElement("strong");
    title.className = "book-title";
    title.textContent = book.title;
    const author = doc.createElement("span");
    author.className = "book-author";
    author.textContent = book.author;
    card.append(title, author);
    return card;
  });
  list.replaceChildren(...cards);
}

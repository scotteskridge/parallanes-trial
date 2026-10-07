// The front end: plain modules, no build step.
const list = document.getElementById("books");

const res = await fetch("/api/books");
const books = await res.json();
for (const book of books) {
  const item = document.createElement("li");
  item.textContent = `${book.title} by ${book.author}`;
  list.append(item);
}

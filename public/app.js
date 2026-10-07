// The front end: plain modules, no build step.
import { loadBooks, submitBook } from "./add-book.js";

const form = document.getElementById("add-book");
const ui = {
  form,
  button: form.querySelector("button"),
  errorText: document.getElementById("add-book-error"),
  list: document.getElementById("books"),
};
const books = [];

// Attached before the list loads, so a submit during a slow or failed load can never fall through
// to the browser's own form submit (a page reload that adds nothing). The button is disabled until
// the load succeeds, which also blocks Enter-to-submit.
form.addEventListener("submit", (event) => {
  event.preventDefault();
  return submitBook(ui, books);
});

await loadBooks(ui, books);

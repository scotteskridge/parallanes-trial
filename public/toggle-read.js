import { cardClass, renderReadCount } from "./render.js";

// Saves a book's read state. `fetchFn` is a parameter so tests can pass a stand-in for `fetch`.
// Resolves to { book } on success or { error } when the API rejects the request (400 or 404).
export async function setRead(id, read, fetchFn = fetch) {
  const res = await fetchFn(`/api/books/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ read }),
  });
  if (res.status === 200) {
    return { book: await res.json() };
  }
  if (res.status === 400 || res.status === 404) {
    const { error } = await res.json();
    // Without this, a rejection with no message would look like success to the caller.
    if (typeof error !== "string" || error === "") {
      throw new Error(`PATCH /api/books/${id} returned ${res.status} without an error message`);
    }
    return { error };
  }
  throw new Error(`PATCH /api/books/${id} failed with status ${res.status}`);
}

// Handles a change to one card's "Read" box. The browser has already flipped `checkbox.checked`;
// `book.read` keeps the saved value until the API confirms, so a failure can put the box back.
// Errors use the add form's message area (`ui.errorText`), as loadBooks does.
export async function toggleRead(ui, books, checkbox, fetchFn = fetch, logError = console.error) {
  const { errorText, readCount, list } = ui;
  const book = books.find((b) => String(b.id) === checkbox.value);
  if (!book) {
    // Every box is rendered from `books`, so this means the page and its data are out of step.
    throw new Error(`No book with id ${checkbox.value} for this checkbox`);
  }
  // Disabled while saving so quick repeated clicks can't send requests that finish out of order.
  // `book.pendingRead` keeps it disabled, showing the new value, if the list is redrawn (say, by
  // adding a book) meanwhile.
  checkbox.disabled = true;
  book.pendingRead = checkbox.checked;
  // Marked as the toggle's, so a later success hides only its own message, never the add form's
  // (whose server-error wording is the same).
  const showError = (message) => {
    errorText.textContent = message;
    errorText.hidden = false;
    errorText.dataset.source = "toggle";
  };
  try {
    const { book: saved, error } = await setRead(book.id, book.pendingRead, fetchFn);
    if (error) {
      showError(error);
      return;
    }
    book.read = saved.read;
    renderReadCount(readCount, books);
    if (errorText.dataset.source === "toggle") {
      errorText.hidden = true;
    }
  } catch (err) {
    // Same wording as the add form: the user can't fix a server fault. Logged so the cause isn't lost.
    logError(err);
    showError("Something went wrong. Please try again.");
  } finally {
    delete book.pendingRead;
    // Looked up again rather than using `checkbox`: a redraw during the save replaces the box.
    const shown = list.querySelector(`input[type="checkbox"][value="${book.id}"]`);
    if (!shown) {
      throw new Error(`The "Read" box for book ${book.id} is no longer on the page`);
    }
    shown.checked = book.read;
    shown.disabled = false;
    shown.closest(".book-card").className = cardClass(book);
  }
}

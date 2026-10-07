import { renderBooks } from "./render.js";

// Posts a new book. `fetchFn` is a parameter so tests can pass a stand-in for `fetch`.
// Resolves to { book } on success or { error } when the API rejects the input (400).
export async function addBook({ title, author }, fetchFn = fetch) {
  const res = await fetchFn("/api/books", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, author }),
  });
  if (res.status === 201) {
    return { book: await res.json() };
  }
  if (res.status === 400) {
    const { error } = await res.json();
    // Without this, a 400 with no message would look like success to the caller.
    if (typeof error !== "string" || error === "") {
      throw new Error("POST /api/books returned 400 without an error message");
    }
    return { error };
  }
  // Anything else is a server fault, not something the user can fix by editing the form.
  throw new Error(`POST /api/books failed with status ${res.status}`);
}

// Loads the existing books into `books` and the list, then enables the add button. On failure the
// button stays disabled: the form can't show a new book among books that never loaded. The message
// reuses the add form's error area deliberately, since the form is unusable after a failed load.
export async function loadBooks(ui, books, fetchFn = fetch, logError = console.error) {
  const { button, errorText, list, doc } = ui;
  try {
    const res = await fetchFn("/api/books");
    if (!res.ok) {
      throw new Error(`GET /api/books failed with status ${res.status}`);
    }
    books.push(...(await res.json()));
    renderBooks(list, books, doc);
    button.disabled = false;
  } catch (err) {
    logError(err);
    errorText.textContent = "Could not load the reading list. Please reload the page.";
    errorText.hidden = false;
  }
}

// Handles one form submission. `ui` holds the page elements (and `doc`, for tests); `books` is the
// list currently shown and is added to on success. `fetchFn` and `logError` are parameters so
// tests need no network or console.
export async function submitBook(ui, books, fetchFn = fetch, logError = console.error) {
  const { form, button, errorText, list, doc } = ui;
  // Disabled while posting so a double click can't add the same book twice.
  button.disabled = true;
  try {
    const { book, error } = await addBook(
      { title: form.elements.title.value, author: form.elements.author.value },
      fetchFn,
    );
    if (error) {
      errorText.textContent = error;
      errorText.hidden = false;
      return;
    }
    books.push(book);
    renderBooks(list, books, doc);
    form.reset();
    errorText.hidden = true;
  } catch (err) {
    // Server error or no connection: the user can't fix it by editing the form, so say so briefly.
    // Logged as well, so the cause isn't lost.
    logError(err);
    errorText.textContent = "Something went wrong. Please try again.";
    errorText.hidden = false;
  } finally {
    button.disabled = false;
  }
}

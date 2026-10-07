import { test } from "node:test";
import assert from "node:assert/strict";
import { addBook, submitBook, loadBooks } from "./add-book.js";

// Records the request and answers with a fixed status and JSON body; no real network.
function fakeFetch(status, body) {
  const calls = [];
  const fetchFn = async (url, options) => {
    calls.push({ url, options });
    return { status, ok: status >= 200 && status < 300, json: async () => body };
  };
  return { fetchFn, calls };
}

test("posts the title and author as JSON to /api/books", async () => {
  const { fetchFn, calls } = fakeFetch(201, { id: 3, title: "Dune", author: "Frank Herbert" });
  await addBook({ title: "Dune", author: "Frank Herbert" }, fetchFn);

  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/books");
  assert.equal(calls[0].options.method, "POST");
  assert.equal(calls[0].options.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(calls[0].options.body), { title: "Dune", author: "Frank Herbert" });
});

test("a 201 resolves to the created book", async () => {
  const created = { id: 3, title: "Dune", author: "Frank Herbert" };
  const { fetchFn } = fakeFetch(201, created);

  assert.deepEqual(await addBook({ title: "Dune", author: "Frank Herbert" }, fetchFn), {
    book: created,
  });
});

test("a 400 resolves to the API's error message", async () => {
  const { fetchFn } = fakeFetch(400, { error: "title is required" });

  assert.deepEqual(await addBook({ title: " ", author: "Frank Herbert" }, fetchFn), {
    error: "title is required",
  });
});

test("any other status rejects with the status in the message", async () => {
  const { fetchFn } = fakeFetch(500, {});

  await assert.rejects(addBook({ title: "Dune", author: "Frank Herbert" }, fetchFn), {
    message: "POST /api/books failed with status 500",
  });
});

test("a 400 whose body has no error message rejects instead of reporting success", async () => {
  const { fetchFn } = fakeFetch(400, {});

  await assert.rejects(addBook({ title: " ", author: "X" }, fetchFn), {
    message: "POST /api/books returned 400 without an error message",
  });
});

// Just enough of the page for submitBook; same approach as render.test.js.
function fakePage(fieldValues) {
  const doc = {
    createElement: () => ({
      className: "",
      textContent: "",
      children: [],
      append(...nodes) {
        this.children.push(...nodes);
      },
      replaceChildren(...nodes) {
        this.children = nodes;
      },
    }),
  };
  return {
    doc,
    form: {
      elements: {
        title: { value: fieldValues.title },
        author: { value: fieldValues.author },
      },
      resets: 0,
      reset() {
        this.resets += 1;
      },
    },
    button: { disabled: false },
    errorText: { textContent: "", hidden: true },
    list: doc.createElement("ul"),
  };
}

test("submitBook adds the new book to the list, clears the form and hides the error", async () => {
  const ui = fakePage({ title: "Dune", author: "Frank Herbert" });
  ui.errorText.textContent = "old";
  const books = [];
  const created = { id: 3, title: "Dune", author: "Frank Herbert" };

  await submitBook(ui, books, fakeFetch(201, created).fetchFn);

  assert.deepEqual(books, [created]);
  assert.equal(ui.list.children.length, 1);
  assert.equal(ui.form.resets, 1);
  assert.equal(ui.errorText.hidden, true);
  assert.equal(ui.button.disabled, false);
});

test("submitBook shows the API's message on a 400 and leaves the form and list alone", async () => {
  const ui = fakePage({ title: " ", author: "Frank Herbert" });
  const books = [];

  await submitBook(ui, books, fakeFetch(400, { error: "title is required" }).fetchFn);

  assert.equal(ui.errorText.textContent, "title is required");
  assert.equal(ui.errorText.hidden, false);
  assert.deepEqual(books, []);
  assert.equal(ui.form.resets, 0);
  assert.equal(ui.button.disabled, false);
});

test("submitBook shows a general message on a server error and re-enables the button", async () => {
  const ui = fakePage({ title: "Dune", author: "Frank Herbert" });
  const books = [];
  const logged = [];

  await submitBook(ui, books, fakeFetch(500, {}).fetchFn, (err) => logged.push(err));

  assert.equal(ui.errorText.textContent, "Something went wrong. Please try again.");
  assert.equal(ui.errorText.hidden, false);
  assert.deepEqual(books, []);
  assert.equal(ui.button.disabled, false);
  assert.equal(logged.length, 1);
});

test("loadBooks fills the list and enables the add button", async () => {
  const ui = fakePage({ title: "", author: "" });
  ui.button.disabled = true;
  const books = [];
  const existing = [{ id: 1, title: "Dune", author: "Frank Herbert" }];

  await loadBooks(ui, books, fakeFetch(200, existing).fetchFn);

  assert.deepEqual(books, existing);
  assert.equal(ui.list.children.length, 1);
  assert.equal(ui.button.disabled, false);
});

test("loadBooks on a non-OK status shows a message and keeps adding disabled", async () => {
  const ui = fakePage({ title: "", author: "" });
  ui.button.disabled = true;
  const books = [];
  const logged = [];

  await loadBooks(ui, books, fakeFetch(500, {}).fetchFn, (err) => logged.push(err));

  assert.equal(ui.errorText.textContent, "Could not load the reading list. Please reload the page.");
  assert.equal(ui.errorText.hidden, false);
  assert.equal(ui.button.disabled, true);
  assert.deepEqual(books, []);
  assert.equal(logged.length, 1);
});

test("loadBooks when the request itself fails shows a message and keeps adding disabled", async () => {
  const ui = fakePage({ title: "", author: "" });
  ui.button.disabled = true;
  const offline = async () => {
    throw new TypeError("fetch failed");
  };

  await loadBooks(ui, [], offline, () => {});

  assert.equal(ui.errorText.textContent, "Could not load the reading list. Please reload the page.");
  assert.equal(ui.button.disabled, true);
});

test("submitBook shows the general message when the request itself fails", async () => {
  const ui = fakePage({ title: "Dune", author: "Frank Herbert" });
  const offline = async () => {
    throw new TypeError("fetch failed");
  };

  await submitBook(ui, [], offline, () => {});

  assert.equal(ui.errorText.textContent, "Something went wrong. Please try again.");
  assert.equal(ui.button.disabled, false);
});

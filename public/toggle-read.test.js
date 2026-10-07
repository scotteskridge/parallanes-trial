import { test } from "node:test";
import assert from "node:assert/strict";
import { setRead, toggleRead } from "./toggle-read.js";
import { fakeFetch } from "./fakes.js";

test("setRead sends the new read value as JSON to PATCH /api/books/:id", async () => {
  const { fetchFn, calls } = fakeFetch(200, { id: 2, title: "Emma", author: "Jane Austen", read: true });
  await setRead(2, true, fetchFn);

  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/books/2");
  assert.equal(calls[0].options.method, "PATCH");
  assert.equal(calls[0].options.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(calls[0].options.body), { read: true });
});

test("setRead on a 200 resolves to the updated book", async () => {
  const updated = { id: 2, title: "Emma", author: "Jane Austen", read: true };

  assert.deepEqual(await setRead(2, true, fakeFetch(200, updated).fetchFn), { book: updated });
});

test("setRead on a 400 or 404 resolves to the API's error message", async () => {
  assert.deepEqual(await setRead(2, true, fakeFetch(400, { error: "read must be true or false" }).fetchFn), {
    error: "read must be true or false",
  });
  assert.deepEqual(await setRead(9, true, fakeFetch(404, { error: "book not found" }).fetchFn), {
    error: "book not found",
  });
});

test("setRead on a 404 with no error message rejects instead of reporting success", async () => {
  await assert.rejects(setRead(9, true, fakeFetch(404, {}).fetchFn), {
    message: "PATCH /api/books/9 returned 404 without an error message",
  });
});

test("setRead on any other status rejects with the status in the message", async () => {
  await assert.rejects(setRead(2, true, fakeFetch(500, {}).fetchFn), {
    message: "PATCH /api/books/2 failed with status 500",
  });
});

// The browser has already flipped `checked` by the time the change event fires, so the fakes
// start in that state.
function fakeToggle({ read, checked }) {
  const book = { id: 1, title: "Dune", author: "Frank Herbert", read };
  const card = { className: read ? "book-card read" : "book-card" };
  const checkbox = fakeCheckbox(checked, card);
  const ui = {
    errorText: { textContent: "", hidden: true, dataset: {} },
    readCount: { textContent: "", hidden: true },
    // `shown` is the box on the page now; a test swaps it to act out a re-render.
    list: {
      shown: checkbox,
      querySelector(selector) {
        assert.equal(selector, `input[type="checkbox"][value="${book.id}"]`);
        return this.shown;
      },
    },
  };
  return { books: [book], book, card, checkbox, ui };
}

function fakeCheckbox(checked, card) {
  return { value: "1", checked, disabled: false, closest: () => card };
}

test("toggleRead saves the change, mutes the card and updates the count", async () => {
  const { books, book, card, checkbox, ui } = fakeToggle({ read: false, checked: true });

  await toggleRead(ui, books, checkbox, fakeFetch(200, { ...book, read: true }).fetchFn);

  assert.equal(book.read, true);
  assert.equal(checkbox.checked, true);
  assert.equal(checkbox.disabled, false);
  assert.equal(card.className, "book-card read");
  assert.equal(ui.readCount.textContent, "1 of 1 read");
});

test("toggleRead keeps the value being saved on the book until the request finishes", async () => {
  const { books, book, checkbox, ui } = fakeToggle({ read: false, checked: true });
  let pendingDuringRequest;
  const fetchFn = async () => {
    pendingDuringRequest = book.pendingRead;
    return { status: 200, ok: true, json: async () => ({ ...book, read: true }) };
  };

  await toggleRead(ui, books, checkbox, fetchFn);

  assert.equal(pendingDuringRequest, true);
  assert.equal(book.pendingRead, undefined);
});

test("toggleRead updates the box on the page now when the list was re-drawn during the save", async () => {
  const { books, book, checkbox, ui } = fakeToggle({ read: false, checked: true });
  const redrawnCard = { className: "book-card" };
  // As renderBooks draws it mid-save: the value being saved, disabled.
  const redrawn = { ...fakeCheckbox(true, redrawnCard), disabled: true };
  const fetchFn = async () => {
    ui.list.shown = redrawn;
    return { status: 200, ok: true, json: async () => ({ ...book, read: true }) };
  };

  await toggleRead(ui, books, checkbox, fetchFn);

  assert.equal(redrawn.checked, true);
  assert.equal(redrawn.disabled, false);
  assert.equal(redrawnCard.className, "book-card read");
});

test("a successful toggle hides an earlier toggle error", async () => {
  const { books, book, checkbox, ui } = fakeToggle({ read: false, checked: true });
  await toggleRead(ui, books, checkbox, fakeFetch(404, { error: "book not found" }).fetchFn);
  checkbox.checked = true;

  await toggleRead(ui, books, checkbox, fakeFetch(200, { ...book, read: true }).fetchFn);

  assert.equal(ui.errorText.hidden, true);
});

test("a successful toggle leaves the add form's message showing, even with the same wording", async () => {
  const { books, book, checkbox, ui } = fakeToggle({ read: false, checked: true });
  await toggleRead(ui, books, checkbox, fakeFetch(500, {}).fetchFn, () => {});
  // The add form then fails the same way, as submitBook writes it.
  ui.errorText.textContent = "Something went wrong. Please try again.";
  ui.errorText.dataset.source = "add-form";
  checkbox.checked = true;

  await toggleRead(ui, books, checkbox, fakeFetch(200, { ...book, read: true }).fetchFn);

  assert.equal(ui.errorText.hidden, false);
});

test("a successful toggle leaves the add form's message showing", async () => {
  const { books, book, checkbox, ui } = fakeToggle({ read: false, checked: true });
  ui.errorText.textContent = "title is required";
  ui.errorText.dataset.source = "add-form";
  ui.errorText.hidden = false;

  await toggleRead(ui, books, checkbox, fakeFetch(200, { ...book, read: true }).fetchFn);

  assert.equal(ui.errorText.textContent, "title is required");
  assert.equal(ui.errorText.hidden, false);
});

test("toggleRead un-mutes the card when a book is marked unread", async () => {
  const { books, book, card, checkbox, ui } = fakeToggle({ read: true, checked: false });

  await toggleRead(ui, books, checkbox, fakeFetch(200, { ...book, read: false }).fetchFn);

  assert.equal(book.read, false);
  assert.equal(card.className, "book-card");
  assert.equal(ui.readCount.textContent, "0 of 1 read");
});

test("toggleRead keeps the box disabled while the request is in flight", async () => {
  const { books, book, checkbox, ui } = fakeToggle({ read: false, checked: true });
  let disabledDuringRequest;
  const fetchFn = async () => {
    disabledDuringRequest = checkbox.disabled;
    return { status: 200, ok: true, json: async () => ({ ...book, read: true }) };
  };

  await toggleRead(ui, books, checkbox, fetchFn);

  assert.equal(disabledDuringRequest, true);
  assert.equal(checkbox.disabled, false);
});

test("toggleRead on an API error puts the box back and shows the API's message", async () => {
  const { books, book, card, checkbox, ui } = fakeToggle({ read: false, checked: true });

  await toggleRead(ui, books, checkbox, fakeFetch(404, { error: "book not found" }).fetchFn);

  assert.equal(checkbox.checked, false);
  assert.equal(checkbox.disabled, false);
  assert.equal(book.read, false);
  assert.equal(card.className, "book-card");
  assert.equal(ui.errorText.textContent, "book not found");
  assert.equal(ui.errorText.hidden, false);
});

test("toggleRead on a server error puts the box back and shows the general message", async () => {
  const { books, book, checkbox, ui } = fakeToggle({ read: true, checked: false });
  const logged = [];

  await toggleRead(ui, books, checkbox, fakeFetch(500, {}).fetchFn, (err) => logged.push(err));

  assert.equal(checkbox.checked, true);
  assert.equal(checkbox.disabled, false);
  assert.equal(book.read, true);
  assert.equal(ui.errorText.textContent, "Something went wrong. Please try again.");
  assert.equal(ui.errorText.hidden, false);
  assert.equal(logged.length, 1);
});

test("toggleRead when the request itself fails puts the box back and shows the general message", async () => {
  const { books, checkbox, ui } = fakeToggle({ read: false, checked: true });
  const offline = async () => {
    throw new TypeError("fetch failed");
  };

  await toggleRead(ui, books, checkbox, offline, () => {});

  assert.equal(checkbox.checked, false);
  assert.equal(ui.errorText.textContent, "Something went wrong. Please try again.");
});

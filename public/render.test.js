import { test } from "node:test";
import assert from "node:assert/strict";
import { renderBooks, renderReadCount } from "./render.js";

// Just enough of the DOM for renderBooks; the project has no browser test runner.
function fakeDocument() {
  const createElement = (tagName) => ({
    tagName: tagName.toUpperCase(),
    className: "",
    textContent: "",
    children: [],
    append(...nodes) {
      this.children.push(...nodes);
    },
    replaceChildren(...nodes) {
      this.children = nodes;
    },
  });
  return { createElement };
}

test("each book renders as a card with the title in bold and the author underneath", () => {
  const doc = fakeDocument();
  const list = doc.createElement("ul");
  renderBooks(
    list,
    [
      { id: 1, title: "Dune", author: "Frank Herbert" },
      { id: 2, title: "Emma", author: "Jane Austen" },
    ],
    doc,
  );

  assert.equal(list.children.length, 2);
  assert.deepEqual(
    list.children.map((c) => c.children[0].textContent),
    ["Dune", "Emma"],
  );
  const card = list.children[0];
  assert.equal(card.tagName, "LI");
  assert.equal(card.className, "book-card");
  const [title, author] = card.children;
  assert.equal(title.tagName, "STRONG");
  assert.equal(title.className, "book-title");
  assert.equal(title.textContent, "Dune");
  assert.equal(author.className, "book-author");
  assert.equal(author.textContent, "Frank Herbert");
});

test("an empty list shows 'No books yet'", () => {
  const doc = fakeDocument();
  const list = doc.createElement("ul");
  renderBooks(list, [], doc);

  assert.equal(list.children.length, 1);
  assert.equal(list.children[0].className, "empty");
  assert.equal(list.children[0].textContent, "No books yet");
});

test("each card has a 'Read' checkbox that shows the book's read field", () => {
  const doc = fakeDocument();
  const list = doc.createElement("ul");
  renderBooks(
    list,
    [
      { id: 1, title: "Dune", author: "Frank Herbert", read: true },
      { id: 2, title: "Emma", author: "Jane Austen", read: false },
    ],
    doc,
  );

  const [readCard, unreadCard] = list.children;
  const label = readCard.children[2];
  assert.equal(label.tagName, "LABEL");
  const [checkbox, text] = label.children;
  assert.equal(checkbox.tagName, "INPUT");
  assert.equal(checkbox.type, "checkbox");
  assert.equal(checkbox.checked, true);
  // The id is how the change handler finds the book.
  assert.equal(checkbox.value, "1");
  assert.equal(text, " Read");
  assert.equal(unreadCard.children[2].children[0].checked, false);
});

test("each checkbox's accessible name includes the book's title", () => {
  const doc = fakeDocument();
  const list = doc.createElement("ul");
  renderBooks(list, [{ id: 1, title: "Dune", author: "Frank Herbert", read: false }], doc);

  assert.equal(list.children[0].children[2].children[0].ariaLabel, "Read: Dune");
});

test("a book whose read change is still saving gets a disabled box showing the value being saved", () => {
  const doc = fakeDocument();
  const list = doc.createElement("ul");
  renderBooks(
    list,
    [
      { id: 1, title: "Dune", author: "Frank Herbert", read: false, pendingRead: true },
      { id: 2, title: "Emma", author: "Jane Austen", read: true, pendingRead: false },
      { id: 3, title: "Ulysses", author: "James Joyce", read: false },
    ],
    doc,
  );

  const boxes = list.children.map((c) => c.children[2].children[0]);
  assert.deepEqual(
    boxes.map((b) => [b.checked, b.disabled]),
    [
      [true, true],
      [false, true],
      [false, false],
    ],
  );
});

test("a read book's card is marked so it looks muted", () => {
  const doc = fakeDocument();
  const list = doc.createElement("ul");
  renderBooks(
    list,
    [
      { id: 1, title: "Dune", author: "Frank Herbert", read: true },
      { id: 2, title: "Emma", author: "Jane Austen", read: false },
    ],
    doc,
  );

  assert.deepEqual(
    list.children.map((c) => c.className),
    ["book-card read", "book-card"],
  );
});

test("the read count says how many of the books are read", () => {
  const count = { textContent: "", hidden: true };
  renderReadCount(count, [
    { id: 1, read: true },
    { id: 2, read: false },
    { id: 3, read: true },
    { id: 4, read: false },
    { id: 5, read: false },
  ]);

  assert.equal(count.textContent, "2 of 5 read");
  assert.equal(count.hidden, false);
});

test("the read count is hidden when there are no books", () => {
  const count = { textContent: "1 of 1 read", hidden: false };
  renderReadCount(count, []);

  assert.equal(count.hidden, true);
});

test("rendering replaces what the list showed before", () => {
  const doc = fakeDocument();
  const list = doc.createElement("ul");
  renderBooks(list, [], doc);
  renderBooks(list, [{ id: 1, title: "Dune", author: "Frank Herbert" }], doc);

  assert.equal(list.children.length, 1);
  assert.equal(list.children[0].className, "book-card");
});

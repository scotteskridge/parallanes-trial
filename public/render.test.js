import { test } from "node:test";
import assert from "node:assert/strict";
import { renderBooks } from "./render.js";

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

test("rendering replaces what the list showed before", () => {
  const doc = fakeDocument();
  const list = doc.createElement("ul");
  renderBooks(list, [], doc);
  renderBooks(list, [{ id: 1, title: "Dune", author: "Frank Herbert" }], doc);

  assert.equal(list.children.length, 1);
  assert.equal(list.children[0].className, "book-card");
});

import { test } from "node:test";
import assert from "node:assert/strict";
import { createApp } from "./app.js";

async function withServer(fn) {
  const server = createApp().listen(0);
  await new Promise((resolve) => server.once("listening", resolve));
  try {
    await fn(`http://127.0.0.1:${server.address().port}`);
  } finally {
    server.close();
  }
}

test("GET /api/books lists the books", async () => {
  await withServer(async (base) => {
    const res = await fetch(`${base}/api/books`);
    assert.equal(res.status, 200);
    const books = await res.json();
    assert.ok(books.length > 0);
    assert.ok(books.every((b) => b.id && b.title && b.author));
  });
});

function postBook(base, body) {
  return fetch(`${base}/api/books`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

test("POST /api/books adds a book and returns it with an id", async () => {
  await withServer(async (base) => {
    const res = await postBook(base, { title: "Refactoring", author: "Martin Fowler" });
    assert.equal(res.status, 201);
    const book = await res.json();
    assert.equal(book.title, "Refactoring");
    assert.equal(book.author, "Martin Fowler");
    assert.ok(Number.isInteger(book.id));

    const list = await (await fetch(`${base}/api/books`)).json();
    assert.deepEqual(list.at(-1), book);
    assert.equal(new Set(list.map((b) => b.id)).size, list.length);
  });
});

test("POST /api/books trims spaces around the title and author", async () => {
  await withServer(async (base) => {
    const res = await postBook(base, { title: "  Refactoring ", author: " Martin Fowler " });
    assert.equal(res.status, 201);
    const book = await res.json();
    assert.equal(book.title, "Refactoring");
    assert.equal(book.author, "Martin Fowler");
  });
});

test("POST /api/books refuses a request with no body with 400", async () => {
  await withServer(async (base) => {
    const res = await fetch(`${base}/api/books`, { method: "POST" });
    assert.equal(res.status, 400);
    const { error } = await res.json();
    assert.match(error, /title/);
  });
});

test("POST /api/books refuses a body that is not valid JSON with a JSON 400", async () => {
  await withServer(async (base) => {
    const res = await fetch(`${base}/api/books`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: '{"title": "x",',
    });
    assert.equal(res.status, 400);
    const { error } = await res.json();
    assert.match(error, /valid JSON/);
  });
});

for (const [name, body, field] of [
  ["missing title", { author: "Martin Fowler" }, "title"],
  ["blank title", { title: "   ", author: "Martin Fowler" }, "title"],
  ["missing author", { title: "Refactoring" }, "author"],
  ["blank author", { title: "Refactoring", author: "" }, "author"],
]) {
  test(`POST /api/books refuses a ${name} with 400`, async () => {
    await withServer(async (base) => {
      const before = (await (await fetch(`${base}/api/books`)).json()).length;
      const res = await postBook(base, body);
      assert.equal(res.status, 400);
      const { error } = await res.json();
      assert.match(error, new RegExp(field));

      const after = (await (await fetch(`${base}/api/books`)).json()).length;
      assert.equal(after, before);
    });
  });
}

test("GET /api/books starts every book as unread", async () => {
  await withServer(async (base) => {
    const books = await (await fetch(`${base}/api/books`)).json();
    assert.ok(books.every((b) => b.read === false));
  });
});

test("POST /api/books adds the new book as unread", async () => {
  await withServer(async (base) => {
    const book = await (await postBook(base, { title: "Refactoring", author: "Martin Fowler" })).json();
    assert.equal(book.read, false);
  });
});

function patchBook(base, id, body) {
  return fetch(`${base}/api/books/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

test("PATCH /api/books/:id marks a book as read and returns it", async () => {
  await withServer(async (base) => {
    const res = await patchBook(base, 1, { read: true });
    assert.equal(res.status, 200);
    const book = await res.json();
    assert.equal(book.id, 1);
    assert.equal(book.read, true);

    const list = await (await fetch(`${base}/api/books`)).json();
    assert.deepEqual(list.find((b) => b.id === 1), book);
  });
});

test("PATCH /api/books/:id marks a read book as unread again", async () => {
  await withServer(async (base) => {
    await patchBook(base, 1, { read: true });
    const res = await patchBook(base, 1, { read: false });
    assert.equal(res.status, 200);
    assert.equal((await res.json()).read, false);
  });
});

for (const id of ["999", "abc"]) {
  test(`PATCH /api/books/${id} refuses an unknown id with a JSON 404`, async () => {
    await withServer(async (base) => {
      const res = await patchBook(base, id, { read: true });
      assert.equal(res.status, 404);
      const { error } = await res.json();
      assert.match(error, /not found/);
    });
  });
}

for (const [name, body] of [
  ["missing read", {}],
  ["string read", { read: "true" }],
  ["numeric read", { read: 1 }],
  ["null read", { read: null }],
]) {
  test(`PATCH /api/books/:id refuses a ${name} with 400 and leaves the book alone`, async () => {
    await withServer(async (base) => {
      const res = await patchBook(base, 1, body);
      assert.equal(res.status, 400);
      const { error } = await res.json();
      assert.match(error, /read/);

      const list = await (await fetch(`${base}/api/books`)).json();
      assert.equal(list.find((b) => b.id === 1).read, false);
    });
  });
}

test("PATCH /api/books/:id refuses a request with no body with 400", async () => {
  await withServer(async (base) => {
    const res = await fetch(`${base}/api/books/1`, { method: "PATCH" });
    assert.equal(res.status, 400);
    const { error } = await res.json();
    assert.match(error, /read/);
  });
});

test("the front end is served", async () => {
  await withServer(async (base) => {
    const res = await fetch(`${base}/`);
    assert.equal(res.status, 200);
    assert.match(await res.text(), /Reading list/);
  });
});

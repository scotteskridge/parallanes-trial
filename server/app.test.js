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

test("the front end is served", async () => {
  await withServer(async (base) => {
    const res = await fetch(`${base}/`);
    assert.equal(res.status, 200);
    assert.match(await res.text(), /Reading list/);
  });
});

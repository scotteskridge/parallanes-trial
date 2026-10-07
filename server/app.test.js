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

test("the front end is served", async () => {
  await withServer(async (base) => {
    const res = await fetch(`${base}/`);
    assert.equal(res.status, 200);
    assert.match(await res.text(), /Reading list/);
  });
});

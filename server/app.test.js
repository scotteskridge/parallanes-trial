import { test, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createApp } from "./app.js";

// Every test gets its own file under one temp folder, so tests never touch data/books.json or
// each other's books.
const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), "reading-list-test-"));
after(() => fs.rmSync(tmpRoot, { recursive: true, force: true }));

let fileCount = 0;
function tempBooksFile() {
  fileCount += 1;
  return path.join(tmpRoot, `books-${fileCount}.json`);
}

async function withServer(fn, booksFile = tempBooksFile()) {
  const server = createApp({ booksFile }).listen(0);
  await new Promise((resolve) => server.once("listening", resolve));
  try {
    await fn(`http://127.0.0.1:${server.address().port}`);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
}

const startingTitles = ["The Pragmatic Programmer", "A Philosophy of Software Design"];

test("a missing books file is seeded with the two starting books", async () => {
  const booksFile = tempBooksFile();
  await withServer(async (base) => {
    const books = await (await fetch(`${base}/api/books`)).json();
    assert.deepEqual(books.map((b) => b.title), startingTitles);
  }, booksFile);
  const saved = JSON.parse(fs.readFileSync(booksFile, "utf8"));
  assert.deepEqual(saved.map((b) => b.title), startingTitles);
});

test("a missing folder for the books file is created", async () => {
  const booksFile = path.join(tmpRoot, "no-such-folder", "books.json");
  await withServer(async (base) => {
    assert.equal((await fetch(`${base}/api/books`)).status, 200);
  }, booksFile);
  assert.ok(fs.existsSync(booksFile));
});

test("an existing books file is loaded as it is", async () => {
  const booksFile = tempBooksFile();
  const stored = [{ id: 7, title: "Refactoring", author: "Martin Fowler", read: true }];
  fs.writeFileSync(booksFile, JSON.stringify(stored));
  await withServer(async (base) => {
    assert.deepEqual(await (await fetch(`${base}/api/books`)).json(), stored);
  }, booksFile);
});

test("a book added with POST is still there after a restart", async () => {
  const booksFile = tempBooksFile();
  let added;
  await withServer(async (base) => {
    added = await (await postBook(base, { title: "Refactoring", author: "Martin Fowler" })).json();
  }, booksFile);
  await withServer(async (base) => {
    const books = await (await fetch(`${base}/api/books`)).json();
    assert.deepEqual(books.at(-1), added);
  }, booksFile);
});

test("a book marked read with PATCH is still read after a restart", async () => {
  const booksFile = tempBooksFile();
  await withServer(async (base) => {
    assert.equal((await patchBook(base, 1, { read: true })).status, 200);
  }, booksFile);
  await withServer(async (base) => {
    const books = await (await fetch(`${base}/api/books`)).json();
    assert.equal(books.find((b) => b.id === 1).read, true);
  }, booksFile);
});

test("a refused request leaves the books file unchanged", async () => {
  const booksFile = tempBooksFile();
  await withServer(async (base) => {
    const before = fs.readFileSync(booksFile, "utf8");
    assert.equal((await postBook(base, { title: "" })).status, 400);
    assert.equal((await patchBook(base, 1, { read: "yes" })).status, 400);
    assert.equal(fs.readFileSync(booksFile, "utf8"), before);
  }, booksFile);
});

for (const [name, content] of [
  ["not valid JSON", '[{"id": 1,'],
  ["not a list", '{"books": []}'],
]) {
  test(`createApp refuses a books file that is ${name}, naming the file`, () => {
    const booksFile = tempBooksFile();
    fs.writeFileSync(booksFile, content);
    assert.throws(() => createApp({ booksFile }), (err) => err.message.includes(booksFile));
    // The bad file is left for a person to inspect, not overwritten with the seed.
    assert.equal(fs.readFileSync(booksFile, "utf8"), content);
  });
}

test("createApp refuses a books file it cannot read, naming the file", () => {
  // A folder where the file should be: reading it fails with EISDIR, which has no file name.
  const booksFile = path.join(tmpRoot, "a-folder-not-a-file");
  fs.mkdirSync(booksFile);
  assert.throws(() => createApp({ booksFile }), (err) => err.message.includes(booksFile));
});

// A folder where the temp file should go makes every save fail, whatever the platform.
function breakSaving(booksFile) {
  fs.mkdirSync(`${booksFile}.tmp`);
}

test("a POST whose save fails answers 500 and adds no book", async () => {
  const booksFile = tempBooksFile();
  await withServer(async (base) => {
    breakSaving(booksFile);
    const res = await postBook(base, { title: "Refactoring", author: "Martin Fowler" });
    assert.equal(res.status, 500);
    const books = await (await fetch(`${base}/api/books`)).json();
    assert.deepEqual(books.map((b) => b.title), startingTitles);
  }, booksFile);
});

test("a PATCH whose save fails answers 500 and leaves the book unread", async () => {
  const booksFile = tempBooksFile();
  await withServer(async (base) => {
    breakSaving(booksFile);
    assert.equal((await patchBook(base, 1, { read: true })).status, 500);
    const books = await (await fetch(`${base}/api/books`)).json();
    assert.equal(books.find((b) => b.id === 1).read, false);
  }, booksFile);
});

test("createApp refuses to start without a books file", () => {
  assert.throws(() => createApp(), /booksFile/);
});

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

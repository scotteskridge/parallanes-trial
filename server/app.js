// The API. Kept separate from index.js so tests can start it on a free port.
import express from "express";
import path from "node:path";
import { fileURLToPath } from "node:url";

const publicDir = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "public");

export function createApp() {
  const books = [
    { id: 1, title: "The Pragmatic Programmer", author: "Andrew Hunt and David Thomas" },
    { id: 2, title: "A Philosophy of Software Design", author: "John Ousterhout" },
  ];

  const app = express();
  app.use(express.json());
  app.use(express.static(publicDir));

  app.get("/api/books", (req, res) => {
    res.json(books);
  });

  app.post("/api/books", (req, res) => {
    // Express 5 leaves req.body undefined when the request has no JSON body.
    const { title, author } = req.body ?? {};
    for (const [field, value] of [["title", title], ["author", author]]) {
      if (typeof value !== "string" || value.trim() === "") {
        return res.status(400).json({ error: `${field} is required` });
      }
    }
    // Max + 1 rather than length + 1, which would collide with an existing id. Placeholder: an id
    // freed by deleting the newest book would be reused; revisit if deleting is added.
    const id = Math.max(0, ...books.map((b) => b.id)) + 1;
    const book = { id, title: title.trim(), author: author.trim() };
    books.push(book);
    res.status(201).json(book);
  });

  // express.json() rejects a malformed body before any route runs; without this the client gets
  // Express's HTML error page (with a stack trace outside production) instead of the JSON shape.
  // Any other error is passed on, not swallowed.
  app.use((err, req, res, next) => {
    if (err.type === "entity.parse.failed") {
      return res.status(400).json({ error: "body must be valid JSON" });
    }
    next(err);
  });

  return app;
}

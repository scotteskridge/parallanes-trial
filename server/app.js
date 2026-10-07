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

  return app;
}

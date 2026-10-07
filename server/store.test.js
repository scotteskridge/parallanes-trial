import { test } from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { resolveBooksFile } from "./store.js";

const projectRoot = path.resolve("project-root");

test("with no BOOKS_FILE the books file is data/books.json under the project root", () => {
  assert.equal(resolveBooksFile(undefined, projectRoot), path.join(projectRoot, "data", "books.json"));
});

test("an empty BOOKS_FILE counts as not set", () => {
  assert.equal(resolveBooksFile("", projectRoot), path.join(projectRoot, "data", "books.json"));
});

test("a relative BOOKS_FILE resolves against the project root, not the current folder", () => {
  assert.equal(resolveBooksFile("lists/mine.json", projectRoot), path.join(projectRoot, "lists", "mine.json"));
});

test("an absolute BOOKS_FILE is used as it is", () => {
  const absolute = path.resolve("elsewhere", "books.json");
  assert.equal(resolveBooksFile(absolute, projectRoot), absolute);
});

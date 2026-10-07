// The front end: plain modules, no build step.
import { renderBooks } from "./render.js";

const list = document.getElementById("books");

const res = await fetch("/api/books");
const books = await res.json();
renderBooks(list, books);

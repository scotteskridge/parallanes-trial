import path from "node:path";
import { fileURLToPath } from "node:url";
import { createApp } from "./app.js";
import { resolveBooksFile } from "./store.js";

// BOOKS_FILE points the books somewhere else; see resolveBooksFile for how paths resolve.
const projectRoot = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const booksFile = resolveBooksFile(process.env.BOOKS_FILE, projectRoot);

// PORT lets two lanes run their dev servers side by side.
const port = Number(process.env.PORT) || 3000;
createApp({ booksFile }).listen(port, () => {
  console.log(`reading-list on http://localhost:${port}, books in ${booksFile}`);
});

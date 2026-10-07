import { createApp } from "./app.js";

// PORT lets two lanes run their dev servers side by side.
const port = Number(process.env.PORT) || 3000;
createApp().listen(port, () => {
  console.log(`reading-list on http://localhost:${port}`);
});

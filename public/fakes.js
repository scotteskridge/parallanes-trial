// Shared test stand-ins. Named to match none of `node --test`'s default patterns (`*.test.js`,
// `test-*.js` and others), so it isn't loaded as a test file itself.

// Records the request and answers with a fixed status and JSON body; no real network.
export function fakeFetch(status, body) {
  const calls = [];
  const fetchFn = async (url, options) => {
    calls.push({ url, options });
    return { status, ok: status >= 200 && status < 300, json: async () => body };
  };
  return { fetchFn, calls };
}

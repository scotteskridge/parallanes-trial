---
# Loads when an agent reads or edits a test file.
paths:
  - "tests/**"
  - "test/**"
  - "**/test_*"
  - "**/*_test.*"
  - "**/*.test.*"
  - "**/*.spec.*"
---
# Tests

- A test asserts behaviour: a value, a state change, an error with its message. "Doesn't throw" is
  not a test on its own.
- For a bug, write the test that fails because of it first, run it, and watch it fail.
- Never delete, skip, loosen or comment out an existing test to get a change through. If a test is
  genuinely wrong, say why and ask before changing it.
- One behaviour per test; the name says what it proves (`test_refuses_negative_quantity`, not
  `test_quantity_2`).
- Reuse the existing fixtures and helpers; search before writing a new one.
- No sleeps, real network or real clocks in unit tests: inject them.
- Tests for impossible cases are over-engineering; don't add them.

# Code standards: worklanes-trial

What "good" means here, for people and agents alike. The reviewer checks changes against this file
and the numbered checklists in `.claude/review/`.
Stack-specific standards go in their own section at the end; path-specific ones go in
`.claude/rules/`.

## 1. Design and structure
- One clear job per module, class and function. If you need "and" to describe it, consider a split.
- Put new code next to the code it belongs with; search for an existing home before making one.
- Keep logic out of the edges (UI, HTTP handlers, CLI parsing): edges translate, the core decides.
- Prefer passing dependencies in over reaching for globals or singletons.
- Files past ~300 lines: suggest a split, don't do it unasked.

## 2. Errors
- Fail loudly on states that should be impossible: raise with a message that says what was
  expected and what was found.
- Never swallow an exception. Catch only what you can handle, and handle it.
- No silent fallbacks: if a default hides a bug, it's a bug.
- Validate at the boundaries (user input, files, network); trust data inside the core.

## 3. Tests
- New behaviour comes with tests; a bug fix comes with the test that would have caught it.
- Tests assert behaviour, are independent of each other, and are deterministic.
- Never weaken, skip or delete a test to make a change pass.

## 4. Naming and comments
- Names say what something is or does, in the project's own vocabulary (see `docs/design/`).
- Comments explain *why*, not what. Match the comment density of the surrounding code.
- No commented-out code; git remembers it.

## 5. Don't over-engineer
Over-engineering is a defect too. Don't add:
- abstractions with one implementation and no second one planned,
- configuration for things that never change,
- defensive checks or tests for cases that can't happen,
- hooks for features that aren't planned.

Build what the plan asks for, in the simplest form that keeps the code easy to change.

## 6. Review severities
Used by the reviewer and in code-health reports:
- 🔴 **Fix now:** a bug risk, a broken hard rule, a data-loss or security risk.
- 🟠 **Fix soon:** debt that will slow or break the next changes in that area.
- 🟡 **Polish:** worth doing while you're in the file anyway.

## 7. Stack-specific
<!-- Standards for this project's stack go here; /onboard proposes a first set. -->

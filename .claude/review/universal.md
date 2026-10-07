# Universal checks (prefix U)

Kit-owned: replaced when the kit updates. Add your own checks to `project.md` in this folder.
Each check names what to look for in the changed lines; the severities are in
`docs/CODE-STANDARDS.md` §6. Cite the ID in every finding.

U1. **Scope.** The change does what the plan or task asks, and nothing else. Unrelated edits,
    drive-by refactors and "while I was here" changes are findings, even when they are good.
U2. **Tests for behaviour.** New behaviour comes with tests; a bug fix comes with the test that would
    have caught it. Tests assert behaviour, not implementation details, and don't depend on each
    other or on timing.
U3. **No weakened tests.** No test deleted, skipped, loosened (fewer assertions, wider tolerances,
    broader exception types) or marked as expected to fail to make a change pass. Always 🔴 unless
    the plan says why.
U4. **Errors are loud.** No swallowed exceptions, no silent fallbacks that hide a bug, no
    `except: pass`. Impossible states fail with a message that says what was expected and found.
U5. **Correctness.** Logic errors, wrong conditions, off-by-one, missing cases at the edges (empty,
    missing, duplicate, very large, non-ASCII, paths with spaces). Trace the code path; say how the
    bug shows, with the input that triggers it.
U6. **Security and secrets.** No keys, tokens or `.env` contents in the diff. Input from outside
    (users, files, network, environment) is validated where it enters; nothing from it reaches a
    shell, query or file path unescaped.
U7. **Reuse.** The change doesn't duplicate something that already exists in the project. Name the
    existing function or file when it does.
U8. **Not over-engineered.** Over-engineering is a defect too: abstractions with one implementation
    and no second planned, configuration for things that never change, defensive code for cases
    that can't happen, hooks for features nobody asked for.
U9. **Project rules.** `AGENTS.md`, `docs/CODE-STANDARDS.md` and every `.claude/rules/` file whose
    `paths:` match a changed file. Quote the rule a finding breaks.
U10. **Guarded areas.** Changes to protected paths (`[protected]` in `.claude/kit.toml`), CI
    workflows, `.claude/settings.json`, hooks or the kit's own files are named for the owner, even
    when they look right.
U11. **Dependencies.** No new dependency unless the plan asked for it; when one is added, it is the
    project's usual kind, declared where the project declares dependencies.
U12. **Names and comments.** Names say what a thing is in the project's own vocabulary. Comments say
    why, not what. No commented-out code, leftover debug output, or TODO without an owner.
U13. **Size and shape.** A file pushed past ~300 lines, or a function doing several jobs: suggest a
    split. A suggestion, not a demand (🟡, or 🟠 when the file is already hard to change).
U14. **Docs follow behaviour.** A change people or agents will notice updates the docs that describe
    it and adds a changelog fragment; a design decision is recorded in the decisions log.
U15. **Undecided design.** A design question the plan didn't settle, settled silently in the code.
    Report it as "needs the owner" with the options you see; don't pick one.

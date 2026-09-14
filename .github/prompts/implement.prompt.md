---
description: "Implement a refined story with TDD. Use when building a planned feature: tests first, then code, then docs, ending with how to test-drive it."
agent: agent
tools: [read, edit, execute, search]
---

Implement phase of the flow. Build one story end to end, following the fixed flow and
Definition of Done in `.github/copilot-instructions.md`.

1. Read the story and its Definition of Done. Restate what "done" means here.
2. Draft a short execution plan (files to change, edge cases, steps) and confirm it for
   anything non-trivial.
3. **Tests first (TDD)**: write a failing test for the next behaviour using
   GIVEN / WHEN / THEN. Run it and confirm it fails for the right reason.
4. Write the minimum code to pass, in small reviewable increments.
5. Run the gate until green: `tara check` (lint, format, types, tests, security).
6. Update docs and the runnable example for the new behaviour; update the changelog if
   it is user-facing.
7. Finish with clear **test-drive instructions**: the exact commands or example a
   developer runs to see the new feature work.

Work on a `<type>/<short-description>` branch (e.g. `feat/add-auth`). Never commit or
push: stage the change, draft the commit message (imperative mood, subject <= 72 chars),
and hand off to the developer.

Finally, note the hand-off in `.agents/memory/` and keep its `index.md` current so
the next session can continue.

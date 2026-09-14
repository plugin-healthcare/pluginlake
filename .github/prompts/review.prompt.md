---
description: "Review code for correctness, clarity, and conventions. Use on a file, function, or diff after implementing, before integrating."
agent: agent
tools: [read, search]
---

Review phase of the flow. Give structured feedback against the story's acceptance
criteria, Definition of Done, and any ADRs it references, plus the fixed flow in
`.github/copilot-instructions.md`.

**Correctness**: bugs, edge cases, error handling gaps
**Clarity**: naming, complexity, readability; clear over clever
**Conventions**: follows the project instructions, layout, and design principles
**Tests**: behaviour covered once, tests independent, the gate would pass
**Docs**: docs, runnable example, and changelog updated for the change
**Security**: secrets not committed, plus any obvious OWASP Top 10 concerns

Format as a prioritised list: `[blocker]`, `[suggestion]`, `[nit]`.
End with a one-line verdict: is the Definition of Done met, or what is missing.

Finally, file your review as `.agents/review/YYYYMMDDHHMM_<short-descriptive-title>.md`,
add a row to
`.agents/review/index.md`, and note the hand-off in `.agents/memory/`.

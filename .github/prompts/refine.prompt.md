---
description: "Refine work into epics and user stories. Use to turn a goal or feature into functional epics and technical stories with acceptance criteria and a Definition of Done."
agent: agent
tools: [read, search, edit]
---

Refine phase of the flow. Turn a goal or feature into agile work items following the
`writing-epics-stories` skill.

1. Clarify the functional goal and who it is for. Ask if it is ambiguous.
2. Write or update the **epic** as a functional requirement that delivers a reviewable,
   testable increment and a clear sprint goal (`tara new epic "<title>"`). The epic
   describes *what* and *why*, not *how*.
3. Break the epic into **technical user stories** (`tara new story "<title>"`): each
   small, independently deliverable, with acceptance criteria, tasks, and a Definition
   of Done that matches `.github/copilot-instructions.md`.
4. Note dependencies and sequencing between stories.
5. When these map to GitHub issues or a PR, create or update them to match.

Keep items short and functional. Do not start implementing here.

Finally, note the hand-off in `.agents/memory/` and keep its `index.md` current so
the next session can continue.

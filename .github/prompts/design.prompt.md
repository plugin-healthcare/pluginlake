---
description: "Design a solution before building it. Use for architecture decisions, research or spikes, and modelling the system. Produces ADRs plus LikeC4 or Mermaid diagrams."
agent: agent
tools: [read, search, edit]
---

Design phase of the flow. Decide *how* to build something before writing feature code.

1. Restate the problem and the constraints in one or two sentences.
2. Research first: read the existing code, then official docs. Note what already exists
   and must not be reinvented.
3. Lay out the realistic options with their trade-offs (cost, risk, fit with the
   composable-stack principles and current architecture).
4. Choose the software that best fits the task, as long as it fits the stack. When two
   options are roughly equal, prefer a tool already in use over adding a new one.
   Recommend one option and justify it.
5. Record the decision as an ADR (`tara new adr "<title>"`), following the
   `writing-adrs` skill: MADR-minimal plus the house Status/Date/Authors block and
   optional Architecture and Rollout sections.
6. When structure needs a picture: use LikeC4 for elaborate architecture overviews, and
   Mermaid for the small diagrams that support ADRs and docs. Prefer a diagram over prose.

Do not write feature code in this phase. Output the decision and diagrams, and stop.

Finally, note the hand-off in `.agents/memory/` and keep its `index.md` current so
the next session can continue.

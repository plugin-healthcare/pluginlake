---
name: writing-epics-stories
description: "Use when defining or refining product work: turning a feature idea into an epic, breaking an epic into user stories, or refining stories into technical tasks with acceptance criteria and a Definition of Done. Also use when creating or updating GitHub issues and pull requests for that work."
---

# Writing epics and stories

Define product work the agile way: an epic is the functional requirement, stories
are the deliverable increments, tasks are the technical steps. Keep epics about
*what and why*, stories about *user value*, tasks about *how*.

## Flow

1. **Epic** first. Scaffold it: `tara new epic "<title>"` (writes
   `docs/epics/<slug>.md`). Fill the goal, background, in/out of scope, success
   metrics, dependencies, and open questions. An epic is a functional description
   that produces a deliverable increment and a sprint goal, not a technical plan.
2. **Stories** next. For each unit of user value: `tara new story "<title>"`
   (writes `docs/stories/<slug>.md`). Link it back to the epic.
3. **Refine** stories into tasks. Add the technical steps, requirements, and a
   Definition of Done. Split a story if it is too big to finish in one increment.

## Writing a good epic

- One-sentence goal: what outcome, for whom.
- Scope is explicit. State what is out of scope, not just what is in.
- Success metrics have a baseline and a target, so "done" is measurable.

## Writing a good story

- `As a <role>, I want <goal>, so that <benefit>.` If you cannot name the benefit,
  the story is not ready.
- Acceptance criteria in GIVEN / WHEN / THEN form, testable and unambiguous.
- Definition of Done covers code review, tests passing, docs, and stakeholder
  verification. Match it to the project's DoD.

## GitHub issues and pull requests

Use the `github` MCP to create and update the corresponding issues and PRs:

- Open an issue per epic and per story; use the epic issue to track its children.
- Mirror the template content into the issue body so the source of truth is one
  place, not two.
- Reference the story issue from the pull request that implements it.

Never commit or push; the developer reviews and commits. You draft the issues, the
stories, and the PR descriptions.

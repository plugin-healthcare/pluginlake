---
description: "Prepare a feature to merge into main. Use before opening or merging a PR: check fit with the codebase, standards, structure, wiring, and changelog and version bump."
agent: agent
tools: [read, search, execute]
---

Integrate phase of the flow. Check that a finished feature is ready to merge into `main`
under GitHub flow (`main` <- feature branch, hotfix straight off `main`).

1. **Fit**: does the change match the overall architecture and direction (relevant ADRs)?
   Flag anything that pulls the project off course.
2. **Standards and structure**: it follows repo rules, coding standards, and the project
   layout in `.github/copilot-instructions.md` and scoped instructions.
3. **Wiring**: the feature is actually connected: entry points, config, and call sites
   are in place. No dead, duplicated, or orphaned code.
4. **Gate**: `tara check` passes (lint, format, types, tests, security) and the
   Definition of Done is met. Flag flaky tests; don't re-run until they pass by luck.
5. **Versioning**: bump the version per semver (x.y.z: major breaks, minor adds, patch
   fixes; docs-only changes do not bump) and update the changelog, using the
   `release-semver-changelog` skill.
6. Draft the PR description: what changed, why, and how to test it.

Never merge, commit, or push. Report readiness and hand off to the developer.

Finally, note the hand-off in `.agents/memory/` and keep its `index.md` current so
the next session can continue.

# Copilot Instructions for pluginlake

All coding conventions and project rules are defined in [AGENTS.md](../AGENTS.md) at the repository root.
This file extends those instructions with GitHub Copilot-specific configuration.

## GitHub issues & project boards

- Use the `github-issues` skill (`.github/skills/github-issues/SKILL.md`) when creating epics, stories, or populating project boards.
- Always discover project field IDs dynamically via `gh project field-list`; never hardcode them.
- Use the `gh` CLI and `gh-sub-issue` extension for parent/child linking.

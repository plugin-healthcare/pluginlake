---
name: github-issues
description: "Create GitHub issues for epics and stories, link parent/child relationships, set project board fields (Story Level, Product/Feature, Status, Priority). Use when: creating epics, creating stories, populating project board, bulk issue creation, setting up initiative hierarchy, setting project labels/fields."
argument-hint: "Describe what epics/stories to create, which project to use, or point to the spec file"
---

# GitHub Issues: Epics, Stories & Project Boards

Create and manage GitHub issues with epic/story hierarchy, parent-child linking, and project board field management using the `gh` CLI.

## When to Use

- Creating epics and stories from a markdown specification
- Bulk-creating issues and linking them in a parent/child hierarchy
- Setting project board fields (Story Level, Product/Feature, Status, Priority, Story Points)
- Populating a new initiative with epics and stories
- Adding labels or project metadata to existing issues

## Prerequisites

- `gh` CLI authenticated (`gh auth status` to verify)
- `gh-sub-issue` extension installed (`gh extension install github/gh-sub-issue`)
- Know the repo owner and name
- Know the org project number (visible in the project URL)

## Step 0: Discover project metadata

Before creating issues, discover the project ID, field IDs, and option IDs. **Never hardcode these; always discover them first.**

```bash
# Set your target
OWNER="<org-or-user>"

# Find the project node ID and number
gh project list --owner "$OWNER" --format json | jq '.projects[] | {number, title, id}'

# List all fields, their IDs, types, and options
gh project field-list <PROJECT_NUMBER> --owner "$OWNER" --format json | jq '.fields[] | {name, id, type, options}'
```

Save the output so you can reference field IDs and option IDs throughout the process. See [references/project-fields.md](./references/project-fields.md) for a concrete example.

## Procedure

### 1. Create epic issues

Create each epic as a GitHub issue. Use the epic title as issue title, the scope/requirements as body.

**Important:**
- Remove links to internal-only documents that are not published on GitHub
- Cross-references to other epics/stories (like "E2" or "S3.5") should use `#<issue-number>` format once the issues exist
- Create all epics first, note the numbers, then create stories with correct `#number` references

```bash
gh issue create \
  --repo "$OWNER/$REPO" \
  --title "E1: Epic title here" \
  --body "## Omschrijving
...epic body..."
```

### 2. Link epics to initiative (parent-child)

```bash
gh sub-issue add <INITIATIVE_NUMBER> --issue-number <EPIC_NUMBER> --repo "$OWNER/$REPO"
```

### 3. Create story issues

Create each story as a GitHub issue. Include Omschrijving, Acceptance Criteria, Technische specificaties (if present), and Definition of Done.

Replace epic/story references in the body with `#<number>` links.

```bash
gh issue create \
  --repo "$OWNER/$REPO" \
  --title "S1.1 – Story title here" \
  --body "### Omschrijving
...story body..."
```

### 4. Link stories to parent epics

```bash
gh sub-issue add <EPIC_NUMBER> --issue-number <STORY_NUMBER> --repo "$OWNER/$REPO"
```

### 5. Add issues to project and set fields

```bash
# Add issue to project (returns item ID needed for field edits)
ITEM_ID=$(gh project item-add <PROJECT_NUMBER> \
  --owner "$OWNER" \
  --url "https://github.com/$OWNER/$REPO/issues/<NUMBER>" \
  --format json | jq -r '.id')

# Set a single-select field (e.g. Story Level, Status, Priority, Product/Feature)
gh project item-edit \
  --project-id "<PROJECT_NODE_ID>" \
  --id "$ITEM_ID" \
  --field-id "<FIELD_ID>" \
  --single-select-option-id "<OPTION_ID>"

# Set a number field (e.g. Story Points)
gh project item-edit \
  --project-id "<PROJECT_NODE_ID>" \
  --id "$ITEM_ID" \
  --field-id "<FIELD_ID>" \
  --number 5
```

### 6. Batch creation with the template script

For bulk creation, use the template script at [scripts/create-issues.sh](./scripts/create-issues.sh).

The script reads all configuration from environment variables, so no values need to be hardcoded. Set them before running:

```bash
export GH_OWNER="my-org"
export GH_REPO="my-repo"
export GH_PROJECT_NUMBER="4"
export GH_PROJECT_NODE_ID="PVT_kw..."
export GH_INITIATIVE="71"  # or "" to skip

# Discover these with Step 0 above
export GH_FIELD_STORY_LEVEL="PVTSSF_..."
export GH_OPTION_STORY_LEVEL_EPIC="abc123"
export GH_OPTION_STORY_LEVEL_STORY="def456"

# Optional fields (leave empty to skip)
export GH_FIELD_PRODUCT=""
export GH_OPTION_PRODUCT=""
export GH_FIELD_STATUS=""
export GH_OPTION_STATUS=""

bash create-issues.sh
```

The script pattern:
1. Declare all issues in arrays (`EPIC_TITLES`, `EPIC_BODIES`, `STORY_TITLES`, `STORY_BODIES`, `STORY_EPIC_INDEX`)
2. Phase 1: Create epics, capture issue numbers
3. Phase 2: Link epics to initiative
4. Phase 3: Create stories
5. Phase 4: Link stories to parent epics
6. Phase 5: Add to project and set fields

**Tips:**
- The script is idempotent: re-running skips issues that already exist (by title match)
- Add `sleep 0.5` between API calls to avoid rate limits
- If `gh sub-issue add` fails, it retries silently; the operation is idempotent

## Issue Body Templates

### Epic

```markdown
## Omschrijving

Als [actor] willen we [capability], zodat [benefit].

> *Dependencies/context note if needed. Reference parent initiative or prerequisite epics by #number.*

## Scope

**Wel:**
- Item 1
- Item 2

**Niet:**
- Out of scope item (dat is #<epic-number>)

## Requirements

- Requirement 1
- Requirement 2
```

### Story (with acceptance criteria)

```markdown
### Omschrijving

[Who] moet [what] kunnen [action], zodat [benefit].

### Acceptance Criteria

- [ ] Criterium 1
- [ ] Criterium 2

### Technische specificaties

> Only include when there are non-obvious technical decisions or patterns to document.
> Keep it brief: describe the approach, not the implementation.

**Section title:**
Description of the technical approach.

### Definition of Done

- [ ] Code is geschreven
- [ ] Error handling en logging zijn geïmplementeerd
- [ ] Code styling en linting zijn correct
- [ ] Tests zijn geïmplementeerd en succesvol
- [ ] Documentatie is bijgewerkt
- [ ] Lokale test run is succesvol
- [ ] Container test run is succesvol
- [ ] Review is uitgevoerd en PR is geaccepteerd
```

### Future epic (no stories yet)

```markdown
## Omschrijving

Als [actor] willen we [capability], zodat [benefit].

> *Dependency note. Reference prerequisite epics by #number.*

## Scope (contouren, stories worden later uitgewerkt)

**Topic 1:**
- Bullet 1
- Bullet 2

**Topic 2:**
- Bullet 1
- Bullet 2
```

## Common Operations

### Verify created issues
```bash
gh issue list --repo "$OWNER/$REPO" --limit 100 --json number,title,state | jq '.[] | "\(.number) \(.title)"'
```

### Check sub-issue links
```bash
gh sub-issue list <PARENT_NUMBER> --repo "$OWNER/$REPO"
```

### Bulk-set a field on multiple issues
```bash
for NUM in 72 73 74 75; do
  ITEM_ID=$(gh project item-add <PROJECT_NUMBER> \
    --owner "$OWNER" \
    --url "https://github.com/$OWNER/$REPO/issues/$NUM" \
    --format json 2>/dev/null | jq -r '.id')
  if [[ -n "$ITEM_ID" && "$ITEM_ID" != "null" ]]; then
    gh project item-edit \
      --project-id "<PROJECT_NODE_ID>" \
      --id "$ITEM_ID" \
      --field-id "<FIELD_ID>" \
      --single-select-option-id "<OPTION_ID>"
  fi
  sleep 0.3
done
```

### Add a repo label to issues
```bash
# Create the label if it doesn't exist
gh label create "epic" --repo OWNER/REPO --color "0E8A16" --description "Epic-level issue" 2>/dev/null

# Apply to issues
for NUM in 72 73 74; do
  gh issue edit $NUM --repo OWNER/REPO --add-label "epic"
done
```

## Tips

- Create all epics first, then all stories, then link everything. This avoids needing to know issue numbers upfront.
- The `gh sub-issue add` command can fail on rate limits; add `sleep 0.5` and retry failures.
- Project item IDs are different from issue numbers. You always need the item ID to set project fields.
- Use `--format json | jq` to extract IDs programmatically. Never hardcode IDs across repos.
- For a new project, always run the discovery step first (Step 0) and save the field reference.

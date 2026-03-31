#!/usr/bin/env bash
# Template script for bulk-creating GitHub issues with hierarchy.
#
# Usage:
#   1. Copy this script to your working directory.
#   2. Set the required environment variables (see below).
#   3. Fill in the EPIC and STORY arrays.
#   4. Run: bash create-issues.sh
#
# Environment variables (all required unless noted):
#   GH_OWNER            - GitHub org or user (e.g. "my-org")
#   GH_REPO             - Repository name (e.g. "my-repo")
#   GH_PROJECT_NUMBER   - Org project number (e.g. "4")
#   GH_PROJECT_NODE_ID  - Project node ID (from discovery, e.g. "PVT_kw...")
#   GH_INITIATIVE       - Parent issue number for epics (optional, "" to skip)
#   GH_FIELD_STORY_LEVEL      - Story Level field ID
#   GH_OPTION_STORY_LEVEL_EPIC  - Story Level "Epic" option ID
#   GH_OPTION_STORY_LEVEL_STORY - Story Level "Story" option ID
#   GH_FIELD_PRODUCT    - Product/Feature field ID (optional, "" to skip)
#   GH_OPTION_PRODUCT   - Product/Feature option ID (optional)
#   GH_FIELD_STATUS     - Status field ID (optional, "" to skip)
#   GH_OPTION_STATUS    - Default status option ID (e.g. Backlog)
#
# Discover these values with:
#   gh project list --owner $GH_OWNER --format json | jq '.projects[] | {number, title, id}'
#   gh project field-list $GH_PROJECT_NUMBER --owner $GH_OWNER --format json | jq '.fields[] | {name, id, type, options}'
#
# The script is idempotent: re-running skips already-created issues (by title match).
set -euo pipefail

# ── Configuration (from environment) ──────────────────────────────────
OWNER="${GH_OWNER:?Set GH_OWNER}"
REPO="${GH_REPO:?Set GH_REPO}"
PROJECT_NUMBER="${GH_PROJECT_NUMBER:?Set GH_PROJECT_NUMBER}"
PROJECT_NODE_ID="${GH_PROJECT_NODE_ID:?Set GH_PROJECT_NODE_ID}"
INITIATIVE_NUMBER="${GH_INITIATIVE:-}"

STORY_LEVEL_FIELD="${GH_FIELD_STORY_LEVEL:?Set GH_FIELD_STORY_LEVEL}"
STORY_LEVEL_EPIC="${GH_OPTION_STORY_LEVEL_EPIC:?Set GH_OPTION_STORY_LEVEL_EPIC}"
STORY_LEVEL_STORY="${GH_OPTION_STORY_LEVEL_STORY:?Set GH_OPTION_STORY_LEVEL_STORY}"

PRODUCT_FIELD="${GH_FIELD_PRODUCT:-}"
PRODUCT_VALUE="${GH_OPTION_PRODUCT:-}"

STATUS_FIELD="${GH_FIELD_STATUS:-}"
STATUS_BACKLOG="${GH_OPTION_STATUS:-}"

# ── Helpers ───────────────────────────────────────────────────────────
create_issue() {
  local title="$1"
  local body="$2"
  # Check if issue already exists
  local existing
  existing=$(gh issue list --repo "$OWNER/$REPO" --search "\"$title\" in:title" --json number --limit 1 | jq -r '.[0].number // empty')
  if [[ -n "$existing" ]]; then
    echo "  ⏭  Already exists: #$existing - $title"
    echo "$existing"
    return
  fi
  local num
  num=$(gh issue create --repo "$OWNER/$REPO" --title "$title" --body "$body" 2>&1 | grep -oP '\d+$')
  echo "  ✅ Created: #$num - $title" >&2
  echo "$num"
  sleep 0.5
}

link_sub_issue() {
  local parent="$1"
  local child="$2"
  gh sub-issue add "$parent" --issue-number "$child" --repo "$OWNER/$REPO" 2>/dev/null || true
  sleep 0.3
}

add_to_project_and_set_fields() {
  local issue_num="$1"
  local story_level_option="$2"  # epic or story option ID

  local item_id
  item_id=$(gh project item-add "$PROJECT_NUMBER" \
    --owner "$OWNER" \
    --url "https://github.com/$OWNER/$REPO/issues/$issue_num" \
    --format json 2>/dev/null | jq -r '.id') || return 0

  if [[ -z "$item_id" || "$item_id" == "null" ]]; then
    echo "  ⚠️  Could not add #$issue_num to project"
    return 0
  fi

  # Story Level
  gh project item-edit --project-id "$PROJECT_NODE_ID" --id "$item_id" \
    --field-id "$STORY_LEVEL_FIELD" --single-select-option-id "$story_level_option" 2>/dev/null || true

  # Product/Feature (if configured)
  if [[ -n "$PRODUCT_FIELD" && -n "$PRODUCT_VALUE" ]]; then
    gh project item-edit --project-id "$PROJECT_NODE_ID" --id "$item_id" \
      --field-id "$PRODUCT_FIELD" --single-select-option-id "$PRODUCT_VALUE" 2>/dev/null || true
  fi

  # Status (if configured)
  if [[ -n "$STATUS_FIELD" && -n "$STATUS_BACKLOG" ]]; then
    gh project item-edit --project-id "$PROJECT_NODE_ID" --id "$item_id" \
      --field-id "$STATUS_FIELD" --single-select-option-id "$STATUS_BACKLOG" 2>/dev/null || true
  fi

  sleep 0.3
}

# ── Define Epics ──────────────────────────────────────────────────────
# Each epic: EPIC_TITLES[i] and EPIC_BODIES[i]
EPIC_TITLES=()
EPIC_BODIES=()

# Example:
# EPIC_TITLES+=("E1: My first epic")
# EPIC_BODIES+=("## Omschrijving
#
# Als [actor] willen we [what], zodat [why].
#
# ## Scope
#
# **Wel:**
# - Item 1
#
# **Niet:**
# - Out of scope
#
# ## Requirements
#
# - Requirement 1")

# ── Define Stories ────────────────────────────────────────────────────
# Each story: STORY_TITLES[i], STORY_BODIES[i], STORY_EPIC_INDEX[i] (0-based index into EPIC_TITLES)
STORY_TITLES=()
STORY_BODIES=()
STORY_EPIC_INDEX=()

# Example:
# STORY_TITLES+=("S1.1 – My first story")
# STORY_BODIES+=("### Omschrijving
#
# [Who] moet [what], zodat [why].
#
# ### Acceptance Criteria
#
# - [ ] Criterium 1
#
# ### Definition of Done
#
# - [ ] Code is geschreven
# - [ ] Tests zijn geïmplementeerd en succesvol")
# STORY_EPIC_INDEX+=(0)  # belongs to EPIC_TITLES[0]

# ── Phase 1: Create Epics ────────────────────────────────────────────
echo "=== Creating Epics ==="
EPIC_NUMBERS=()
for i in "${!EPIC_TITLES[@]}"; do
  num=$(create_issue "${EPIC_TITLES[$i]}" "${EPIC_BODIES[$i]}")
  EPIC_NUMBERS+=("$num")
done

# ── Phase 2: Link Epics to Initiative ────────────────────────────────
if [[ -n "$INITIATIVE_NUMBER" ]]; then
  echo ""
  echo "=== Linking Epics to Initiative #$INITIATIVE_NUMBER ==="
  for num in "${EPIC_NUMBERS[@]}"; do
    echo "  🔗 Linking #$num → #$INITIATIVE_NUMBER"
    link_sub_issue "$INITIATIVE_NUMBER" "$num"
  done
fi

# ── Phase 3: Create Stories ───────────────────────────────────────────
echo ""
echo "=== Creating Stories ==="
STORY_NUMBERS=()
for i in "${!STORY_TITLES[@]}"; do
  # Replace epic references in body with actual issue numbers
  body="${STORY_BODIES[$i]}"
  num=$(create_issue "${STORY_TITLES[$i]}" "$body")
  STORY_NUMBERS+=("$num")
done

# ── Phase 4: Link Stories to Epics ────────────────────────────────────
echo ""
echo "=== Linking Stories to Epics ==="
for i in "${!STORY_NUMBERS[@]}"; do
  epic_idx="${STORY_EPIC_INDEX[$i]}"
  epic_num="${EPIC_NUMBERS[$epic_idx]}"
  echo "  🔗 Linking #${STORY_NUMBERS[$i]} → Epic #$epic_num"
  link_sub_issue "$epic_num" "${STORY_NUMBERS[$i]}"
done

# ── Phase 5: Add to Project & Set Fields ──────────────────────────────
echo ""
echo "=== Adding to Project & Setting Fields ==="
for num in "${EPIC_NUMBERS[@]}"; do
  echo "  📋 Epic #$num → Project"
  add_to_project_and_set_fields "$num" "$STORY_LEVEL_EPIC"
done
for num in "${STORY_NUMBERS[@]}"; do
  echo "  📋 Story #$num → Project"
  add_to_project_and_set_fields "$num" "$STORY_LEVEL_STORY"
done

# ── Summary ───────────────────────────────────────────────────────────
echo ""
echo "=== Done ==="
echo "Epics: ${EPIC_NUMBERS[*]}"
echo "Stories: ${STORY_NUMBERS[*]}"
echo ""
echo "Verify: gh issue list --repo $OWNER/$REPO --limit 100 --json number,title"

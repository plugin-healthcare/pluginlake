# Session Handoff

This document tracks the current state of work across Copilot sessions.
Each session must update this file before completing.

## Current State

**Branch:** `docker-deploy-cli`
**Status:** In progress — ADR cross-consistency fixes complete, ready to commit docs changes
**Last updated:** 2026-06-03

## What Was Done

### This session (2026-06-03, continued)

- Added foundational glossary to ADR-008 (DID, VC, VP, signature, OIDC, Nuts, DSP, ODRL, contract, DPoP, Bolt, Permission) with "how they relate" paragraph explaining contract → VC → permission hierarchy.
- Fixed cross-ADR inconsistencies:
  - ADR-003: clarified rejected "landing zone" alternative (decoupled polling vs direct trigger).
  - ADR-006: reconciled deployment contradiction (separate in production, colocation dev/test only).
  - ADR-006: defined boundary-2 role mechanism (`role` claim in `NutsOrganizationCredential`, station policy validates `role: hub`).
- Confirmed data flow pattern: write path always through Dagster; read/serve path is FastAPI → DuckLake directly.
- Confirmed DuckDB/DuckLake/Quack stack stays; Quack not yet relevant (Dagster still needs Postgres).

### This session (2026-06-03, earlier)

- Restructured documentation into proper ADR + Background pattern:
  - **ADR-008** slimmed from ~680 lines → 216 lines (context, decision, consequences, open questions only).
  - **`docs/background/dsp-authorization.md`** created: design spec extracted from ADR-008 (routes, schemas, state machines, RBAC, enforcement, phased delivery).
  - **`docs/background/federated-infrastructure.md`** created: final published version of platform comparison with balanced vantage6 framing.
  - **`docs/background/index.md`** created: landing page for the Background section.
- Added "Background" nav section to `zensical.toml`; added ADR-006/007 to Decisions nav.
- Removed `docs/reference/federated-infrastructure.md` and `docs/reference/federated-infrastructure-v2.md` (consolidated).
- ADR-008 clarity fixes: trust boundary definitions in terminology, EHDS/TEHDAS2 links, hub/station distinction, undefined terms explained (Bolt, TCK, StatusList2021, ODRL Level 2), two-auth-layer mechanism documented.
- Vantage6 tone: reframed limitations as scale-dependent trade-offs, acknowledged current production use via pluginml.

### Previous session (2026-06-02)

- Split ADR-008 into two files for easier review and commit:
  - `adr-008-dataspace-protocol-authz-authc-rbac.md` (685 lines, 30KB): concise decision record with all architecture, enforcement, phased delivery, and implementation-ready content.
  - `adr-008-dataspace-protocol-authz-authc-rbac-reference.md` (1634 lines, 83KB): full reference with detailed options analysis, dashboard UX workflows, RBAC entity model, and international standards appendix.
- Cross-linked both files in both directions.
- Updated `docs/decisions/README.md` to include ADR-006 and ADR-008 entries.

### Previous session (2026-05-28)

- Thoroughly reviewed ADR-008 (dataspace protocol architecture) as senior architect.
- Iteratively refined architecture through discussion: OPA → VC-native ODRL, station-authoritative model.
- Major structural cleanup of ADR-008: removed 160 lines of OPA content, rewrote workflows/governance/RBAC sections for internal consistency.
- Independent model review (rubber-duck agent): addressed 2 blocking + 5 non-blocking findings.
- Added TL;DR, terminology table, ADR-008 forward references, v1 scope clarification.
- **Split ADR-006 and ADR-008 into clean separation of concerns:**
  - ADR-006 (366 lines): Nuts Node integration — organizational identity, sidecar deployment, middleware, DID model, federation topologies, SDC safety, Bolt definition, researcher identity scoping.
  - ADR-008 (1632 lines): DSP + authorization — contract negotiation, per-user VCs with ODRL, enforcement, RBAC, governance models.
  - Cross-references between both ADRs.
- Clarified researcher identity model: "A researcher's identity is scoped to a processing hub. Each hub issues its own independent credentials and permits."

### Previous session

- Rebuilt Docker deployment architecture (separate webserver, daemon, code-server).
- Created `pluginlake` CLI for deployment lifecycle management.
- Passed code review (security + production readiness).

## What Needs To Be Done

### Immediate

- [x] Final review of restructured docs (ADR-008, dsp-authorization.md, federated-infrastructure.md).
- [x] Cross-ADR consistency review and fixes.
- [ ] Fix ADR-004 cross-references (points to ADR-002 for staging/logs, should be ADR-003) — minor.
- [ ] Commit docs restructure.
- [ ] Commit and push `docker-deploy-cli` branch (40 files from previous session).
- [ ] Open PR against `main`.

### Next priorities

- [ ] Write ADR-008: contract-to-compute mapping, query safety, algorithm approval, privacy validation for non-aggregates.
- [ ] Begin Phase 1 implementation planning (`src/pluginlake/dsp/`, `src/pluginlake/authz/`).
- [ ] Test full production compose startup end-to-end.
- [ ] Test CLI `pluginlake init` flow on a clean machine.

## Known Issues

- Dagster jobs may still OOM if host memory is limited and both ingest jobs run concurrently.
- Type checking has some pre-existing issues unrelated to current branches.

## Context for Next Session

- **Docs structure:** ADRs in `docs/decisions/` (short decision records). Design specs and research in `docs/background/`. API reference in `docs/reference/` (auto-generated).
- ADR-006 = "which orgs can connect" (Nuts, trust boundary 2). Now includes role claim mechanism (hub vs station).
- ADR-008 = "what users/queries are allowed" (DSP + VC + ODRL, trust boundaries 1 & 3). Now includes foundational glossary. Points to `background/dsp-authorization.md` for implementation detail (private, not in nav).
- `docs/background/federated-infrastructure.md` is the published platform comparison. Explicitly acknowledges pluginml uses vantage6 in production.
- ADR-008 is needed for: structured filter AST, pre-approved algorithm registry, privacy validation for non-aggregates, station-side credential sync, techniques to limit destructive operations.
- All work is on `docker-deploy-cli` branch, branched from `main`.
- Tests pass (`uv run pytest` — 250 tests).
- Linting clean (`uv run ruff check .`).

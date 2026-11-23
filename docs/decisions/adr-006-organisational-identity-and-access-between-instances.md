# ADR-006: Organisational identity and access between instances

**Status:** Proposed

## Context

Every pluginlake instance, whether it acts as a data station or as a processing hub, has to prove which organisation it belongs to.
A processing hub has to grant fine-grained access to the data stations in a federation, and each station has to enforce that access locally.
Which mechanism provides this is not decided yet.
Nuts is the leading candidate, but it is still being investigated, and so is the two-step approach that separates authenticating the caller from authorising by contract.

## Decision

Whatever mechanism is chosen, these properties hold:

- Every instance has its own organisational identity.
- The processing hub grants fine-grained access, and the data station validates and enforces it locally.
- The processing hub holds no data.
- A compromised instance cannot forge access that was issued by another one.

## Open questions

- Is Nuts used for organisational identity, and if so which release is the target?
- How is the caller authenticated first and authorised by contract second, and where does each step run?
- Which protocol carries contract negotiation between hub and station, and how are per-user permissions expressed?
- How do stations learn which hubs to trust, and how do instances join a network?
- Who issues the organisational identity for a hub operated by several organisations?
- Can a hub and a station share one instance, or are they always separate?
- How long do credentials live, and who renews them?

## Background

The research and the earlier design notes are background, not decisions.
The Nuts integration notes and the DSP decisions and risks notes are in the spike reports of the handbook vault.
The [DSP authorization architecture](../background/dsp-authorization.md) stays here as a design specification.

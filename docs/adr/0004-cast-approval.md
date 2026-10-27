# ADR 0004: Approve the cast before drawing panels

- **Status:** Accepted
- **Date:** 2026-10-27
- **Deciders:** Isaac Tumuti

## Context

In the [Day 2 spikes](../spikes/2026-10-28-findings.md), reference sheets kept both characters on model across 18 panels. But the cat's reference sheet invented a blue knitted vest that was not in its canonical description, and every panel faithfully copied it. References are strong enough to spread their mistakes everywhere.

## Decision

- After the director builds the character bible, Frameteller generates **one reference sheet per character** and shows them to the user.
- The user approves the cast or regenerates individual sheets. The cast has a status, `draft` or `approved`.
- **No panel can be drawn while the cast is `draft`.** This is a domain rule, not a UI convention.
- Changing an approved character's description or reference returns the cast to `draft`.

## Consequences

- One extra step before the first panel, which costs a few seconds of user attention and saves redrawing every panel later.
- The approval screen doubles as the demo's "meet the cast" moment.

# ADR 0002: Direct one transcript turn at a time

- **Status:** Accepted
- **Date:** 2026-10-27
- **Deciders:** Isaac Tumuti

## Context

Wow moment (a) is "live speech becoming panels". In the [Day 2 spikes](../spikes/2026-10-28-findings.md), directing the whole six-turn story in one Spark call took 22–31 s at default reasoning. With `reasoning_effort: minimal`, a single turn took 6.2 s and the whole story 6.8 s, and both still validated against our schema and domain checks.

## Decision

- The director runs **once per finished transcript turn** (`speechComplete`), with `reasoning_effort: minimal`. It receives the current character bible and the shots so far, and returns the shots and any new characters for that turn only.
- The system prompt and character bible form a **stable prefix** at the start of every request, for prompt caching once the prefix is large enough.
- A **full-story pass** (re-directing every turn together, e.g. to fix pacing) runs only when the user asks for it.

## Consequences

- Shots appear a few seconds after each sentence instead of after the whole take.
- Each turn's shots depend on earlier ones, so a later turn cannot re-plan earlier shots without a full-story pass.
- Many small calls instead of one: more requests, but Spark tokens are a negligible cost next to images.

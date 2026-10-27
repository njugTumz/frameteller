# ADR 0001: Use Clean Architecture for the backend

- **Status:** Accepted
- **Date:** 2026-10-27
- **Deciders:** Isaac Tumuti

## Context

Frameteller orchestrates four Meta models (Voice Transcribe, Spark, Image, SAM), Azure Blob Storage and ffmpeg. Several of these are uncertain on day 1: mask support in image edits, character consistency across panels, realtime ASR limits and rate limits. We may need to swap a model, add a fallback (for example region-described edits instead of mask edits), or add an open-weight router (Glimmer) late in the event.

Technical depth and code quality are 20% of the judging, and judges read the code and commit history. We need business rules that can be unit-tested without network calls or credits, and a structure where changing a provider is a contained change.

## Decision

The backend (`backend/src/frameteller/`) uses Clean Architecture with SOLID principles, in four layers:

| Layer | Contains | May depend on |
|---|---|---|
| `domain/` | Entities and value objects (`Project`, `Scene`, `Shot`, `Panel`, `Character`, `CharacterBible`, `TranscriptTurn`, `ObjectMask`, `Animatic`) and domain rules. Pure Python: no I/O, no framework imports. | nothing |
| `application/` | One use case class per use case, each with a single `execute()` (e.g. `DirectStoryFromTranscript`, `GeneratePanel`, `ExportAnimatic`). **Ports**: abstract interfaces such as `SpeechToTextPort`, `DirectorPort`, `ImageGenerationPort`, `SegmentationPort`, `MediaStoragePort`, `ProjectRepository`, `JobQueuePort`, `VideoRendererPort`, `Clock`, `IdGenerator`. Budget and cost guardrails. | `domain` |
| `infrastructure/` | Adapters that implement ports: Meta API clients, Azure Blob storage and repository, ffmpeg renderer, settings, logging, telemetry. | `application`, `domain` |
| `interface/` | FastAPI app, HTTP routes, WebSocket handlers, Pydantic request/response DTOs, and the composition root that wires adapters to use cases. No business logic. | all inner layers |

### The dependency rule

**Source code dependencies point inward only.** An inner layer never imports from an outer one. `domain` knows nothing about use cases; use cases know only ports, never concrete adapters, SDKs or FastAPI. Data crossing a boundary is converted to the inner layer's types (DTOs at the interface edge, domain entities inside).

Swapping a model or storage provider touches only `infrastructure/` and the composition root.

## Consequences

**Positive**

- Domain and use cases are unit-tested with in-memory fakes for every port: fast, deterministic, no credits spent.
- Fallbacks and provider swaps (mask vs. no-mask edits, Spark vs. Glimmer routing) are new adapters, not rewrites.
- Cross-cutting concerns (retries, timeouts, circuit breaking, cost logging) live in adapters, keeping use cases readable.
- The structure is easy for judges and new contributors to navigate.

**Negative**

- More files and mapping code (DTO ↔ entity) than a flat FastAPI app.
- Some ceremony for simple operations during a 9-day build.

**Mitigations**

- Keep ports narrow and only add them when a use case needs one.
- Once the backend is scaffolded, propose enforcing the dependency rule in CI (for example an import-linter contract).
- Any change that must cross a layer boundary needs a new ADR first.

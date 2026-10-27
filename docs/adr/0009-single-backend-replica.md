# ADR 0009: One backend replica

- **Status:** Accepted
- **Date:** 2026-10-27
- **Deciders:** Isaac Tumuti

## Context

Three parts of the backend live in process memory:

- The **job queue** (`InProcessJobQueue`) runs panel renders, cast sheets, pre-segmentation and edits as asyncio tasks. Its idempotency keys are a set in memory.
- The **event hub** (`EventHub`) delivers `job.updated`, `cast.proposed` and `shots.replaced` only to WebSockets connected to the same process.
- **Active sessions** (`ActiveSessions`) enforce one live voice session per project with an in-memory set.

With two replicas:
- a render queued on one replica would report progress only to sockets on that replica;
- the same idempotency key could run twice, charging credits twice;
- two narrations could run on one project.

Project documents are already safe across processes: `BlobProjectRepository` uses ETag optimistic concurrency.

For the hackathon, load is a demo, judges and a community vote. One 0.5 vCPU container handles many concurrent sessions, because the work is waiting on Meta's APIs.

## Decision

- The Container App runs with **`maxReplicas: 1`** and `minReplicas: 0` (scale to zero when idle) in staging and production.
- Revisions use single-revision mode, so a deploy replaces the replica rather than running two side by side.
- Nothing in the code assumes a single replica beyond the three components above. Storage, projects and the spend ledger are in Blob Storage.

## Consequences

- **Cold start**: the first request after idle waits for a container start (typically 10–20 s). Before the live demo, warm it with a `/healthz` request or set `minReplicas: 1` for the demo window.
- **A deploy interrupts live sessions** and drops queued jobs that have not started. Jobs that never ran can be re-requested; their idempotency keys are only in memory. Deploy staging freely, and production only outside demo and judging windows (CLAUDE.md section 7 freeze).
- **To scale out later**, the work is:
  1. **Job queue**: move to a durable queue (Azure Storage Queues or Service Bus), with workers on any replica, and idempotency keys in a store with a TTL (blob leases or Table Storage).
  2. **Events**: publish through a shared channel (Azure Web PubSub, Service Bus topics or Redis pub/sub) so any replica can push to any socket. Alternatively, pin a project's sockets to one replica with session affinity, which is not enough on its own for jobs.
  3. **One session per project**: hold a blob lease on the project for the session's lifetime, renewed while it runs, instead of the in-memory set.
  4. **Rate limiting**: move the token buckets to a shared store, or accept per-replica limits.
  5. Raise `maxReplicas` and add an HTTP concurrency scale rule.

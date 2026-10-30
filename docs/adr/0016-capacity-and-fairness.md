# ADR 0016: Capacity and fairness: limits, a waiting room, a judge lane and a budget calendar

- **Status:** Accepted
- **Date:** 2026-10-29
- **Deciders:** Isaac Tumuti
- **Builds on:** [ADR 0009](0009-single-backend-replica.md) (one backend replica), [ADR 0011](0011-animatic-export.md) (exports)

## Context

The public launch (Nov 2, 21:00 UTC+4), the X posts and the judging days (Nov 5–8) can each bring dozens of visitors at once. Before this change, nothing limited global concurrency:

- Fifty visitors could start fifty Muse Image calls at once and hit Meta's rate limits, and one visitor's 429 retries slowed everyone.
- ffmpeg exports competed with live sessions for the same CPU.
- A busy evening could spend the day's budget before a judge arrived.

Judges have to be able to try the product at any time, whatever the public is doing, and a busy studio has to say so instead of failing.

## Decision

### Global limits, and a line instead of an error

`application/capacity.py` has one `Gate` per scarce resource:

| Gate | Default | Setting | Where |
|---|---|---|---|
| live voice sessions | 24 | `CAPACITY_SESSIONS` | the session WebSocket |
| Muse Image calls in flight | 8 | `CAPACITY_IMAGES` | `GatedImages` around `ImageGenerationPort` |
| SAM calls in flight | 4 | `CAPACITY_SAM` | `GatedSegmentation` around `SegmentationPort` |
| exports rendering | 2 | `CAPACITY_EXPORTS` | the job queue's export lane |
| background jobs | 32 | `CAPACITY_JOBS` | the job queue |

- **Past a limit, work waits in line.** Each gate keeps arrival order, with judges ahead of the public. Whenever the line moves, every waiter is told its place and an estimate: the number of full rounds ahead of it times a moving average of how long a slot is held, seeded with typical times (sessions 150 s, images 25 s, SAM 5 s, exports 40 s).
- **Sessions:** a visitor past the limit gets `queue.waiting {position, estimate_s}` on the session socket ("The studio is busy. You're 3rd in line, about 2 min.") and can leave the line. Audio is read only once seated.
- **Jobs:** waiting jobs publish `job.updated` with `status: queued`, `position` and `estimate_s`, which the shot cards and the export panel show.
- **Exports and gallery copies run in their own lane**, so they never take a slot from drawing. ffmpeg runs at `nice 10` with 2 threads, so a live session's directing and drawing keep the CPU first.
- **A 429 never opens the circuit breaker.** It is retried up to 6 times, honouring `Retry-After` (at most 20 s), while the gate keeps everyone else in line behind it. Glimmer's quick policy does not retry a 429: Spark takes the review at once.

The gates are in memory, which is correct only with one replica (ADR 0009). We keep `maxReplicas: 1`.

### The judge lane

- A private link `https://app.frameteller.com/judge#<JUDGE_TOKEN>` (the token stays in the fragment, so it never reaches a server log) is posted once to `POST /judge`. The response sets `ft_judge`: an HttpOnly, Secure, SameSite=None cookie, valid 21 days (`JUDGE_PASS_DAYS`).
- The cookie holds only an expiry and an HMAC of it, keyed from the token, so **rotating `JUDGE_TOKEN` ends every pass at once**.
- `JudgeMiddleware` runs every request and socket with a valid cookie in the judge lane (a context variable that queued jobs inherit). There:
  - per-visitor and per-project caps do not apply;
  - judges go to the front of every line, and the session limit does not apply to them at all;
  - spending draws from a **separate judge budget** (`JUDGE_BUDGET_PER_DAY_USD`, default USD 15), which the public cap can never consume.
- The studio shows a "Judge access" badge in the top bar.
- **One link, a pass per browser (v1.1.0).** The token is never used up. Each `POST /judge` issues a new pass:
  the cookie carries a random pass id, signed with the expiry. Each pass may start 15 stories a day
  (`JUDGE_STORIES_PER_PASS_PER_DAY`), so one leaked or over-eager browser can't take the whole reserve. Each
  judge charge is also recorded under the pass's own ledger key, beside the judges' pool, so the admin overview
  shows stories and spend per pass without counting anything twice.
- **Dated reserve (v1.1.0):** USD 25 a day on Nov 5-8 (`JUDGE_BUDGET_DAYS_USD`), USD 15 otherwise. The admin page
  can lower it at once (`PUT /admin/judge/reserve`, kept in `admin/judge.json`), never raise it, so a leaked link
  can be contained without a redeploy. Public visitors get 5 stories a day on Nov 5-8 and 3 otherwise, and all
  story limits now count days at UTC+4, like the budget.

### A budget calendar

`BudgetCalendar` sets the public daily cap by date, with days counted in UTC+4 (`BUDGET_UTC_OFFSET_HOURS`). The default is USD 10. `BUDGET_DAYS_USD` raises it to USD 25 on Nov 2 and Nov 5–8. The judge budget is in addition to these caps. The runbook says how to change it with one `az containerapp update`.

### Size the container from measurements

`scripts/load_test.py` runs the real app with fake Meta adapters, which take as long as the real models. With 50 visitors it measured CPU at p95 1.9 cores (both cores busy while two exports render) and peak memory of 0.93 GiB ([docs/load-test.md](../load-test.md)). Production moves from 1 vCPU / 2 GiB to **2 vCPU / 4 GiB**, Container Apps' pairing for 2 vCPU. That gives 4x memory headroom over the measured peak and a full core for live sessions while ffmpeg renders.

## Consequences

- No visitor sees an error because the studio is busy: they see their place in line. A visitor who waits too long can leave the line, or watch the gallery.
- The image gate is the throughput limit. At 8 in flight and about 18 s per draft, the studio draws about 25 panels a minute. That is enough for the expected launch traffic. In the real five-story test on staging, 17 Muse Image, 40 Spark and 16 SAM calls a minute drew no 429 ([docs/load-test.md](../load-test.md)). If Meta throttles us below that, lower `CAPACITY_IMAGES`, and 429s keep backing off in line meanwhile.
- The image work around the models (SAM masks and cut-outs, contact sheets, render preparation) runs in worker threads. On one core, doing it on the event loop blocked the health probe, and the platform restarted the app.
- Burned captions go through one ffmpeg stream, so an export's memory does not grow with its caption lines. Staging (0.5 vCPU / 1 GiB) renders one export at a time.
- Everything is in memory, so scaling out would need a shared queue (Redis or Service Bus) first. With one replica that is out of scope.
- The judge link is a bearer secret. It is never committed, and rotating it is one command (runbook).

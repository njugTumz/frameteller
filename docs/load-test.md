# Load test: 50 visitors at once (Oct 29, 2026)

What the studio does under a crowd, measured with `backend/scripts/load_test.py` ([ADR 0016](adr/0016-capacity-and-fairness.md)). It also explains the production size of 2 vCPU / 4 GiB.

## Setup

- **The real app**, in one process: routes, the session WebSocket and waiting room, the gates, the job queue, the budget guard, local file storage, Pillow, and real ffmpeg with burned-in captions.
- **Fake Meta adapters** that sleep for the latencies seen on staging and return full-size images:
  - Spark: 3 s per turn, 4 s for the cast;
  - Muse Image draft: 18 s;
  - SAM: 4 s;
  - supervisor review: 3 s.
- **Each visitor** has its own browser id and:
  1. creates a project;
  2. narrates 24 s of PCM at real-time pace, with a beat every 6 s;
  3. waits for the cast sheets and approves them;
  4. draws every shot as a draft;
  5. exports the animatic.
- **The machine:** a 2 vCPU / 8 GiB Linux VM, the same CPU count as production. The 50 clients ran on the same cores, so the server numbers are conservative.
- **Default limits:** sessions 24, images 8, SAM 4, exports 2, jobs 32. The per-IP rate limits were raised, since every visitor came from 127.0.0.1.
- **Measurements:** CPU and memory are the server process plus its ffmpeg children, sampled every second from `/proc`. The queues come from `GET /admin/overview`.

```
cd backend && .venv/bin/python scripts/load_test.py --visitors 50 --ramp 60
cd backend && .venv/bin/python scripts/load_test.py --visitors 50 --ramp 5 --scale 3   # a burst
```

## Results

### 50 visitors arriving over 60 s, real model latencies

**50/50 visits finished, in 471 s. No errors.**

| step (seconds) | p50 | p95 | max |
|---|---|---|---|
| any REST call (create, approve, render, export) | 0.00 | 0.02 | 0.02 |
| waiting room seat | 0.00 | 0.00 | 0.00 |
| end of narration → session ended | 3.0 | 3.0 | 3.0 |
| end of narration → cast sheets drawn | 99.6 | 199.9 | 214.3 |
| draw 2 draft panels | 196.2 | 218.4 | 231.6 |
| export animatic (2 shots, captions) | 5.8 | 8.5 | 8.7 |
| whole visit | 332.6 | 408.5 | 410.9 |

| gate | most in flight | longest line |
|---|---|---|
| sessions | 22 / 24 | 0 |
| images | 8 / 8 | 48 |
| SAM | 4 / 4 | 27 |
| exports | 2 / 2 | 2 |
| jobs | 32 / 32 | 127 |

- **Server CPU:** mean 0.58 cores, p95 1.92 cores, max 1.97 cores.
- **Memory:** 146 MiB idle, **929 MiB at peak**.

### A burst: 50 visitors within 5 s (model latencies divided by 3)

**50/50 visits finished, in 226 s.**

- **Waiting room:** 26 visitors waited for a seat, as the session limit is 24. They waited p50 22 s, max 45 s. Each saw its place and an estimate, then got in.
- **Export:** p50 23 s, p95 64 s. The export lane held two at a time and the rest waited in line, while drawing went on.
- **Server CPU:** mean 1.23 cores, p95 1.95 cores.
- **Memory:** 933 MiB at peak.

## What it shows

1. **Nothing fails under load.** Past a limit, work waits in line, and REST calls stay instant (p95 20 ms) because all slow work is a job.
2. **The image gate sets the pace,** by design. At 8 Muse Image calls in flight and about 18 s each, the studio draws about 25 images a minute. Fifty visitors arriving in a minute need 200 images (2 sheets and 2 panels each), so the last cast waits about 3 minutes, and the shot cards say so. Raising `CAPACITY_IMAGES` speeds this up only if Meta's rate limits allow it. On staging, 17 Muse Image calls a minute drew no 429 (below).
3. **CPU spikes come from ffmpeg.** Two exports at once use both cores for a few seconds. That is why exports have their own lane at `nice 10`, and why production needs a second core, so live sessions, directing and drawing keep one.
4. **Memory peaks below 1 GiB.** An ffmpeg export takes about 420 MiB for 2 shots and 510 MiB for 6 shots with 18 caption lines (measured after the caption fix below).

**Production size: 2 vCPU / 4 GiB** (from 1 vCPU / 2 GiB), still one replica (ADR 0009). That is twice the cores the p95 needs, and 4x the memory of the peak. 4 GiB is also Container Apps' pairing for 2 vCPU.

## Staging: 5 stories at once with the real models (Oct 30)

Five copies of `scripts/smoke_local.py --beats --export` at once against staging, each with its own visitor id. Each one:

1. narrates the 28 s lantern-cat story at real-time pace;
2. approves the cast;
3. draws 2 draft panels, click-selects an object, draws the other 4;
4. exports the animatic with captions.

Staging is smaller than production: **0.5 vCPU / 1 GiB** (production is 2 vCPU / 4 GiB).

### What the first run found, and the fixes

| Run | What happened | Cause | Fix |
|---|---|---|---|
| 1 (03:25 UTC) | All five sockets dropped at about 4 min (close 1012). One story reached export, which failed. | The liveness probe (1 s default timeout) failed three times, and Container Apps restarted the app. SAM's pixel work (decode, resize, the pure-Python mask decoder, cut-outs) ran on the event loop, and pre-segmenting many panels at once blocked it. | SAM's pixel work runs in a worker thread. The liveness probe timeout is now 5 s. |
| 2 (10:12 UTC) | No restarts, and every story drew all its panels. But 3 of 4 exports were killed (ffmpeg exit -9). | Out of memory: each burned caption line was its own full-frame input, about 13 MiB each. Two 6-shot exports did not fit in 1 GiB beside the app. | All captions now go through one stream, so 6 shots with 18 lines peak at 509 MiB (was 711). Staging renders one export at a time (`CAPACITY_EXPORTS=1`). |
| 2, exports again (10:44 UTC) | **5/5 exports succeeded.** One rendered at a time while the others waited in line: about 118 s each on 0.5 vCPU. | | |

One more failure in run 2 was our test client, not the server. Story 3's script made blocking REST calls inside its async loop, missed the server's keepalive pings for about 20 s, and was disconnected. The client now makes its REST calls in a thread.

### Run 2: latencies with the real models, 5 stories at once

| step (seconds) | min | max |
|---|---|---|
| end of narration → session ended | 1.5 | 1.8 |
| end of narration → cast sheets drawn (drawn while still narrating) | 1.6 | 3.9 |
| draw 2 draft panels (in parallel) | 20.7 | 33.8 |
| click-select on panel 1 (SAM) | 1.8 | 7.4 |
| draw the other 4 draft panels | 28.1 | 62.0 |
| export one animatic (6 shots, captions; on 0.5 vCPU) | 94 | 120 |

### Meta's rate limits

**No 429 from any model in either run.** Peak calls per minute (run 2):

- Muse Spark: 40;
- Muse Image: 17, with the image gate holding 8 in flight;
- SAM: 16;
- Voice Transcribe: 5 sessions at once.

We never reached Meta's limits, so the real ceiling is still unknown. The image gate (`CAPACITY_IMAGES=8`) stays as the bound. If 429s do appear, they are retried up to 6 times, honouring `Retry-After`, while the gate keeps everyone else in line (ADR 0016).

**Spend:** run 1 cost USD 0.84 and run 2 USD 0.93, both in Meta credits. The exports call no model.

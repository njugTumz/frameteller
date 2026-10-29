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
2. **The image gate sets the pace,** by design. At 8 Muse Image calls in flight and about 18 s each, the studio draws about 25 images a minute. Fifty visitors arriving in a minute need 200 images (2 sheets and 2 panels each), so the last cast waits about 3 minutes, and the shot cards say so. Raising `CAPACITY_IMAGES` speeds this up only if Meta's rate limits allow it. The staging test below checks that.
3. **CPU spikes come from ffmpeg.** Two exports at once use both cores for a few seconds. That is why exports have their own lane at `nice 10`, and why production needs a second core, so live sessions, directing and drawing keep one.
4. **Memory peaks below 1 GiB.** Each ffmpeg export at 1920×1280 with captions takes about 350 MiB.

**Production size: 2 vCPU / 4 GiB** (from 1 vCPU / 2 GiB), still one replica (ADR 0009). That is twice the cores the p95 needs, and 4x the memory of the peak. 4 GiB is also Container Apps' pairing for 2 vCPU.

## Staging: 5 stories at once with the real models

*Pending: runs after the next staging deploy (this branch is not pushed while the production test is in progress). The results, the 429s seen and Meta's observed rate limits go here.*

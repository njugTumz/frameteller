# ADR 0020: Judges wake Muse Glimmer

- **Status:** Accepted
- **Date:** 2026-10-31
- **Deciders:** Isaac Tumuti
- **Builds on:** [ADR 0013](0013-glimmer-on-modal.md) (Glimmer on Modal, the warm lease), [ADR 0016](0016-capacity-and-fairness.md) (the judge pass)

## Context

Glimmer reviews only while the warm-up script holds a lease, so visitors never start the GPU. Judges review the build
on their own schedule (Nov 5–8), when nobody is running the script. They would see "Checked by Muse Spark" on every
panel, and never see the open-weight model at work.

## Decision

- **A request with a valid judge pass is judge activity.** The judge middleware tells `JudgeGlimmer`. Public requests
  never reach it.
- **Cold Glimmer: one wake-up starts in the background.** It polls `/health`, as `deploy/modal/warm.py` does, then
  sends one tiny chat request. Spark reviews meanwhile. When Glimmer answers, the backend takes the same lease the
  script does, and reviews switch to screen mode.
- **A keeper holds the lease until 5 minutes after the last judge activity.** It renews the lease every 30 s and
  pings Glimmer every 4 minutes, so Modal keeps the container up. When judges go quiet the lease runs out, and Modal
  scales to zero 5 minutes later.
- **Caps per day (UTC+4):** 10 wake-ups, and USD 5 of estimated Modal cost for them. The estimate is GPU time from the
  wake-up to the end of the lease, plus the 5-minute scale-down, at USD 3.95/hour (H100). At the spend guard the
  keeper revokes the lease. Past either cap, judges get Spark.
- **One document**, `admin/glimmer-wakes.json` (never served), keeps each day's wake-ups, the estimate and the last
  cold start. The admin overview shows them.
- **An operator route** (`POST /internal/glimmer/judge-wake`) does what a judge request does. It is authorised by the
  Glimmer endpoint token, like the lease, so the team can check the wake-up without a judge cookie.

## Consequences

- While a judge's lease holds, public reviews also use Glimmer (the lease is global). That is the same rule as
  before: Glimmer is used when it is warm.
- Worst case for judges is USD 5 a day of Modal.
- One replica (ADR 0009): the keeper runs in-process. A restart ends it, and the lease runs out within 5 minutes.

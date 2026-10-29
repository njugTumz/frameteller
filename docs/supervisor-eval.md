# Continuity supervisor eval

Measured on 2026-10-29. The set and the runner are in [`backend/tests/eval/`](../backend/tests/eval/). The decision it informs is recorded in [ADR 0013](adr/0013-glimmer-on-modal.md).

## The set

There are 20 images from the lighthouse story (our own synthetic story: Ada, an old lighthouse keeper, and Pip, a small fox), stored as 768 px webp files. `labels.json` holds the labels.

**9 should pass:**
- The 2 clean reference sheets.
- The 6 clean panels.
- One control edit that changes nothing that matters (heavier rain on the window).

**11 should be flagged**, each with the rules a correct review names:
- **Reproduced real failures.** These happened in our own runs:
  - Pip's sheet drawn in Ada's green sweater (CAST-04).
  - Pip drawn in a blue vest (CONT-04).

  The originals were overwritten by later runs, so each was recreated with one Muse Image edit of the clean image.
- **Controlled variants**, one Muse Image edit each (`make_set.py`, USD 0.12 for all 12 edits):
  - Ada's sheet with a red scarf (CAST-04).
  - Ada with a hat, with glasses, with black hair, or in a red sweater (CONT-04 or CONT-05).
  - An extra grey cat (CONT-02).
  - Pip removed (CONT-01).
  - Pip turned into a cat (CONT-03).
  - Pip drawn photorealistically in a pencil panel (CONT-07).

Every edit was looked at before labelling, and all 12 took. 8 of the 11 failures can be repaired with one appearance edit ("fixable"). The other 3 cannot: the missing character, the wrong species and the wrong style.

Each image is reviewed once, with the same rubrics, prompt and schema the supervisor uses. Panels are checked against `panel-continuity.md` and `shot.md`, with the shot and the clean reference sheets. Sheets are checked against `cast.md`. Only blocker and major issues count, as in the policy.

## Results

| | Muse Spark 1.3 | Muse Glimmer (Modal, H100) | Screen: Glimmer, Spark confirms flags |
|---|---|---|---|
| Precision, flagged items | **1.00** | 0.79 | **1.00** |
| Recall, flagged items | **1.00** | **1.00** | **1.00** |
| Names an expected rule | **11/11** | **11/11** | **11/11** |
| False flags on clean images | **0/9** | 3/9 | **0/9** |
| False fixes (an automatic edit of a clean image) | **0/9** | **0/9** | **0/9** |
| Proposes a fix when one edit can repair it | **8/8** | 6/8 | **8/8** |
| Median latency per review | **4.7 s** | 10.0 s | 12.8 s |
| Model cost per review | USD 0.0061 | USD 0 per call; GPU USD 3.95/h | USD 0.0043 (Spark on 14 of 20) |

Notes:
- Latency is measured per review, one at a time, with Glimmer already warm. A cold Glimmer takes 194–221 s to start (measured twice). Under `fallback` or `screen`, Spark answers in the meantime.
- **Spark cost** is from the token counts: about 1,350 input tokens (two 768 px images and the rubrics) and a few hundred reasoning tokens at low effort.
- **Glimmer cost.** A review costs about 10 s of GPU (about USD 0.011) when the GPU is busy. But every wake from cold costs at least the 5-minute scale-down window (about USD 0.33) plus the start.
- **Screen latency** for a flagged image adds both reviews, one after the other. For an image Glimmer passes, it is Glimmer's latency alone.

## Discussion

**Spark is the better reviewer on this set, and the default (`REVIEWER=spark`).** It flagged every failure with the right rule, flagged no clean image, proposed the right edit for all 8 fixable failures, and asked about the 3 an edit cannot fix. It is also twice as fast, and it has no cold start.

**Glimmer clearly underperforms Spark as the only reviewer, but it does well at one narrower job: screening.** It missed nothing: 11/11, always with the right rule. Every image it passed was clean (6/6), and it never proposed an edit to a clean image. Its weakness is false alarms: it flagged 3 of 9 clean images. Two were arguable:
- Ada's sheet shows "white pants and shoes not named in her description". The description names only the sweater.
- A panel is "more watercolour than the sheet's pencil".

One was a misreading: it said Pip "is outside the window instead of tumbling inside", but he is mid-jump through it. All three were `ask`, never `fix`, so under the policy they would cost the user a look, not a wrong edit.

That profile suits a screen. With `REVIEWER=screen`, Glimmer's passes stand and anything it flags goes to Spark, whose verdict decides. On this set:
- The screen scores the same as Spark alone.
- It sends 14 of 20 reviews on to Spark, saving 30% of Spark's cost.
- It costs latency (reviews run in the background, so this is acceptable) and GPU hours.

So we use the screen when Glimmer is warm anyway, for a demo or a recording session (see the [runbook](runbook.md#warm-glimmer-before-a-demo)). We keep Spark alone when it is not. Waking a GPU for each casual visitor's first review would cost more than it saves.

**Serving lesson.** The first Glimmer run scored 0/11 on rules: every answer came back without its `issues` array. vLLM accepted the strict JSON schema but did not enforce it for this model and reasoning parser. Answers contained extra keys (`"reason": "CONT-04: …"`), an `issues` object instead of an array, and fields in any order. Two changes fixed it:
1. The Glimmer adapter now spells the answer's shape out in the prompt.
2. The parser repairs the two off-schema shapes Glimmer actually produced.

Contract tests replay both shapes. Spark, on Meta's API, followed the strict schema every time.

**Limits of this eval.**
- 20 images is small, and one story in one style (pencil). Treat the numbers as a sanity check, not a benchmark.
- Most variants change one thing on purpose. Real failures can be subtler, such as a slightly different face. CONT-06 and CONT-08 are barely tested here.
- Each image was reviewed once. Glimmer samples at temperature 1.0 as Meta recommends, so its answers vary between runs.
- The labels are ours.

## Reproduce

```bash
cd backend
.venv/bin/python -m tests.eval.make_set ../spikes/out/lighthouse/store   # only missing variants are made
.venv/bin/python -m tests.eval.run_eval spark                          # about USD 0.12
python3 ../deploy/modal/warm.py && .venv/bin/python -m tests.eval.run_eval glimmer
.venv/bin/python -m tests.eval.run_eval screen                         # combines the two, no calls
```

Results are written to `tests/eval/results-*.json`, one row per image with the decision, the rules, the issues, the latency and the cost.

# ADR 0008: Narrator beats cut the shots

- **Status:** Accepted
- **Date:** 2026-10-27
- **Deciders:** Isaac Tumuti

## Context

[ADR 0002](0002-incremental-direction.md) directs one transcriber turn at a time. On our 48.5 s, six-paragraph recording, the transcriber's endpointing gave 4 turns once and 2 turns in both smoke runs ([findings](../spikes/2026-10-28-findings.md)). Pauses between story beats sit close to its threshold. A 30 s turn arrives as one block, so shots appear late and in a burst, and the director has to guess where one shot ends.

The narrator knows where a shot starts. One key press (or a button) is a far more reliable signal than a pause.

## Decision

**Beats.** The live session accepts `{"type": "beat"}`, meaning "a new shot starts now".
- The beat's time is the audio position the server has received at that moment. It is exact, because frames and beats arrive in order on one socket.
- The beat closes the stretch since the previous beat (or since the session started): its words become one turn, which is directed at once with `minimal` effort.
- **It closes once the transcriber has processed 500 ms of audio past the beat** (`audioProgress`), not at the instant it arrives. The grace period comes from measurements on the real recording:

  | Event | When it appeared, in transcriber audio, relative to the pause |
  |---|---|
  | Last word before a pause | 80–240 ms after the beat; it was still missing at the instant of the beat |
  | First word after the pause | 840 ms or more after the beat |

  - Snapshotting at the instant of the beat put the last word of four of six paragraphs into the next shot.
  - With the grace period, all six paragraphs split exactly. Each beat closes about 0.8 s after it was sent.
- Words are matched to beats by position in the running transcript: words of finished transcriber turns, followed by the current cumulative partial.
- When the stream ends, waiting beats close in order. The last stretch runs to the end of the speech.
- ~~Beat stretches are contiguous from the first beat to the end.~~ Amended 2026-10-28: a stretch starts at its first speech, not at the previous beat (see below).

**Amendment (2026-10-28): leading silence is trimmed.** A narrator pressed beat at 66 s and started talking much later, and the first shot lasted 49 s.
- A stretch now starts where its first words were spoken: the transcriber's `speechStart` for the turn they came from. It never starts before the previous boundary.
- If that transcriber turn began before the boundary (one long sentence across a beat), the words start at the boundary, because speech never stopped.
- Adapters without `speechStart` fall back to the boundary, as before.
- Stretches are no longer contiguous. The animatic cuts the narration recording to the same segments, so picture and voice stay in sync ([ADR 0011](0011-animatic-export.md)).

**Endpointing is the fallback.** Until the first beat, each transcriber turn (`speechComplete`) is directed as before. From the first beat on, transcriber turns only add words to the transcript; they never create shots. A `speechComplete` that arrives after a beat therefore cannot direct the same audio twice.

**Duration split.** When one turn produces several shots, the turn's time is shared between them in proportion to each shot's word count (its action plus dialogue).
- Every shot gets at least **1.5 s** when the turn is long enough for that. A shorter turn is split evenly.
- The parts always add up exactly to the turn (largest-remainder rounding), so the animatic never drifts from the narration.
- This replaces the director's own `duration_ms`. The domain rule is `split_duration` in `domain/timing.py`.

**Corrections.** `{"type": "transcript.corrected", "turn_id", "text"}` fixes misheard words in one turn ("Sinuan" → "Scene one").
- Only the shots that cite that turn are re-directed. The new shots take the old shots' place and everything is renumbered.
- The old shots' panels are dropped, because they showed the misheard version.
- The server replies with `shots.replaced`.
- It works during the session, in order with direction, and after `session.ended` while the socket stays open.

**Turn ids are per session.** They carry a session tag (`55a635ca-b3`, `55a635ca-0`), so a second narration in the same project cannot reuse the first one's ids.

## Consequences

- Shots appear one per beat, about 4 s after the narrator moves on (0.8 s grace plus a ~3–4 s `minimal` director call), instead of after a 30 s block.
- The UI needs a beat control (space bar or a button) and should show where beats fell.
- The 500 ms grace assumes partials trail the transcriber's progress by less than that. If the model gets slower, words can spill again: raise `BEAT_GRACE_MS`. A narrator who starts speaking the instant they press beat loses nothing, because the first word takes 840 ms or more to appear.
- Word counts of action and dialogue approximate how long the narrator spoke about each shot. With beats, most turns produce one shot, so the approximation rarely matters.

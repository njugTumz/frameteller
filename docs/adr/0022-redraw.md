# ADR 0022: Redraw, with what should change and Keep previous

- **Status:** Accepted
- **Date:** 2026-10-31
- **Deciders:** Isaac Tumuti
- **Builds on:** [ADR 0014](0014-edit-from-stored-images.md) (edits from stored images), [ADR 0019](0019-image-prompt-safety.md) (prompt safety)

## Context

A tester said "there was no button to regenerate" an image. A panel could only be drawn again when it was out of
date or had failed, and while it was drawn again the card showed an empty sketch. Sheets said "Try again" or
"Regenerate". A new drawing replaced the old one with no way back. A drawing drawn again from the same prompt
often came out nearly the same.

On production on Oct 31, 41 drawings took 17.6 s at the median and 25 s at p90 (28.7 s at most). None were refused
and none failed.

## Decision

- **Every panel card, the panel editor and every sheet has a visible Redraw button**, icon and label, on phones too.
  It opens an optional box, "What should change?", with **Redraw** and **Surprise me**.
- **A Redraw is a new take of the same shot.** The prompt moves the camera: one of seven takes, chosen by
  revision, so a retried job draws the same take. Surprise me asks for bolder staging and lighting. The
  user's change is said as the director's, cleaned like every prompt, and said more plainly in the retry after a
  refusal. The shot's framing, setting and action, the approved sheets and the clothes stay as they are. Draw
  final is not a new take.
- **The drawing stays on screen** while the new one is drawn, with "Drawing… about 20 s" and a bar that fills
  to 90% in 20 s. A redraw that fails leaves the panel ready on its last drawing.
- **Panels keep their earlier drawings as versions**, as they were shown, composite included, newest first and
  six at most, each with its continuity check. After a Redraw the card offers **Use new** or **Keep previous**,
  and the editor lists the versions with **Use this**. Showing a version again is free: no model call. It
  becomes the next revision, as a plain render without layers, and is segmented again for click-to-select.
- **A frame refused twice says what to change.** The message asks the user to say plainly what happens, by look
  and action, and the panel keeps a suggested change (the shot's action, said plainly). The Redraw box opens
  with that suggestion.
- **Sheets take the same change or Surprise me.** A change lets a sheet whose description was refused through;
  a Redraw with no change still answers 409 `edit_first`. Sheets keep no versions.
- Redraws count toward the render allowance and the budget like any render, and the supervisor checks each one.

## Consequences

- A panel document holds up to six more image references. Old images are already kept in storage, so nothing
  new is stored.
- Restoring a drawing that had moves bakes them into the picture; its layers cannot be adjusted again.
- Sheets have no Keep previous. A redrawn sheet must still be approved, which is the time to check it.

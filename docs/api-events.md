# Live session WebSocket

The REST API is described by [`backend/openapi.json`](../backend/openapi.json) (also served at `/docs` by a running backend). OpenAPI cannot describe WebSocket messages, so they are documented here. Message shapes come from `backend/src/frameteller/interface/dto.py` (`event_message`).

```
ws(s)://<backend>/ws/projects/{project_id}/session
```

One live session per project at a time. Browsers must connect from an origin in `ALLOWED_ORIGINS`.

## Client → server

| Message | When | Shape |
|---|---|---|
| Start | First message, within 10 s | JSON `{"mode": "narrate" \| "co_direct", "keywords": ["Mira", ...], "keep_audio": true}` |
| Audio | Then, repeatedly | **Binary** frames of raw PCM, signed 16-bit little-endian, mono, **24 kHz**. Even length, at most 32,768 bytes (about 0.34 s). Send at real-time pace. |
| Beat | When a new shot starts | JSON `{"type": "beat"}`. See [Beats](#beats). |
| Correction | Any time, also after `session.ended` | JSON `{"type": "transcript.corrected", "turn_id": "55a635ca-b1", "text": "Scene one. Night. ..."}`. `text` is 1–2,000 characters. |
| End | When the narrator is done | JSON `{"type": "end"}` |

- `mode` is fixed for the session. `narrate` uses low-latency turn endpointing; `co_direct` adds speaker labels (`A`, `B`) but only closes a turn when the speaker changes or the stream ends. In our measurement, one narrator gave a single 42-second turn (see the [findings](spikes/2026-10-28-findings.md)).
- `keywords` (at most 50, each trimmed to 40 characters) bias recognition towards character and place names.
- `keep_audio` (default `false`): only with the narrator's consent. The server keeps the session's audio as a WAV (`narrations` on the project) for the animatic's voice track. It is never logged; `DELETE /projects/{id}/narration` deletes it, and in staging it expires after 30 days.
- Invalid frames and unknown JSON messages are dropped. The server reports each kind once with a non-fatal `error`.
- A session stops by itself after **55 minutes** of audio.

## Server → client

Every server message is JSON with a `type`.

| `type` | Fields | Meaning |
|---|---|---|
| `session.started` | `mode` | Start message accepted; send audio. |
| `transcript.partial` | `text` | The words heard since the last completed turn (with beats: since the last beat closed). **Replace** the previous partial; never append. It is sent again, often empty, when a beat closes, so a word never shows both in a `turn.completed` and in the partial. |
| `turn.completed` | `turn: {id, text, start_ms, end_ms, speaker}` | A finished turn, sent to the director. With beats, there is one per beat; without beats, one per transcriber turn. `start_ms`/`end_ms` are positions in the audio and drive animatic timing. `speaker` is `null` in `narrate` mode. Ids are unique per session (`55a635ca-b2`, `55a635ca-0`). |
| `shot.created` | `shot: {id, number, framing, character_ids, setting, action, dialogue, duration_ms, source_turn_ids, panel: null}` | The director turned a turn into a shot (one or more per turn). The shots of one turn share its time by word count, at least 1.5 s each, and add up to the turn. |
| `shot.updated` | `shot: {...same fields as shot.created}` | A later turn revealed who or what an earlier, vaguely described shot showed ("something small and orange" was Pip). Only the last 3 shots can change, and only `character_ids` and `action`. Replace the card; its panel is now `outdated`, so offer to draw it again. A character the reveal replaced (a guess no shot shows any more) leaves the cast, so refresh with `GET /projects/{id}`. |
| `shots.replaced` | `turn, removed_shot_ids, shots` | A correction was applied. `shots` (already renumbered) replace `removed_shot_ids` at the same place in the storyboard. Shots after them may have new numbers, so refresh numbering with `GET /projects/{id}`. Panels of removed shots are gone. |
| `cast.proposed` | `characters: [{id, name, description, reference_url}]` | New characters with freshly drawn reference sheets. Show them, then `POST /projects/{id}/cast/approve`. |
| `job.updated` | `kind, key, status, shot_id, revision, message, progress` | Background work: `kind` is `generate_cast`, `generate_panel`, `pre_segment_panel`, `edit_panel`, `compose_panel` (a saved move, [ADR 0010](adr/0010-clean-plates.md)) or `export_animatic` ([ADR 0011](adr/0011-animatic-export.md)); `status` is `queued`, `running`, `succeeded` or `failed`. `message` is user-facing, on failure. `progress` (0–1) comes with `running` updates of the animatic export, every 5%; otherwise it is `null`. |
| `error` | `message, fatal` | Something went wrong. `fatal: false` means the session carries on (for example, one turn could not be directed). `fatal: true` means it has ended. |
| `audio.silent` | `after_ms, level` | Sent at most once, at the start: 8 s of audio arrived with no words and nothing louder than about -46 dBFS (`level` is the loudest 80 ms as RMS, 0–1). The microphone is probably muted or the wrong device. Say so and offer a device picker; reconnect with the new device. |
| `session.ended` | `turns, shots, heard` | The narration is fully transcribed and directed. `heard: false` means no words were heard at all: say so rather than "done". |

After `session.ended` the socket **stays open** so `cast.proposed` and `job.updated` keep arriving, including for renders started over REST. Close it when you are done. It closes by itself after 15 idle minutes. A new narration on the same project can start on a new socket as soon as `session.ended` arrives.

Typical order for one turn that introduces a character:

```
session.started
transcript.partial  (several)
turn.completed
shot.created
job.updated  generate_cast queued → running
session.ended            (after {"type":"end"})
cast.proposed
job.updated  generate_cast succeeded
```

## Beats

A beat means "a new shot starts now" ([ADR 0008](adr/0008-reliable-beats.md)). Send it when the narrator presses the beat key, ideally in the pause before the next sentence.

- Its time is the end of the audio the server has received.
- It closes the stretch since the previous beat once the transcriber has caught up: 500 ms of audio past the beat, about 0.8 s of wall time. Then the stretch is sent as one `turn.completed` and directed.
- A beat with nothing said since the previous one only marks the start, so it is fine to send one before the first sentence.
- After the first beat, the transcriber's own pauses no longer cut shots. Without any beats, they do, exactly as before.
- When the narration ends, the last stretch runs to the end of the speech.

```
session.started
transcript.partial  (several)
                    ← {"type": "beat"}   (narrator moves to the next shot)
turn.completed      (the words since the previous beat, ~0.8 s later)
shot.created
```

## Corrections

Send `transcript.corrected` with a `turn_id` from a `turn.completed` event and the fixed text.
- Only the shots from that turn are re-directed.
- The reply is `shots.replaced`, and `cast.proposed` follows if the correction introduced a new character.
- An unknown turn gets a non-fatal `error`.

## Close codes

| Code | Meaning |
|---|---|
| 1000 | Normal close |
| 1008 | Origin not allowed, or rate limited |
| 4400 | Missing or invalid start message |
| 4404 | No such project |
| 4409 | A voice session is already running for this project |

Before closing with a 44xx code, the server sends a fatal `error` with a user-facing message.

## REST endpoints that pair with the session

| Endpoint | Returns |
|---|---|
| `POST /projects/{id}/cast/approve` `{descriptions?}` | `{approved, redrawing, job_key}`. A corrected description redraws that sheet (`cast.proposed` follows), and you approve again. |
| `POST /projects/{id}/shots/{n}/panel` `{quality: "draft" \| "final"}` | 202 job ticket; follow `job.updated`. |
| `POST /projects/{id}/shots/{n}/panel/edit` `{instruction}` | 202 job ticket. |
| `POST /projects/{id}/shots/{n}/panel/select` `{x, y, preview_width, preview_height}` | The mask under the click. `cached: true` means no SAM call was needed. |
| `POST /projects/{id}/shots/{n}/panel/layers` `{object_id, dx, dy, scale, deleted}` | 202 `compose_panel` ticket. The panel's `image_url` then shows the object at its new place on a clean plate; `base_image_url` stays the model render. |
| `POST /projects/{id}/exports/animatic` `{subtitles}` | 202 `export_animatic` ticket. When it succeeds, `GET /projects/{id}` has `animatic: {url, duration_ms, subtitles, voiced}`. The URL plays inline (it answers `Range` requests); `?download=1` saves it. |
| `GET /projects/{id}/exports/storyboard.pdf` | The storyboard sheet (A4 landscape, six shots a page): panel, shot number, framing, action, dialogue and duration. Undrawn shots print as "Not drawn yet". |
| `POST /projects/{id}/dictation` (body: WAV, mono 16-bit, 16 or 24 kHz, at most 30 s) | `{text}`: a spoken edit instruction, transcribed for the user to check before sending it to `.../panel/edit`. Nothing is directed. |

## Share links

A share link is read-only, unguessable and revocable. It never contains or reveals the project id: the project id is all it takes to edit a project.

| Endpoint | Returns |
|---|---|
| `POST /projects/{id}/share` | Body `{public?: bool}` (default false). Returns `{token, public, url, page_url}`. Post `url` (`{api}/s/{token}`): it previews on X and redirects browsers to `page_url` (`{studio}/s/{token}`). Calling it again returns the same link and sets `public`. |
| `DELETE /projects/{id}/share` | 204. The link stops working within a minute (share responses are cached for 60 s). |
| `GET /s/{token}` | HTML with `og:` and `twitter:` tags (title, description, a 1200x630 `og.png`) and a no-script redirect to the share page. A revoked link redirects too, with status 404, so the page can explain. |
| `GET /shares/{token}` | `{title, style, shots: [{number, framing, action, dialogue, duration_ms, image_url}], animatic: {url, duration_ms} \| null, public}`. Media URLs are under `/shares/{token}/`. |
| `GET /shares/{token}/panels/{n}`, `/animatic`, `/og.png` | The panel as shown, the animatic (with `Range` support) and the preview image. |

**Unlisted by default.** Until the owner ticks "Make public", every share response carries `X-Robots-Tag: noindex, nofollow`, the stub has a robots meta tag and the studio's share page adds one, so search engines leave it out. Link previews on X still work: noindex keeps a page out of search results, not out of preview crawlers. A public link drops all three. On staging the whole studio is noindex (`STUDIO_NOINDEX=1`), public or not.


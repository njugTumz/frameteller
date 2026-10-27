# Live session WebSocket

The REST API is described by [`backend/openapi.json`](../backend/openapi.json) (also served at `/docs` by a running backend). OpenAPI cannot describe WebSocket messages, so they are documented here. Message shapes come from `backend/src/frameteller/interface/dto.py` (`event_message`).

```
ws(s)://<backend>/ws/projects/{project_id}/session
```

One live session per project at a time. Browsers must connect from an origin in `ALLOWED_ORIGINS`.

## Client → server

| Message | When | Shape |
|---|---|---|
| Start | First message, within 10 s | JSON `{"mode": "narrate" \| "co_direct", "keywords": ["Mira", ...]}` |
| Audio | Then, repeatedly | **Binary** frames of raw PCM, signed 16-bit little-endian, mono, **24 kHz**. Even length, at most 32,768 bytes (about 0.34 s). Send at real-time pace. |
| End | When the narrator is done | JSON `{"type": "end"}` |

- `mode` is fixed for the session. `narrate` uses low-latency turn endpointing; `co_direct` adds speaker labels (`A`, `B`) but only closes a turn when the speaker changes or the stream ends. In our measurement, one narrator gave a single 42-second turn (see the [findings](spikes/2026-10-28-findings.md)).
- `keywords` (at most 50, each trimmed to 40 characters) bias recognition towards character and place names.
- Invalid frames are dropped, and the server reports that once with a non-fatal `error`.
- A session stops by itself after **55 minutes** of audio.

## Server → client

Every server message is JSON with a `type`.

| `type` | Fields | Meaning |
|---|---|---|
| `session.started` | `mode` | Start message accepted; send audio. |
| `transcript.partial` | `text` | Cumulative text of the turn in progress. **Replace** the previous partial; never append. |
| `turn.completed` | `turn: {id, text, start_ms, end_ms, speaker}` | A finished turn with the final text. `start_ms`/`end_ms` are positions in the audio and drive animatic timing. `speaker` is `null` in `narrate` mode. |
| `shot.created` | `shot: {id, number, framing, character_ids, setting, action, dialogue, duration_ms, source_turn_ids, panel: null}` | The director turned a turn into a shot (one or more per turn). |
| `cast.proposed` | `characters: [{id, name, description, reference_url}]` | New characters with freshly drawn reference sheets. Show them, then `POST /projects/{id}/cast/approve`. |
| `job.updated` | `kind, key, status, shot_id, revision, message` | Background work: `kind` is `generate_cast`, `generate_panel`, `pre_segment_panel` or `edit_panel`; `status` is `queued`, `running`, `succeeded` or `failed`. `message` is user-facing, on failure. |
| `error` | `message, fatal` | Something went wrong. `fatal: false` means the session carries on (for example, one turn could not be directed). `fatal: true` means it has ended. |
| `session.ended` | `turns, shots` | The narration is fully transcribed and directed. |

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

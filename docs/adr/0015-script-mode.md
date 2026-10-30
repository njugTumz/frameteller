# ADR 0015: Script mode: the teleprompter and "Read it to me"

- **Status:** Accepted
- **Date:** 2026-10-29
- **Deciders:** Isaac Tumuti
- **Builds on:** [ADR 0002](0002-incremental-direction.md) (one turn directed at a time), [ADR 0008](0008-reliable-beats.md) (beats cut shots)

## Context

Narrating is the fastest way to tell a story that is not written yet. Many creators already have one written: a pitch script, an episode outline, a screenplay. Asking them to improvise it again, and to press Space for every shot, throws that work away. Some also want the animatic narrated by a voice rather than their own, or in another language.

The studio needs three ways to tell a story, chosen on the start screen:

1. **Narrate** (exists): make it up out loud, Space for each shot.
2. **Teleprompter**: paste or upload a script, then read it aloud while it scrolls. The animatic uses the reader's recording.
3. **Read it to me**: paste or upload a script, pick a voice and a language; the user doesn't speak. The animatic uses the synthesized narration.

## Decision

### One script format for both modes

`domain/script.py` parses `.txt`, `.md` and `.fountain` without a new dependency (`.docx` would need one, so it is left out; paste its text instead).

- Each paragraph is one **beat**, so one turn for the director.
- **Framing cues** ("Wide shot.", "Close-up.", "Slow push-in.") are kept in the beat's `direction`, which the director reads, and left out of its `narration`, which is spoken and captioned. A paragraph that is only a cue directs the next one.
- A line `Episode N` (also `EPISODE N`, `Ep. N`, with an optional title) starts an **episode**. Episodes share the cast. Shot numbers stay global in the domain, and the studio numbers them from 1 within each episode.
- **Fountain:** the title page, transitions, notes, boneyard, sections and synopses are dropped. A scene heading becomes "Scene: …" in the next beat's direction, and dialogue becomes `Name says: …`.
- **Public-demo limits:** 4,000 characters, 3 episodes and 12 shots per episode. `accept_script` checks them before any model call, with a message that says what to change. The director's refusal of real people and franchise characters applies to every turn, scripted or not.

`TranscriptTurn` gains `direction` (what the director reads: the paragraph with its cues) and `episode`. `text` stays what was spoken, and `turn.for_director` picks the direction when there is one.

### Teleprompter: follow the reader, cut at the end of each paragraph

Speech-to-text stays on Muse Voice Transcribe. The session already collects every word heard since the last cut (`_Heard`). In teleprompter mode, after each partial, audio progress or turn event, `application/teleprompter.py` matches the end of the current paragraph against those words:

- **Fuzzy matching:** words are normalised (lowercase, no accents, digits spelled out) and compared with a similarity ratio of at least 0.72. Short words must match exactly. "Lena" heard as "Lina" still matches.
- **When a paragraph counts as read:** at least 60% of its last 5 words were heard in order, including one of the last two, and the reader has said at least half as many words as the paragraph has. At least half of all the paragraph's words must also have been heard in order: on staging, a recording read against the wrong script matched one tail by chance ("all" heard in "alley", "it" later) until this check was added. Saying the last words too early ("the old antenna" alone) does not count. A misheard final word ("ruf" for "roof") stays with its paragraph.
- **When the beat is cut:** once the end is covered, the beat is cut when the transcriber hears a pause (its `speechEnd`, or 600 ms of audio with no new words), when the reader reads on into the next paragraph (2 or more words past the end), or when the stream ends.
- **Timing:** the cut time is the first audio position after the end was heard, or the end of the speech when that is later. So panel timing follows the voice, as with beats.
- **Space** still cuts by hand. A Space press within 2.5 s of an automatic cut, before any new words were spoken, only confirms that cut, so a reader who is used to pressing Space does not create an empty shot.

The turn's text is the script's own words: captions and the transcript rail show what was written, not what was misheard.

### Read it to me: Azure Text-to-Speech, synthesized one paragraph ahead

- **Service:** Azure AI Speech over REST, not the Speech SDK (a large native dependency). SSML goes in, and `riff-24khz-16bit-mono-pcm` comes out: the same 24 kHz mono 16-bit PCM as our recordings, so the animatic treats a synthesized narration like a recorded one.
- **Key, not identity:** keyless auth (the Container Apps' managed identities with "Cognitive Services Speech User") was the plan. The Speech resource is in a tenant our deployment identity cannot see, so the key is a Container App secret (`AZURE_SPEECH_KEY`), set from the GitHub environments. Without it, `/voices` says `available: false` and the studio offers the other two ways.
- **Voices:** a curated set of five multilingual neural voices: Ava (the default since v1.1.0; Brandon was before), Brandon and Andrew (US), and Ada and Ollie (UK). Each lists only the languages it can speak among English, French, Spanish, Hindi, Arabic and Portuguese. The voice list is fetched once and cached in storage. Previews are synthesized once per voice and language, then kept.
- **Translation:** for a language other than English, Muse Spark translates the narration text of each episode first, checked one for one. The director still reads the original paragraph, so shots and panels follow the author's meaning. The transcript rail shows the translated text, because that is what the voice says. If translation fails, the episode is read as written and the studio says so.
- **Pacing:** `ReadScript` stays one paragraph ahead of playback. The browser plays each clip as it arrives (`script.voiced`); each turn lasts exactly as long as its audio, and the turns are laid end to end.
- **Episodes:** between episodes the reading pauses (`script.paused`, reason `episode`; the studio shows "Episode 2 is next"). It waits until every turn of the finished episode is directed and every shot from them has a drawn or failed panel. A Continue skips the wait, and after 3 minutes it goes on anyway. Pause and Continue work at any time, at paragraph boundaries.
- **Caching:** audio is cached per text, voice and language (`projects/{id}/speech/{sha}.wav`), so reading the same story again costs nothing. At the end, the whole reading is stored as the project's narration with its voice and language, and the share page says which voice narrated it.
- **Guardrails:** synthesized characters count toward a per-visitor daily cap (12,000) and a cap for all visitors together (`SPEECH_CHARACTERS_PER_DAY`, 200,000). The cost (USD 15 per million characters) is charged to the budget guard before each call.

## Consequences

- The animatic and share links work the same way in all three modes, because every mode produces timed turns and one narration WAV.
- Renders per story rise from 30 to 60, so that 3 episodes of 12 shots can all be drawn and edited.
- Teleprompter matching is heuristic. A reader who skips a paragraph's ending is not cut until they read on 2 words or press Space. The tests cover misheard, dropped and early words.
- A second provider (Azure) joins the stack, for narration only. Speech-to-text stays on Muse Voice Transcribe (CLAUDE.md section 4).

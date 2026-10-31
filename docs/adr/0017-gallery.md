# ADR 0017: The public gallery

- **Status:** Accepted
- **Date:** 2026-10-29
- **Deciders:** Isaac Tumuti
- **Builds on:** [ADR 0011](0011-animatic-export.md) (animatic export), [ADR 0012](0012-continuity-supervisor.md) (rubrics and the reviewer)

## Context

The Community Vote and the X posts need one place where anyone can watch what people made with Frameteller. Anything public must respect the hackathon's rights rule: no real people, no franchise characters, nothing a family audience should not see. And creators must stay in control of their own work.

## Decision

### Where it lives: a studio route, `app.frameteller.com/gallery`

The other option was a static page on the marketing site that fetched a public API. A studio route is simpler, because the studio already has:

- the typed API client generated from OpenAPI,
- the visitor id that hearts need,
- the shared UI components,
- Vitest coverage,
- a CSP that allows the API.

On the marketing site we would have to rebuild all of that, or loosen its CSP. `frameteller.com/gallery` redirects (301) to the studio's gallery. The page loads on demand, so the studio's first load does not grow.

### Submit with consent

"Submit to gallery" sits beside Share. The creator ticks a consent statement (original story, no real people or franchise characters, shown publicly, can be withdrawn) and chooses the audio:

- **my voice**: the kept narration;
- **the Ava voice instead** (Brandon before v1.1.0): Azure Text-to-Speech reads each shot's caption, cut to the shot;
- **no audio**.

The backend refuses without consent, before every shot has a panel, or with "my voice" when the recording was not kept.

The gallery keeps **its own copy**: an animatic with burned-in captions and the chosen audio, plus a cover copied from the first panel, under `gallery/<entry>/`. Later edits to the project never change what the gallery shows, and withdrawing deletes exactly that copy. A submission counts as one of the project's exports.

### Automatic moderation, a person for the doubtful ones

A background job (in the export lane, ADR 0016) renders the copy, then the continuity supervisor's reviewer checks it against a new rubric, [`agents/gallery.md`](../../agents/gallery.md). The rubric bans real people, franchise characters, sexual, hateful or violent content, war and politics, personal details, and spam. The reviewer sees a contact sheet of the first six panels, and as the subject the title, the cast and the story as told.

- **Who reviews:** the configured reviewer. In production that is Spark, with Glimmer screening while it is warm and Spark confirming whatever Glimmer flags.
- A **pass with confidence ≥ 0.7 and no blocker or major issue** publishes the entry and makes its share page indexable.
- **Anything else** (ask, fix, low confidence, the check failing to run) leaves it **pending** for the admin. The creator sees "A person will look at it", never the reviewer's own words.
- The verdict's model is recorded on the entry, and the rubric file's hash is recorded as with every review.

### The page, hearts, reports, the admin

- **Cards:** title, cover, style, episode count, shot count and length. Playing a card swaps the cover for the video. Each card links to its share page.
- **Filters:** Featured or Newest, by style.
- **Hearts:** one per browser (a hash of the browser id).
- **Reports:** one per visitor. Three distinct reports hide an entry until the admin decides.
- **Admin:** `app.frameteller.com/admin#<ADMIN_TOKEN>` (bearer token, fragment only). It shows today's budgets and queues, then pending and reported entries first: watch, publish, feature, hide, remove.
- **Indexing:** `GET /gallery/sitemap.xml` lists the gallery and every published share page, and the studio's `robots.txt` points to it.

### Storage

The gallery is one JSON document (`gallery/index.json` in the projects container), changed with ETag optimistic concurrency, like projects are. At hackathon scale (hundreds of entries), one read serves the whole listing. `GalleryRepository` is a port, with file and blob adapters.

## Consequences

- Nothing reaches the public gallery without passing the rubric or a person's look. A missed case can still be reported, and three reports hide it.
- The Ava voice is trimmed to each shot's length. Text read faster than it was spoken fits, but a long caption over a short shot is cut off. Narrated stories usually fit, because the caption is what was said in that time.
- One document for the whole gallery keeps reads cheap and writes simple. With thousands of entries it would need an index per entry and paging.

## Amendment (Oct 31, 2026): reserved names are decided by a rule, not a model

The moderation review (GAL-08) judged "Frameteller team" once as fine and once as doubtful, for the same story. Brand names are now a fixed rule:

- **Reserved:** "Frameteller", "Frameteller team", "Frameteller official", "Meta", "Muse" and "Cerebral Valley". Matching ignores case, spaces and punctuation (after NFKC), so "frame-teller TEAM" and full-width letters match too.
- **From a creator:** a reserved name always goes to `pending` with the note "GAL-08: The name is reserved for official entries…", before any model is asked. The creator is told the name is reserved. Signing one again, even unchanged, is held again.
- **From the admin console:** publishing an entry, or changing its name there (`PATCH /admin/gallery/{id}`, no new check), marks a reserved name `official`. The public gallery card and share page show an "Official" badge. Any later edit by the creator removes `official`.

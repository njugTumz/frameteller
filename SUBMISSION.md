# Submission draft

Working copy of every field in the hackathon submission form (CLAUDE.md section 10). Keep it updated as we build; paste from here on Nov 4.

**Deadline:** Wed Nov 4, 9:00 PM ET = **Thu Nov 5, 6:00 AM UTC+4**. Also claim Meta credits before then.

## Checklist

- [ ] Team name
- [ ] Team members
- [x] Track
- [x] Problem statement
- [ ] X post link
- [ ] Project description
- [ ] 3-minute demo video (checked in an incognito window)
- [ ] Use of Meta products
- [ ] Why Meta's models are important
- [ ] Feedback on Meta products (optional)
- [ ] Feedback on partner technologies (optional)
- [ ] Repo public and accessible; production URL live
- [ ] Tag `v1.0-submission` and freeze production until at least Nov 16

---

## Team name

TODO (working name: Frameteller)

## Team members

- Isaac Tumuti (Representative)
- TODO: anyone else who worked on it (max 4)

## Track

Indie Developer

## Problem statement

Build for Your World

## X post link (Most Viral)

TODO: the single hero post (launch post on Nov 2).

## Project description

**Draft:** Frameteller turns spoken stories into editable storyboards and timed animatics. You talk through a scene; Frameteller transcribes you live, works out the shots, draws storyboard panels where the same character looks the same in every frame, and lets you fix any panel by voice or by clicking an object in it. When you are done, it exports an animatic timed to your own narration, plus a PDF storyboard sheet.

Storyboarding is slow, manual work that sits between having an idea and making it. Indie filmmakers, YouTubers, animators, comic and game writers, and pitch teams can describe a scene in a minute but take hours or days to sketch it. Frameteller gets them from a spoken idea to a reviewable, timed animatic in minutes.

TODO: add measured time saved from a real test run.

## Demo video

TODO: YouTube URL (public or unlisted).

## Describe your use of Meta products

**Draft:**

- **Muse Voice Transcribe 1.0** hears the story: realtime streaming ASR with turn detection and speaker labels, so two people can co-direct. Turn timestamps set each panel's duration in the animatic.
- **Muse Spark 1.3** directs: structured output turns transcript turns into a validated shot list (scenes, shots, framing, characters, setting, action, dialogue) and maintains a character bible. It also routes voice commands ("make the cat bigger in shot 3") into edit operations via tool calls. The system prompt and character bible are a stable prefix for prompt caching.
- **Muse Image 1.0** draws: a reference sheet per character first, then every panel generated from those references for consistency, and multi-turn edits for voice fixes.
- **SAM 3.1** selects: clicking an object in a panel sends a point prompt, and SAM returns that object's cut-out. Moves, resizes, swaps and deletes transform the SAM cut-out on our canvas. Appearance changes ("her coat is red now") are whole-panel Muse Image edits that name the selected object, chained with `previous_response_id`. In our tests the rest of the panel kept its layout (at most 0.6% structural change outside the selected object), though fine texture such as rain is redrawn.

TODO: re-measure edit stability on the final pipeline, add stretch models (Glimmer, Wonder) if shipped.

## Why Meta's models are important

**Draft:** Frameteller needs to hear, direct, draw and select, and Meta's models cover all four as one stack behind one API. Consistency and editability are only possible because they work together: Spark's character bible feeds Muse Image references, so characters stay the same across panels; SAM picks out the object you clicked so we can move, swap or delete it on the canvas, and Muse Image's multi-turn edits change that named object's appearance while the rest of the panel keeps its layout; Voice Transcribe's turn timestamps drive the animatic timing.

TODO: tighten after the demo is built.

## Feedback on Meta products (optional)

TODO: paste from [FEEDBACK.md](FEEDBACK.md).

## Feedback on partner technologies (optional)

TODO: paste from [FEEDBACK.md](FEEDBACK.md) (Fireworks, Modal, Baseten).

## Links

- Repository: https://github.com/njugTumz/frameteller
- Production: TODO
- Marketing page: https://frameteller.com (the earlier https://gentle-stone-032869c0f.3.azurestaticapps.net redirects there)

# CLAUDE.md — Frameteller

Project brief and working rules for coding agents (Muse Code, Claude, others) and humans.
Read this whole file before making changes. When a decision here changes, update this file in the same commit.

> "Frameteller" is a working name. Change it in one place per surface: `marketing/index.html` (CONFIG) and `frontend/src/config.ts`.

---

## 1. What we are building

**Frameteller turns spoken stories into editable storyboards and timed animatics.**

You talk through a scene. Frameteller listens live, works out the shots, draws consistent storyboard panels, lets you fix any panel by voice or by clicking an object in it, and exports an animatic timed to your own narration.

Target users: indie filmmakers, YouTubers, animators, comic and game writers, ad and pitch teams. Anyone who can describe a scene faster than they can draw it.

### Core flow (the demo)

1. **Speak** — the user narrates ("Scene one. Night, a rainy alley. A girl in a yellow raincoat finds a glowing cat…"). Muse Voice Transcribe streams the transcript live, with turn detection and speaker labels (two people can co-direct).
2. **Direct** — Muse Spark 1.3 (structured output) turns transcript turns into a shot list: scenes → shots, each with camera framing, characters, setting, action and dialogue. It maintains a **character bible** (one canonical description per character).
3. **Draw** — Muse Image generates a reference sheet per character first, then every panel using those references, so characters stay consistent across panels.
4. **Refine** — voice commands ("make the cat bigger in shot 3", "swap shots 2 and 4", "her coat is red now") are routed by Spark into edit operations. Clicking an object runs SAM 3.1 to segment it so it can be moved, swapped or edited in isolation.
5. **Export** — an MP4 animatic (ffmpeg) where each panel's duration comes from the transcript turn timestamps and the user's own recording is the scratch narration track. Also a PDF storyboard sheet.

The "wow" moments to protect: **(a)** live speech becoming panels, **(b)** the same character looking the same in every panel, **(c)** "I talked for 60 seconds and got a timed animatic".

---

## 2. Hackathon facts (Meta Global AI Developer Hackathon)

### Key dates

Times below are Eastern Time; the team is in UTC+4. US clocks change on **Nov 1**, so ET is UTC−4 until then and UTC−5 after.

| What | ET | UTC+4 (team) |
|---|---|---|
| Office hours (weekdays, Discord #office-hours) | 10–11 AM | 6–7 PM to Oct 30; 7–8 PM from Nov 2 |
| **Our public live demo (marketing countdown target)** | **Mon Nov 2, 12:00 PM** | **Mon Nov 2, 9:00 PM** |
| Last full day for submission questions | Tue Nov 3 | Tue Nov 3 |
| **Submission + Meta credit claim deadline** | **Wed Nov 4, 9:00 PM** | **Thu Nov 5, 6:00 AM** |
| Judging | Nov 5–8 | Nov 5–8 |
| Closing ceremony, top 5 per track live | Mon Nov 9, 12:00 PM | Mon Nov 9, 9:00 PM |
| Community vote winner announced | Mon Nov 16 | Mon Nov 16 |

### Hard rules (breaking these disqualifies us)

- **Must use Meta's models** (Stage 1 pass/fail: fits a problem statement and reasonably uses Meta Model API and/or Meta open-weight models).
- **Repository must be public.**
- **New work only.** Everything demoed must be built during the event (Oct 26 – Nov 4). Judges must be able to clearly identify what we built. Commit history is evidence.
- **Max 4 people per team.** One Representative submits. Everyone who worked on it is listed.
- **Only code, data and assets we have rights to.** No copyrighted characters, franchises, logos or music in demos, samples or tests. Invent original characters.
- **Avoid the anti-project list**: medical/mental-health advice, basic RAG, simple image analyzers, simple AI-for-education chatbots, job screeners, nutrition coaches, personality analyzers, sports analyzers/coaches, anything political or involving war. Frameteller is none of these; keep demo stories clear of politics and war.

### Our submission

- **Track:** Indie Developer (switch to Startups only if we enter as a startup).
- **Problem statement:** Build for Your World (creators turning their own ideas into visual stories, freeing time from manual sketching).
- **Bonus prizes we target:** Best Creative Build ($5K, requires Muse Image or Muse Wonder), Most Viral on X ($20K), Community Vote ($10K), stretch: Best Open-Weight Build ($10K) via Glimmer.

---

## 3. How we are judged, and what that means for the build

Stage 1 pass/fail → Stage 2 scored 0–10 per category → Stage 3 top 5 per track judged live from the demo video.

| Criterion | Weight | What earns it for Frameteller | Build implication |
|---|---|---|---|
| **Impact** | 30% | Real creators, real time saved: a storyboard in minutes, not days. | Demo a believable creator scenario end to end. State who uses it and the time saved. |
| **Use of Meta AI tooling** | 25% | Four Meta models, each doing a distinct job (hear, direct, draw, select), plus reference-based consistency and SAM-driven edits. Stretch: Glimmer local router. | Every model must be visibly load-bearing in the demo, not decorative. Show the model doing the work on screen. |
| **Technical depth & execution** | 20% | Clean architecture, typed contracts, streaming, async jobs, retries, cost guardrails, CI/CD with staging and production. | Code quality is judged. Follow section 6 strictly. README explains the architecture. |
| **Demo** | 25% | A live, working product and a genuinely fun 3-minute video. | Production must be live and stable. Optimise the first 20 seconds of the video. |

**Rule of thumb for every feature:** if it does not make the 3-minute demo better or make a model visibly more useful, it is P2.

---

## 4. Scope

### P0 — must ship by Nov 2 live demo
- Live mic capture → realtime transcript on screen.
- Transcript → shot list (structured output, validated).
- Character bible + reference sheet per character.
- Panel generation with character references; storyboard grid UI.
- Voice edit of a single panel (multi-turn image edit).
- Animatic MP4 export with narration audio and turn-timed panels.
- Deployed to production on Azure, with staging.

### P1 — ship by Nov 3
- Click object → SAM 3.1 mask → targeted edit / move / swap.
- Reorder and delete shots by voice.
- Two-speaker co-direction (speaker labels shown).
- PDF storyboard export. Shareable read-only project link (for X and the gallery).

### P2 — only if everything above is solid
- Glimmer local voice-command router (open-weight bonus).
- Muse Wonder "story doctor" pass (pacing and continuity suggestions).
- Style presets (pencil rough, ink, colour).

---

## 5. Meta models we use

Base URL `https://api.meta.ai/v1`, auth `Authorization: Bearer $MODEL_API_KEY`. Model API is OpenAI-SDK compatible: use the `openai` Python SDK with `base_url` set. Prices below are from the console; chat prices are assumed per 1M tokens.

| Role in Frameteller | Model ID | Endpoint | Cost |
|---|---|---|---|
| Hear (live transcript) | `muse-voice-transcribe-1.0` | `wss://api.meta.ai/v1/asr/realtime` (live), `POST /v1/asr/transcribe` (files) | $0.18 / hour |
| Direct (shot list, edit routing) | `muse-spark-1.3` | `POST /v1/responses` (structured output, tool calls) | $1.25 in / $0.15 cached / $4.25 out |
| Direct, cheap dev mode | `muse-spark-1.3-contributor` | same | $0.10 / $0.002 / $0.20 — select countries only; inputs/outputs used for training. **Dev and synthetic data only, never user data.** |
| Draw | `muse-image-1.0` | `/v1/images/generations`, `/v1/images/edits`, multi-turn via Responses API | $0.01 / image |
| Select objects | `sam-3.1` | `POST /v1/responses`, `POST /v1/files` | $2.50 / 1K images, $0.20 / 1K video frames |
| Optional heavy reasoning | `muse-wonder-1.0` | `POST /v1/responses` | $4 / $0.20 / $20 — use sparingly |
| Optional open-weight | Muse Glimmer (30B, Apache 2.0, single GPU) | self-hosted (vLLM / llama.cpp) on Modal or Baseten | partner credits |

Not used: Muse Wonder Full (Muse Code subscription only), Muse Spark 1.1/1.2 (same price as 1.3, older).

### Facts and limits to respect
- Voice Transcribe returns **turn-level timestamps, not word-level**. Animatic timing is per turn.
- Muse Image returns base64 or a **signed URL**: persist every image to Blob Storage immediately; never store the signed URL as the source of truth.
- Prompt caching: keep the system prompt and character bible as a **stable prefix** at the start of every Spark request.
- Budget: $150 Meta credits per person. Spend limit set on the Billing page.

### Verify on day 1 (do not assume)
- [ ] Does `/v1/images/edits` accept a mask? If yes, SAM masks drive targeted edits. If no, fall back to region-described edit prompts.
- [ ] How well do reference images hold a character across 6+ panels? Measure before building UI.
- [ ] Realtime ASR audio format (sample rate, encoding, chunk size) and session limits.
- [ ] Rate limits per model on our account.

Docs sections worth reading: Quickstart, Capabilities (Speech to text, Image generation, Media segmentation, Structured output, Prompt caching, Tool calling), Protocols, Agent guides, Get unblocked, Pricing and rate limits, API reference.

---

## 6. Architecture — Clean Architecture

We use **Clean Architecture** with **SOLID** principles and standard system design practice. The dependency rule is absolute: **source code dependencies point inward only.**

```
            ┌──────────────────────────────────────────────┐
            │ interface   FastAPI routes, WebSockets, DTOs  │
            │  ┌────────────────────────────────────────┐  │
            │  │ infrastructure  Meta API clients, Blob, │  │
            │  │                 ffmpeg, config, logging │  │
            │  │  ┌──────────────────────────────────┐   │  │
            │  │  │ application  use cases + ports    │   │  │
            │  │  │  ┌────────────────────────────┐   │   │  │
            │  │  │  │ domain  entities, rules     │   │   │  │
            │  │  │  └────────────────────────────┘   │   │  │
            │  │  └──────────────────────────────────┘   │  │
            │  └────────────────────────────────────────┘  │
            └──────────────────────────────────────────────┘
```

### Layers (backend, Python)

- **domain/** — pure Python, no I/O, no framework imports. Entities and value objects: `Project`, `Scene`, `Shot`, `Panel`, `Character`, `CharacterBible`, `TranscriptTurn`, `ObjectMask`, `Animatic`. Domain rules (e.g. a shot references only characters in the bible; panel order is contiguous).
- **application/** — use cases, one class per use case, each with a single `execute()`:
  `StartTranscriptionSession`, `DirectStoryFromTranscript`, `BuildCharacterBible`, `GenerateCharacterReference`, `GeneratePanel`, `EditPanelByCommand`, `SegmentObjectInPanel`, `ReorderShots`, `ExportAnimatic`, `ExportStoryboardPdf`.
  **Ports** (abstract interfaces) live here: `SpeechToTextPort`, `DirectorPort`, `ImageGenerationPort`, `SegmentationPort`, `MediaStoragePort`, `ProjectRepository`, `JobQueuePort`, `VideoRendererPort`, `Clock`, `IdGenerator`.
- **infrastructure/** — adapters implementing ports: `MetaVoiceTranscribeAdapter`, `MetaSparkDirectorAdapter`, `MetaImageAdapter`, `MetaSamAdapter`, `AzureBlobMediaStorage`, `BlobProjectRepository`, `FfmpegVideoRenderer`, settings, logging, telemetry. Optional later: `GlimmerCommandRouterAdapter`.
- **interface/** — FastAPI app, HTTP routes, WebSocket handlers, request/response DTOs (Pydantic), dependency wiring (composition root). No business logic here.

Swapping a model or a storage provider must only touch `infrastructure/` and the composition root.

### Frontend (React + Vite + TypeScript + Tailwind)

```
frontend/src/
  app/            routing, providers, layout
  features/       one folder per feature: recording/, storyboard/, panel-editor/, export/
    <feature>/components, hooks, api.ts, store.ts
  shared/         ui primitives, api client, types generated from backend OpenAPI
  config.ts
```

- Components render; hooks orchestrate; `api.ts` talks to the backend. No business logic in components.
- State: Zustand, one store per feature. Server state via a typed client generated from the FastAPI OpenAPI schema.
- Canvas: react-konva for panels, masks and drag/recompose.
- Audio: AudioWorklet → PCM chunks → backend WebSocket. **The browser never talks to Meta APIs directly.**

### Repository layout

```
/
  CLAUDE.md  README.md  LICENSE (MIT)  SUBMISSION.md  FEEDBACK.md  .env.example  .gitignore
  backend/   pyproject.toml  src/frameteller/{domain,application,infrastructure,interface}/  tests/
  frontend/  package.json  vite.config.ts  src/
  marketing/ index.html  updates.json        # public landing page with countdown + build log
  infra/     main.bicep  modules/  parameters/{staging,production}.bicepparam
  .github/workflows/  ci.yml  deploy-staging.yml  deploy-production.yml  deploy-marketing.yml
  docs/      architecture.md  adr/  demo-script.md
```

### System design practices (required)

- **Typed contracts everywhere.** Pydantic models for every API boundary and every LLM structured output; validate model output and retry once with the validation error on failure.
- **Async jobs for slow work.** Image generation, segmentation and export run as background jobs (`JobQueuePort`) with status pushed to the client over WebSocket. Never block a request on image generation.
- **Idempotency.** Jobs carry an idempotency key (project + shot + revision) so retries never double-charge credits.
- **Resilience.** Every external call has a timeout, bounded retries with exponential backoff and jitter, and a clear error mapped to a user-facing message. Circuit-break a model that keeps failing; degrade gracefully (e.g. no-mask edits if mask edits fail).
- **Cost guardrails.** Per-project and per-day budget counters in the application layer; SAM on video samples at 2–5 fps; Wonder only behind an explicit flag; cache stable prompt prefixes.
- **12-factor config.** All config from environment variables via a settings class. Nothing environment-specific in code.
- **Persistence.** Media and project documents in Azure Blob Storage behind `MediaStoragePort` / `ProjectRepository`. Container disk is ephemeral; never rely on it.
- **Observability.** Structured JSON logs with a request ID and project ID on every line; OpenTelemetry traces to Application Insights; log model name, latency, tokens and cost per call. Never log secrets or raw audio.
- **Health.** `/healthz` (process up) and `/readyz` (dependencies reachable) for Container Apps probes.
- **Security.** Rate-limit public endpoints, validate upload size/type, CORS restricted to our frontend origins, no user-supplied URLs fetched server-side.
- **Architecture decisions** recorded as short ADRs in `docs/adr/`.

### Testing

- Domain and application: pytest unit tests using in-memory fake adapters for every port. No network in unit tests.
- Infrastructure: contract tests per adapter against recorded fixtures; a small opt-in live suite (`pytest -m live`) that uses real credits.
- Frontend: Vitest + Testing Library. Playwright smoke test against staging after each deploy.
- CI fails on lint (ruff, eslint), type errors (mypy, tsc) or tests.

---

## 7. Environments and deployment (Azure + GitHub Actions)

No hosting is mandated by the hackathon; we use Azure.

| Piece | Service | Notes |
|---|---|---|
| App frontend | Azure Static Web Apps | PR preview environments |
| Marketing page | Azure Static Web Apps (separate app) | Deploys on any push to `main` touching `marketing/**` |
| Backend | Azure Container Apps | WebSockets on, scale to zero, health probes |
| Media + project docs | Azure Blob Storage | Private containers, SAS for reads |
| Secrets | Key Vault / Container Apps secrets | `MODEL_API_KEY` never in the repo |
| Images | GitHub Container Registry | Free for public repos |
| Telemetry | Application Insights | |

One resource group per environment: `rg-frameteller-staging`, `rg-frameteller-prod`, same Bicep with different parameter files.

**Pipelines**
- `ci.yml` — on `pull_request` (never `pull_request_target`) and push: lint, type-check, test both apps.
- `deploy-staging.yml` — on push to `main`: build and push image, deploy backend and frontend to staging, run Playwright smoke.
- `deploy-production.yml` — on published release: GitHub `production` environment with required manual approval.
- `deploy-marketing.yml` — on push to `main` with changes in `marketing/**`.
- Azure auth via **OIDC federated credentials** (`azure/login`), no stored Azure passwords.
- Separate Meta Model API keys for staging and production if the console allows.
- Azure budget alerts and the Meta Billing spend limit both set.

**Freeze:** after submitting, tag `v1.0-submission`, stop deploying to production, and keep it up unchanged **until at least Nov 16** (judging, finals, community vote).

---

## 8. Public repo and commit rules

The repo is public from day one and judges read the commit history.

- `.gitignore` excludes `.env*` (except `.env.example`), keys, local media, `node_modules`, venvs. `.env.example` has names only.
- **Never** put secrets in a `VITE_*` variable: Vite bakes those into the public bundle. All model calls go through the backend.
- Secrets live only in GitHub Environments and Azure. Secret scanning and push protection on.
- If a secret is ever committed: **rotate it immediately**. Deleting it does not remove it from history.
- Branch protection on `main`; approval required for workflows from outside contributors.
- Bicep and workflows reference subscription/tenant/resource names via GitHub variables, not hardcoded.
- **Conventional Commits** (`feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`, `ci:`), small and frequent, messages say what changed.
- **No squash merges and no force-pushes to `main`.** Use merge commits so granular history stays visible.
- Commit author email = the author's GitHub account email. Authors must match the people listed on the submission.
- Tool-generated scaffolding (e.g. `npm create vite`) gets its own commit saying so.
- Only original assets: sample stories, test audio, character art and music must be ours or generated by us. MIT `LICENSE` in the root.
- README has a **"Built during the hackathon (Oct 26 – Nov 4, 2026)"** section listing what we built.

---

## 9. Schedule (team time, UTC+4)

| Day | Goal |
|---|---|
| Tue Oct 27 | Repo, licence, CI, Azure skeleton. Marketing page live with countdown. First X post. |
| Wed Oct 28 | Spikes in plain scripts: voice → shot JSON; character consistency across 6 panels; SAM mask → edit. Decide fallbacks. |
| Thu Oct 29 – Fri Oct 30 | Domain + use cases + adapters; storyboard UI; live mic streaming. Staging up. |
| Sat Oct 31 – Sun Nov 1 | Voice edits, animatic export, hardening, Playwright smoke. |
| **Mon Nov 2, 9 PM** | **Public live demo on production. Countdown hits zero. Launch post on X.** |
| Tue Nov 3 | P1 features, polish, README, record demo video, draft all submission answers. |
| Wed Nov 4 | Buffer, final checks, submit well before **Thu Nov 5, 6:00 AM**. Tag and freeze. |

---

## 10. Submission form checklist

Keep `SUBMISSION.md` updated as we build; paste from it on Nov 4.

- [ ] **Team name** — required.
- [ ] **Team members** — everyone who worked on it.
- [ ] **Track** — Indie Developer.
- [ ] **Problem statement** — Build for Your World.
- [ ] **X post link** (Most Viral) — the single hero post.
- [ ] **Project description** — what it does and the problem it solves.
- [ ] **3-minute demo video** — YouTube, public or unlisted, checked in an incognito window.
- [ ] **Describe your use of Meta products** — each model, what it does in the pipeline, and how (references, multi-turn edits, structured output, realtime ASR, SAM masks).
- [ ] **Why Meta's models are important** — one coherent stack covering hearing, directing, drawing and selecting; consistency and editability are only possible because these models work together.
- [ ] **Feedback on Meta products** (optional) — from `FEEDBACK.md`.
- [ ] **Feedback on partner technologies** (Fireworks, Modal, Baseten; optional) — from `FEEDBACK.md`.
- [ ] Repo public and accessible; production URL live.

**`FEEDBACK.md` habit:** whenever something about a Meta model, the docs, or a partner (Baseten, Modal, Fireworks) is confusing, slow or great, add a dated one-line entry. Concrete details make that feedback field stand out.

### Demo video outline (3:00)
- 0:00–0:15 Hook: speak a scene, panels appear.
- 0:15–0:40 Problem and who it is for.
- 0:40–2:10 Live walkthrough: speak → shot list → consistent panels → voice edit → click-to-select edit → animatic.
- 2:10–2:40 How it works: the four Meta models and the architecture, in one diagram.
- 2:40–3:00 What we built during the hackathon, and the live URL.

---

## 11. Viral and community plan

- **Marketing page** (`marketing/`) is live from day one: what Frameteller is, a countdown to the **Nov 2, 12:00 PM ET (9:00 PM UTC+4)** live demo, how it works, the Meta models used, and a **live build log**.
- **Live build log:** append an entry to `marketing/updates.json` (newest first) and push to `main`. The deploy workflow publishes it and open pages pick it up within a minute. Post an update at least once a day.
- **On X:** daily build clips (native video, 15–45 s), each linking to the marketing page. On Nov 2, the launch post with a 30–60 s native video and the live link. Invite replies with story ideas and post the storyboards we make from them.
- **Hero post:** one post's link goes in the submission. Ask in Discord #questions whether only that post counts, the engagement end date, and whether reposts count. Engagement must be organic.
- After submission, share the gallery link for the Community Vote (closes Nov 16).

---

## 12. Rules for coding agents

- Read this file first. Respect the layer boundaries in section 6; if a change needs to cross them, stop and propose an ADR.
- Keep changes small and focused; one concern per commit, Conventional Commit messages.
- Write or update tests with every behaviour change; run lint, type-check and tests before declaring done.
- Never add secrets, real API keys or personal data to code, tests, fixtures or logs.
- Never call Meta APIs from the frontend.
- Ask before adding a new dependency or a new Azure resource.
- Use the contributor model only with synthetic data.
- When P0 is at risk, cut scope (move to P1/P2) rather than cut quality.
- After any user-visible milestone, add a build-log entry to `marketing/updates.json`.

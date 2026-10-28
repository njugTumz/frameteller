# Frameteller

**Frameteller turns spoken stories into editable storyboards and timed animatics.**

Talk through a scene. Frameteller listens live, works out the shots, draws consistent storyboard panels, lets you fix any panel by voice or by clicking an object in it, and exports an animatic timed to your own narration.

Built for indie filmmakers, YouTubers, animators, comic and game writers, and ad and pitch teams: anyone who can describe a scene faster than they can draw it.

> Built for the Meta Global AI Developer Hackathon (Indie Developer track, "Build for Your World").

- **Live demo:** TODO (production URL)
- **Studio on staging:** https://wonderful-field-0efc7e10f.3.azurestaticapps.net
- **Marketing page and build log:** https://gentle-stone-032869c0f.3.azurestaticapps.net
- **Demo video:** TODO
- **Source:** https://github.com/njugTumz/frameteller

## How it works

| Step | Meta model | What it does |
|---|---|---|
| Hear | `muse-voice-transcribe-1.0` | Streams a live transcript with turn detection and speaker labels. |
| Direct | `muse-spark-1.3` | Turns transcript turns into a validated shot list and keeps a character bible. Routes voice edit commands. |
| Draw | `muse-image-1.0` | Generates a reference sheet per character, then every panel from those references so characters stay consistent. |
| Select | `sam-3.1` | Segments a clicked object so it can be moved, swapped or edited in isolation. |

The animatic is rendered with ffmpeg: each panel's duration comes from the transcript turn timestamps, and your recording is the narration track.

## Architecture

The backend follows Clean Architecture: `domain` ← `application` ← `infrastructure` / `interface`, with dependencies pointing inward only. The browser never calls Meta APIs directly; all model calls go through the backend.

- Backend: Python, FastAPI, async jobs, Azure Container Apps
- Frontend: React, Vite, TypeScript, Tailwind, Azure Static Web Apps
- Storage: Azure Blob Storage
- CI/CD: GitHub Actions with staging and production environments

See [docs/architecture.md](docs/architecture.md) and the decision records in [docs/adr/](docs/adr/).

| Studio, light | Studio, dark |
|---|---|
| ![The studio in the light theme: transcript beats on the left, the approved cast and the storyboard on the right](docs/img/studio-light.png) | ![The same studio in the dark theme](docs/img/studio-dark.png) |

### Frontend

`frontend/` is React 19, Vite, TypeScript (strict) and Tailwind, laid out as CLAUDE.md section 6 describes:

- `app/` composes: the router, theme, top bar, the Start and Studio pages, and `app/studio/`, which fans session events out to the feature stores.
- `features/` holds one folder per feature: `start`, `recording`, `storyboard`, `cast` and `panel-editor`. Each has `store.ts` (a pure reducer in a Zustand store), `api.ts` (backend calls), `hooks/` (orchestration) and `components/` (rendering only). An ESLint rule stops components importing `api.ts`, the client, the session or the audio code.
- `shared/` holds the typed REST client generated from `backend/openapi.json` (`openapi-typescript` and `openapi-fetch`), the WebSocket event types from [docs/api-events.md](docs/api-events.md) with a runtime guard, the audio pipeline and UI primitives.
- **Audio:** `getUserMedia` feeds an AudioWorklet that mixes to mono, downsamples to 24 kHz and sends 80 ms frames of 16-bit PCM (3,840 bytes) over the session WebSocket as they are captured, which is real-time pace. Up to 2 s is held while the session connects. A dropped socket reconnects into a new session and says so.
- **Panel editor:** a react-konva canvas. A click calls `.../panel/select` with preview coordinates and outlines the returned mask. Masks cached on the panel answer instantly. The selected cut-out can be dragged and resized on the canvas, or changed by a typed or spoken instruction, which is transcribed by `POST /projects/{id}/dictation`. Moves are kept in the browser for now.
- The only build-time setting is `VITE_API_BASE_URL`, which is public, not a secret. The browser talks only to our backend, never to Meta.

## Deployment

**Staging:**
- Studio: https://wonderful-field-0efc7e10f.3.azurestaticapps.net
- API: https://ca-frameteller-staging.orangeplant-e171b35e.eastus2.azurecontainerapps.io (`/healthz`, `/readyz`, `/docs`, live session at `wss://…/ws/projects/{id}/session`)

```
GitHub push to main ──► deploy-staging.yml
                         ├─ build backend image ──► ghcr.io/njugtumz/frameteller-backend:<sha> (public)
                         └─ OIDC login ──► Bicep what-if ──► deploy infra/main.bicep (image + key) ──► check /healthz, /readyz
                       ──► deploy-frontend-staging.yml (frontend/** changed)
                         └─ build with VITE_API_BASE_URL ──► write staticwebapp.config.json (CSP) ──► OIDC login
                            ──► read the SWA deployment token (masked, never stored) ──► upload ──► check headers

rg-frameteller-staging (eastus2, tags project=frameteller env=staging)
  ca-frameteller-staging         Container App: HTTPS + WebSocket ingress, 0–1 replicas (ADR 0009),
   │  system-assigned identity    probes on /healthz and /readyz, MODEL_API_KEY as a Container App secret
   │  ──Storage Blob Data Contributor──►
  stftstag…                      Storage account, identity-only access: media/ (30-day lifecycle in staging), projects/
  cae-frameteller-staging        Container Apps environment (consumption) ──► log-frameteller-staging (Log Analytics)
  appi-frameteller-staging       Application Insights (workspace-based)
  swa-frameteller-app-staging    Static Web App (Free): the studio, SPA fallback, CSP allowing only the API origin
  budget-frameteller-staging     USD 20/month, alerts at 80% actual and 100% forecast
```

- **Infrastructure as code:** everything except the resource group and the budget is in [`infra/`](infra/): `main.bicep`, `modules/`, and `parameters/{staging,production}.bicepparam`. Production stays unused until staging is proven.
- **Auth:** GitHub Actions signs in to Azure with an Entra app that has a federated credential for this repo's `staging` environment. There is no client secret. Its roles are Contributor on the resource group only, and the right to assign only Storage Blob Data Contributor there.
- **Configuration:** `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` and `VITE_API_BASE_URL` are environment variables. `MODEL_API_KEY` is an environment secret, passed to Bicep from the job's environment and never written in a file.
- **Storage:** the backend uses `STORAGE_BACKEND=blob` in Azure. Projects are one JSON blob each, with ETag concurrency; spend is kept in append blobs. Locally the default is files under `backend/.data/`.
- **Smoke test against staging:** `python scripts/smoke_local.py --base <staging URL> --beats --ledger none`. Spend is in the `model call` log lines in Log Analytics.

## Local setup

Backend (Python 3.12, pip 25.1 or newer):

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install --upgrade "pip>=25.1" && pip install -e . --group dev

ruff check src tests scripts && ruff format --check src tests scripts
mypy
PYTHONPATH=src lint-imports
pytest --cov                              # no network; RUN_LIVE=1 pytest -m live spends real credits
python scripts/export_openapi.py          # after changing a route or DTO; CI fails if openapi.json is stale
```

### Configuration

Settings come from environment variables, or a `.env` file in the repo root or `backend/`. Copy `.env.example`, fill in `MODEL_API_KEY`, and never commit the result.

- With `APP_ENV=local` (the default), the director uses the cheap contributor model. Use it with synthetic stories only.
- Media and project documents go to `backend/.data/`. This directory is gitignored.
- Optional settings:
  - `ALLOWED_ORIGINS`: comma-separated frontend origins for CORS and the WebSocket.
  - `SAM_MAX_SIDE`: default 768 ([ADR 0007](docs/adr/0007-sam-on-downscaled-copy.md)); empty means full size.
  - `RATE_LIMIT_PER_MINUTE` and `RATE_LIMIT_COSTLY_PER_MINUTE`.
  - The per-project and per-day budget limits; see `backend/src/frameteller/infrastructure/config.py`.

### Run the API

```bash
cd backend
uvicorn frameteller.interface.main:app --port 8000 --reload
```

- `GET /healthz` reports that the process is up.
- `GET /readyz` checks settings and storage, without calling Meta.
- Interactive REST docs are at http://127.0.0.1:8000/docs.
- The live voice WebSocket is documented in [docs/api-events.md](docs/api-events.md).

Or in Docker (the same image CI builds):

```bash
docker build -t frameteller-backend backend
docker run --rm -p 8000:8000 --env-file .env frameteller-backend
```

### End-to-end smoke test

With the API running, the smoke test drives the whole flow and spends about $0.05 in real credits. It:
1. creates a project
2. streams `spikes/fixtures/narration.wav` over the session WebSocket at real-time pace
3. approves the proposed cast
4. draws draft panels for shots 1–2
5. clicks once on panel 1
6. prints events, latency per step and spend

The WAV must be mono, 16-bit, 24 kHz. It is your own recording and is gitignored.

```bash
cd backend
python scripts/smoke_local.py --base http://127.0.0.1:8000
```

### Run the studio (frontend)

You need Node 20.19 or later. With the API running on port 8000:

```bash
cd frontend
npm ci
npm run dev        # http://localhost:5173, which the API allows by default
```

The app calls `http://localhost:8000` unless `VITE_API_BASE_URL` is set (`VITE_API_BASE_URL=https://… npm run dev`). Never put a secret in a `VITE_*` variable: Vite bakes them into the public bundle.

| Command | What it does |
|---|---|
| `npm run lint` / `npm run typecheck` | ESLint, including the layer rule, and `tsc` |
| `npm test` | Vitest and Testing Library: store reducers for every event, the beat button and Space, corrections, cast gating, select-to-mask |
| `npm run api:types` / `npm run api:check` | Regenerate `src/shared/api/schema.d.ts` from `backend/openapi.json`, or check that it is current (CI does) |
| `npx playwright install chromium` then `npx playwright test` | End-to-end in headless Chromium against a backend faked in the browser: no network, no credits (CI does) |

**Live end-to-end (opt-in, spends about USD 0.10 locally and 0.11 on staging).** This uses the real backend and models. Chromium's fake microphone plays `spikes/fixtures/narration.wav`. The test clicks "Next shot" at each paragraph, then checks for 6 shot cards, the proposed cast, drafts after approval, and a mask selection on panel 1. It saves a video, a timeline and the spend to `spikes/out/`.

```bash
# against a local API started with ALLOWED_ORIGINS=http://localhost:4173,http://localhost:5173
E2E_LIVE=1 E2E_SPEND_LOG=$PWD/../backend/.data/spend.jsonl npx playwright test
# against staging
E2E_LIVE=1 E2E_TARGET=staging E2E_APP_URL=https://wonderful-field-0efc7e10f.3.azurestaticapps.net \
  E2E_API_URL=https://ca-frameteller-staging.orangeplant-e171b35e.eastus2.azurecontainerapps.io npx playwright test
```

## Built during the hackathon (Oct 26 – Nov 4, 2026)

Everything in this repository was built during the event. The commit history is the record.

- [x] Project brief, marketing page with countdown and live build log
- [x] Repository foundation: licence, config template, ADR 0001, marketing deploy workflow
- [x] Day 2 spikes proving voice → shots, character consistency and click-to-select ([findings](docs/spikes/2026-10-28-findings.md))
- [x] Backend domain and application layers with tests, import contracts and CI
- [x] Meta model adapters (realtime voice, Spark director, Muse Image, SAM 3.1) with contract fixtures recorded from real calls
- [x] FastAPI interface: REST, live voice session WebSocket, health probes, rate limiting, OpenAPI export, Docker image
- [x] Narrator beats and transcript corrections on the live session ([ADR 0008](docs/adr/0008-reliable-beats.md))
- [x] Azure staging: Blob Storage adapters, Bicep, OIDC deploy pipeline, live at the staging URL above
- [x] The studio: speak a story, cut shots with "Next shot", approve the cast, watch drafts arrive, and click an object in a panel to select, move or change it, on staging with CI and Playwright tests
- [ ] TODO: list features as they ship

## License

[MIT](LICENSE)

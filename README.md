# Frameteller

**Frameteller turns spoken stories into editable storyboards and timed animatics.**

Talk through a scene. Frameteller listens live, works out the shots, draws consistent storyboard panels, lets you fix any panel by voice or by clicking an object in it, and exports an animatic timed to your own narration.

Built for indie filmmakers, YouTubers, animators, comic and game writers, and ad and pitch teams: anyone who can describe a scene faster than they can draw it.

> Built for the Meta Global AI Developer Hackathon (Indie Developer track, "Build for Your World").

- **Live demo:** TODO (production URL)
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

## Deployment

**Staging:** https://ca-frameteller-staging.orangeplant-e171b35e.eastus2.azurecontainerapps.io (`/healthz`, `/readyz`, `/docs`, live session at `wss://…/ws/projects/{id}/session`)

```
GitHub push to main ──► deploy-staging.yml
                         ├─ build backend image ──► ghcr.io/njugtumz/frameteller-backend:<sha> (public)
                         └─ OIDC login ──► Bicep what-if ──► deploy infra/main.bicep (image + key) ──► check /healthz, /readyz

rg-frameteller-staging (eastus2, tags project=frameteller env=staging)
  ca-frameteller-staging         Container App: HTTPS + WebSocket ingress, 0–1 replicas (ADR 0009),
   │  system-assigned identity    probes on /healthz and /readyz, MODEL_API_KEY as a Container App secret
   │  ──Storage Blob Data Contributor──►
  stftstag…                      Storage account, identity-only access: media/ (30-day lifecycle in staging), projects/
  cae-frameteller-staging        Container Apps environment (consumption) ──► log-frameteller-staging (Log Analytics)
  appi-frameteller-staging       Application Insights (workspace-based)
  budget-frameteller-staging     USD 20/month, alerts at 80% actual and 100% forecast
```

- **Infrastructure as code:** everything except the resource group and the budget is in [`infra/`](infra/): `main.bicep`, `modules/`, and `parameters/{staging,production}.bicepparam`. Production stays unused until staging is proven.
- **Auth:** GitHub Actions signs in to Azure with an Entra app that has a federated credential for this repo's `staging` environment. There is no client secret. Its roles are Contributor on the resource group only, and the right to assign only Storage Blob Data Contributor there.
- **Configuration:** `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` and `AZURE_SUBSCRIPTION_ID` are environment variables. `MODEL_API_KEY` is an environment secret, passed to Bicep from the job's environment and never written in a file.
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

The frontend is not scaffolded yet.

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
- [ ] TODO: list features as they ship

## License

[MIT](LICENSE)

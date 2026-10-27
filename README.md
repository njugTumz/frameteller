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

## Local setup

Backend (Python 3.12, pip 25.1 or newer):

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install --upgrade "pip>=25.1" && pip install --group dev

ruff check src tests && ruff format --check src tests
mypy
PYTHONPATH=src lint-imports
pytest --cov
```

Create `.env` from `.env.example` and fill in values locally; never commit it. The frontend is not scaffolded yet.

## Built during the hackathon (Oct 26 – Nov 4, 2026)

Everything in this repository was built during the event. The commit history is the record.

- [x] Project brief, marketing page with countdown and live build log
- [x] Repository foundation: licence, config template, ADR 0001, marketing deploy workflow
- [x] Day 2 spikes proving voice → shots, character consistency and click-to-select ([findings](docs/spikes/2026-10-28-findings.md))
- [x] Backend domain and application layers with tests, import contracts and CI
- [ ] TODO: list features as they ship

## License

[MIT](LICENSE)

# DynastyAI — AI Chinese Historical Drama Generator

An AI-powered pipeline for generating short Chinese historical dramas from a simple story idea.

**Phase 1:** turn a story brief into an editable, structured storyboard. The long-term goal is a short Chinese historical drama video for YouTube Shorts and Instagram Reels. This release generates storyboards only; image, voice, music, and video generation are future work.

## Features

- Enter a story idea, genre, target duration, and output language.
- Generate with a server-side, OpenAI-compatible Chat Completions LLM API.
- Each scene includes its number, duration in seconds, narration, structured dialogue, visual prompt, characters, and camera description.
- Edit the title and all scene content; add or remove dialogue lines.
- Download validated UTF-8 JSON and reopen it later using **Open JSON**.
- Exact total-duration validation, consecutive scene numbers, and dialogue-speaker checks.
- Explicit demo mode to explore the UI without an API key. Demo mode uses a fixed sample and does not adapt its story to the brief.
- English, Simplified Chinese, and Traditional Chinese output.

## Quick start

Requirements: Python 3.11+ and [uv](https://docs.astral.sh/uv/getting-started/installation/).

```sh
git clone https://github.com/wjy-Jerry/DynastyAI.git
cd DynastyAI
uv sync --locked
```

Copy `.env.example` to `.env` (`Copy-Item .env.example .env` in PowerShell, or `cp .env.example .env` on macOS/Linux), then configure:

```dotenv
LLM_API_KEY=your-provider-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
DEMO_MODE=false
```

The base URL must be the API root ending in `/v1`, not the `/chat/completions` endpoint. Choose a model your provider supports. It must support `response_format: {"type": "json_object"}` and the Chat Completions request/response format. Keys stay on the backend. No key is needed for the explicit sample mode: set `DEMO_MODE=true` instead.

```sh
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open [localhost:8000](http://localhost:8000). API documentation is at [localhost:8000/docs](http://localhost:8000/docs).

On Windows, `./start-demo.ps1` starts the fixed-template demo directly after `uv sync --locked`.

Without uv, create and activate a Python virtual environment and install with `python -m pip install .`, then run `python -m uvicorn app.main:app`. uv is recommended for reproducible dependency versions.

## Editing and saving

Generate a storyboard, edit its fields, then click **Save JSON**. A project downloads to your browser's download folder. **Open JSON** loads a previously saved project. Edits live in the page until downloaded; there is no server-side project database. Replacing a project prompts you to save first, and leaving the page triggers the browser's unsaved-work warning.

Scene durations must remain positive integers summing to the original target. If you change one duration, balance another scene before saving. Character names are entered one per line, and every dialogue speaker must appear in the scene's character list. Invalid edits remain available to correct when export validation fails.

Exports have `schema_version: "1.0"`, a `title`, the original `request`, `generation_mode`, and a `scenes` array. See [examples/demo-project.json](examples/demo-project.json). The API model definitions in [app/models.py](app/models.py) are the canonical schema.

## Development and testing

```sh
uv sync --locked
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```

Backend tests cover input validation, demo languages and durations, edited JSON round trips, real HTTP payload construction with a mocked provider, invalid LLM output, network failures, and sanitized provider errors. Browser tests exercise generation, scene editing, JSON download and reopening, invalid import/export, and narrow-screen layout:

```sh
npm ci
npm run format:check
npx playwright install chromium
npm test
```

Playwright starts a local demo server automatically. Tests do not require an API key and do not make billable LLM calls. To verify a real provider, configure `.env` with `DEMO_MODE=false` and generate a storyboard in the UI.

## Structure

```text
app/
  main.py          # FastAPI routes and static frontend
  config.py        # environment configuration
  models.py        # request, scene, and project validation
  storyboard.py    # LLM adapter and explicit demo template
  static/          # HTML, CSS, and JavaScript editor
tests/             # backend tests
e2e/               # Playwright browser tests
examples/          # sample exported project
.github/workflows/ # automated checks
```

## Scope and limitations

This is a local development application. Run on the loopback interface. Before making it internet-accessible, add authentication, request limits, abuse protection, and deployment-specific controls. Story briefs are sent to the configured provider; project JSON and API keys are never deliberately logged. The LLM may invent historical details, and language quality and spoken timing need human review. Malformed or incorrectly timed outputs fail visibly rather than being silently accepted. There are no automatic retries or background jobs in Phase 1.

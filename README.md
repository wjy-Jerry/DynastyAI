# DynastyAI — Chinese Historical Drama Story Studio

DynastyAI turns a story idea into an editable storyboard, a Character Bible, a Visual Style Bible, and vertical scene keyframes. It is a polished local MVP for the first two phases of a larger short-drama pipeline. It does not create video, audio, music, or social-media posts.

## What Phase 2 adds

The story brief still captures idea, genre, target duration, and output language. The backend now generates structured recurring-character descriptions and project-level visual settings together with the storyboard. Each scene has a composed final image prompt that includes its visual action and camera direction, the full Visual Style Bible, and the **same complete Character Bible entry** for each recurring character ID. The final prompt is visible and editable before image generation.

The editor can create a mock image for one scene, regenerate it, or generate all scenes sequentially. The mock provider writes a clearly labeled 9:16 SVG placeholder and never pretends to use AI. The OpenAI provider requests a 1152×2048 PNG through the Images API. Provider selection and keys are server-side environment settings. Generated files live in `data/assets/<project-id>/` and are ignored by Git; project JSON stores only asset metadata and local URLs.

Character consistency is **prompt-level only**. Independent image generations may still change a face, costume detail, or prop. There is no reference-image conditioning, identity embedding, cross-scene image editing, or visual matching in this phase. Character and era descriptions are fictional creative guidance, not a claim of historical accuracy.

## Quick start

Requirements: Python 3.11+ and [uv](https://docs.astral.sh/uv/getting-started/installation/). Browser test development also needs Node.js 20+.

```sh
git clone https://github.com/wjy-Jerry/DynastyAI.git
cd DynastyAI
uv sync --locked
```

Copy `.env.example` to `.env` (`Copy-Item .env.example .env` in PowerShell, or `cp .env.example .env` on macOS/Linux). To explore the complete workflow without any API key, set:

```dotenv
DEMO_MODE=true
IMAGE_PROVIDER=mock
```

The demo storyboard is a fixed template and does not adapt its story to your idea. Mock images are labeled placeholders. Start the app:

```sh
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open [localhost:8000](http://localhost:8000). On Windows, `./start-demo.ps1` starts the same demo after `uv sync --locked`. API documentation is at [localhost:8000/docs](http://localhost:8000/docs).

## Configure real providers

Storyboards and Character Bibles use an OpenAI-compatible Chat Completions endpoint. The model must support JSON-object responses. Set the API root ending in `/v1`, not the `/chat/completions` endpoint:

```dotenv
DEMO_MODE=false
LLM_API_KEY=your-story-llm-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

Image generation is an independent provider. `IMAGE_PROVIDER=mock` remains available even when the storyboard uses a real LLM. For OpenAI Images, set:

```dotenv
IMAGE_PROVIDER=openai
IMAGE_API_KEY=your-image-api-key
IMAGE_API_BASE_URL=https://api.openai.com/v1
IMAGE_MODEL=gpt-image-2.5-flare
```

The configured image model must support the Images API and the requested 1152×2048 PNG dimensions. The [official image generation guide](https://developers.openai.com/api/docs/guides/image-generation) describes supported models and dimensions. A real image call may incur provider charges. Automated tests never make billable calls. No real provider call is attempted merely by starting the app or opening a project.

Keys stay on the backend and `.env` is ignored by Git. `ASSET_DIR` defaults to `data/assets`; keep it on local disk. Existing generated files are not embedded in JSON or uploaded to GitHub.

## Workflow

1. Enter a story brief and click **Generate storyboard**. In demo mode, the response is a fixed example with a Character Bible and Visual Style Bible. With an LLM key, one request asks the LLM for all three together.
2. Edit scene narration, dialogue, characters, visual prompts, and camera direction. Review and edit every recurring character's appearance, face, hairstyle, costume, and accessories. Edit the fictional era, style, lighting, cinematography, and color mood. The aspect ratio is fixed at 9:16 in this version.
3. Click **Refresh prompts** after changing scene direction, Character Bible entries, or visual style. This replaces manual edits to final prompts, so the editor asks before doing it. Inspect the resulting final prompt for each scene; edit it if needed. The full character and style blocks, visual action, and camera direction must remain present. The backend rejects stale prompts before image generation.
4. Click **Generate Image** for one scene or **Generate All Scene Images** for every scene. The all-scenes action runs sequentially and reports failures per scene; **Regenerate Image** affects only that scene. Mock images explicitly say they are placeholders. The final prompt shown in the editor is sent verbatim to the provider.
5. Click **Save JSON** to download the version 2 project with character descriptions, style, final prompts, and image metadata. **Open JSON** restores it. Image files remain on the machine where they were generated. If they are missing, the UI says so and you can regenerate them.

Scene durations must sum to the target duration, and every dialogue speaker must be listed in its scene. Character IDs are stable references; scene character names must match those IDs. Adding a new name in a scene creates a Character Bible entry marked for review. Edits live in the browser until you save JSON; there is no server-side project database.

### Opening Phase 1 projects

Existing `schema_version: "1.0"` JSON remains loadable. The app validates it, then explicitly migrates it to version 2. Storyboard content is preserved. New Character Bible entries say that their visual details are unspecified and require review. The UI shows a migration message. Unsupported versions fail with a helpful version error; they are never silently rewritten. [The Phase 1 example](examples/demo-project.json) can be used to test migration.

## Development and testing

```sh
uv sync --locked
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
npm ci
npm run format:check
npx playwright install chromium
npm test
```

Backend tests cover both phases: schema and migration, prompt reuse, mock and real-provider adapters, per-scene regeneration, asset persistence, invalid provider responses, and HTTP errors. Browser tests cover the Character Bible editor, prompt refresh, generation, JSON save/open, migration, failure retry, and mobile layout. Real provider requests use `httpx.MockTransport` in tests; browser tests run with the local mock provider.

## Project layout

```text
app/models.py           Phase 1 schema, retained for compatibility
app/phase2_models.py    Character, style, asset, and v2 project schema
app/storyboard.py       Phase 1 LLM flow and demo template
app/phase2.py           v2 generation and v1 migration
app/prompts.py          deterministic final image prompt composition
app/images.py           mock and OpenAI image providers; local asset writes
app/main.py             FastAPI routes and asset serving
app/static/             browser editor
tests/                  backend tests
e2e/                    Playwright browser tests
data/assets/            generated local images, ignored by Git
```

The app binds to `127.0.0.1` in these examples. It has no user accounts or request limits and should remain local. LLMs can invent historical details, and generated images may contain visual errors. Review prompts, cultural details, output language, and character identity before using any image in production.

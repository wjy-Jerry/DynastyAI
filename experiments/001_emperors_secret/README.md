# Experiment 001 — The Emperor's Secret

This is an **offline experiment design**, not a video-generation feature. It prepares a 15-second, three-scene fictional Chinese historical suspense drama for a later visual comparison of Vidu Q3 Turbo I2V and Wan 2.7 I2V. No API key, network request, task submission, or generated video is needed for any command here.

## Controlled design

The machine-readable source is [`experiment.json`](experiment.json); [`experiment.schema.json`](experiment.schema.json) records its validation schema. The unchanged Chinese script and three English narration adaptations for a later international release are laid out in [`script.md`](script.md). The Lin Yue Character Bible, Visual Style Bible, three complete English motion prompts, frame specifications, filenames, and comparison controls are fixed in the JSON. Four production-ready still-image prompts and their schema are in [`still_prompts.json`](still_prompts.json) and [`still_prompts.schema.json`](still_prompts.schema.json); [still_images.md](still_images.md) gives the reference-conditioning workflow. This is a fictional imperial court, not a claim of historical accuracy. Narration and dialogue are script only; neither provider is asked to synthesize or score speech in this comparison.

| Scene | Time | Chinese dramatic beat | Shared first-frame target |
| --- | --- | --- | --- |
| 01 | 0–5 s | Lin Yue finds a fresh seal on the late emperor's decree. | Lin Yue alone at the candlelit archive desk, decree and seal visible. |
| 02 | 5–10 s | Guards approach; a hidden dragon pattern appears in the decree. | Lin Yue holds the decree near a candle and watches the closed door. |
| 03 | 10–15 s | A secret door opens; the emperor's silhouette appears. | Lin Yue in the foreground, hidden doorway behind her, second figure only a silhouette. |

The exact same `motion_prompt_en` string and the exact same scene PNG bytes are bound to both model previews for each scene. Both are set to five seconds and 720p, with no prompt rewriting where a switch exists. Vidu is configured with `audio=false`; Wan 2.7's documented I2V request does **not** expose an equivalent silence switch and may add audio even when the prompt requests none. Score visual output only and mute playback. A fixed seed is included where supported, but it does not guarantee reproducible pixels.

The committed `fixtures/scene_0N_start.mock.png` files are visible, synthetic **MOCK FIXTURE** cards. They allow dimension, hash, and request-shape checks but cannot measure video or character quality. Before any future real comparison, generate and approve one Lin Yue portrait at `assets/lin_yue_reference.png`, then create three scene starts at `assets/scene_0N_start.png`, each conditioned on **that exact same portrait**. All four must be 8-bit RGB PNGs at exactly 720×1280 with no alpha. The portrait must be at most 9 MiB and each scene frame at most 14 MiB. This leaves room for base64 expansion and JSON under Vidu's 20 MB POST-body limit. Use **the same production scene PNG file and SHA-256 digest for both video providers**, and record all four digests in local `assets/manifest.json`. The portrait is an identity source for making the scene frames; it is not itself an I2V input. `assets/` and `outputs/` are ignored by Git. Do not use the mock cards or unrelated generated portraits for live model evaluation.

The 9:16 target is enforced for input frames. Wan documents that encoded output can drift slightly from the input ratio because its dimensions are rounded for video encoding; measure actual output dimensions before claiming a 9:16 result. [Wan I2V aspect-ratio note](https://help.aliyun.com/en/model-studio/image-to-video-general-api-reference)

## Offline checks and previews

From the repository root after `uv sync --locked`:

```sh
uv run python experiments/001_emperors_secret/make_fixtures.py
uv run python experiments/001_emperors_secret/validate.py schema
uv run python experiments/001_emperors_secret/validate.py validate
uv run python experiments/001_emperors_secret/validate.py preview
uv run pytest -q experiments/001_emperors_secret/tests
```

`preview` prints six JSON request **previews**. Authorization is omitted, image base64 is replaced by a non-submittable SHA-256 marker, and each request says `submittable: false`. The code imports no HTTP client. The `--frames production` option validates the four local production images and manifest, then prints similarly redacted previews; it fails while those files are absent. It must not be represented as passed until all four reviewed real images exist. `make_fixtures.py --write` and `validate.py schema --write` are only for deliberately regenerating their committed offline artifacts.

Provider-specific, non-secret templates are [`providers/vidu_q3_turbo.json`](providers/vidu_q3_turbo.json) and [`providers/wan_2_7_i2v.json`](providers/wan_2_7_i2v.json). They describe future request contracts, not runnable clients. Vidu's documented endpoint is `POST /ent/v2/img2video` with one image, `viduq3-turbo`, five seconds, and 720p. Wan's documented asynchronous endpoint uses `input.media` with one `first_frame`, plus `X-DashScope-Async: enable`. Its model, regional endpoint, and API key must be from the same region. The Wan template uses a Singapore workspace URL placeholder; substitute your own workspace ID later, or choose the matching Beijing endpoint when conducting a separately approved live run. [Vidu I2V API](https://platform.vidu.com/docs/image-to-video) · [Wan 2.7 I2V API](https://help.aliyun.com/en/model-studio/image-to-video-general-api-reference)

## Expected local assets

| Role | Files |
| --- | --- |
| Mock offline inputs | `fixtures/scene_01_start.mock.png` through `scene_03_start.mock.png` and `fixtures/manifest.json` |
| Future reviewed inputs | `assets/lin_yue_reference.png`, `assets/scene_01_start.png` through `scene_03_start.png`, and a four-entry `assets/manifest.json` |
| Future Vidu outputs | `outputs/vidu_q3_turbo/scene_01.mp4` through `scene_03.mp4` |
| Future Wan outputs | `outputs/wan_2_7_i2v/scene_01.mp4` through `scene_03.mp4` |

No expected output video exists yet. Keep the full original API response and task ID in private experiment notes if a later approved run occurs; do not commit credentials or expiring asset URLs.

## Evaluation and spend

[`blind_scorecard.csv`](blind_scorecard.csv) has six anonymous clip rows and two set-level rows. A coordinator should assign whole model sets randomly to A and B, then give only copied, muted `A-01.mp4` … `B-03.mp4` clips and the scorecard to reviewers. The mapping stays local under ignored `outputs/` until scoring closes. Use 1–5 scores for first-frame fidelity, Lin Yue face/hair/costume, action and camera adherence, composition, and artifact severity; score cross-scene identity at set level. The rubric and tie-break rules are in [`evaluation.md`](evaluation.md). Do not compare provider names during blind scoring.

[`cost_estimates.md`](cost_estimates.md) gives dated, non-binding Vidu-credit and Wan CNY estimates for a later **one take per scene** run. No cost was incurred by preparing this package. Rates, promotions, model availability, and regional billing must be rechecked in each provider console before any later live experiment.

[`r2v_plan.md`](r2v_plan.md) describes a separate, later reference-to-video consistency test. It is a plan only; no R2V request template or execution path is implemented here.

## What remains untested

Actual still-image creation, reference-conditioned identity fidelity, production-frame validation, provider acceptance, generation latency, final video dimensions, soundtrack behavior, output quality, Lin Yue's real facial continuity, and live charges have not been tested. The committed fixtures are schematic placeholders. A later live comparison needs the four reviewed production images and manifest, a successful offline production-frame preview, region-specific account configuration, a spending cap, and separate explicit authorization.

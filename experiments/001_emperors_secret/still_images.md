# Still-image preparation for Experiment 001

The four complete English prompts and negative prompts are in [`still_prompts.json`](still_prompts.json), with a committed [JSON Schema](still_prompts.schema.json). They are fixed against the Character Bible and Visual Style Bible in [`experiment.json`](experiment.json) by canonical SHA-256 digests. The exact Lin Yue identity anchor appears once in every prompt. The setting is a **fictional** Chinese imperial court with no claimed dynasty or historical accuracy.

| Order | Image | Method | Purpose |
| --- | --- | --- | --- |
| 1 | `assets/lin_yue_reference.png` | Text-to-image; review and lock one master | The sole approved identity reference: Lin Yue's face, beauty mark, bun, jade hairpin, teal robe, and pouch must all be visible. |
| 2 | `assets/scene_01_start.png` | Image-to-image using the **same locked portrait** | Archive desk and freshly sealed decree. |
| 3 | `assets/scene_02_start.png` | Image-to-image using the **same locked portrait** | Candle, decree, barely emerging dragon mark, approaching-guard shadow. |
| 4 | `assets/scene_03_start.png` | Image-to-image using the **same locked portrait** | Lin Yue foreground; emperor is only an unidentifiable silhouette. |

Generate the portrait first and choose **one** visually sound result. If it fails the Character Bible, review and decide whether to make another separately approved request *before* any scene frame. Once approved, freeze its bytes and SHA-256. Submit that exact portrait as the image input for **each** scene still, along with that scene's `prompt_en` and `negative_prompt_en`; never use a scene frame or another independent portrait as a substitute reference. The experiment-local [`qwen_stills.py`](qwen_stills.py) now implements this using Alibaba's [Qwen image generation and editing API](https://help.aliyun.com/en/model-studio/qwen-image-generation-and-editing-api-reference): it sends the actual portrait bytes as a Base64 PNG `image` field. The general DynastyAI Phase 2 provider remains unchanged and does not gain reference conditioning through this experiment adapter.

## Qwen still generation, dry-run first

Copy the non-secret names in [`providers/qwen_image.env.example`](providers/qwen_image.env.example) into your **local** environment. Set `QWEN_IMAGE_REGION` to `beijing`, `singapore`, `virginia`, `frankfurt`, or `tokyo`; set `QWEN_IMAGE_WORKSPACE_ID` and `DASHSCOPE_API_KEY` from that **same** Model Studio region. The adapter constructs the official workspace-specific HTTPS endpoint itself. It never prints or saves the key, and never sends it when fetching the signed output image URL. Do not commit local `.env` files or generated assets.

From the repository root, preview the one-portrait request without an API key or network access:

```sh
uv run python experiments/001_emperors_secret/qwen_stills.py portrait
```

The preview prints the model, region, endpoint, estimated list cost, exact positive and negative prompts, size, and parameters. It is a dry run by default. `scene --number 1` (and 2/3) previews a request only after the portrait is generated and explicitly approved; the Base64 image field is **redacted** in the preview, but the actual paid request uses the approved portrait bytes. Each invocation submits at most **one** image generation request; `n=1`, no automatic retry, no batch command, and existing candidate files are never overwritten.

**No paid run is authorized by this document or the present preparation task.** For a future separately approved run, the operator must set `EXPERIMENT_001_ENABLE_PAID_CALLS=true` and deliberately use both `--execute` and `--confirm-cost` on `portrait`. Start with that **one portrait request only**, then stop for visual review. The adapter validates the returned file as 8-bit RGB PNG at exactly 720×1280 and saves it to ignored `assets/lin_yue_reference.png` with a local generation record. If Qwen returns a different mode or size, the candidate is rejected rather than silently resized or recolored; such edits would need separate visual review.

After visually reviewing the master portrait, calculate its SHA-256 (PowerShell: `Get-FileHash experiments/001_emperors_secret/assets/lin_yue_reference.png -Algorithm SHA256`; Unix: `sha256sum experiments/001_emperors_secret/assets/lin_yue_reference.png`) and record explicit approval:

```sh
uv run python experiments/001_emperors_secret/qwen_stills.py approve-portrait --sha256 <full-lowercase-sha256>
```

This command checks the candidate's bytes, dimensions, RGB format, generation record, model, and unchanged prompt. A scene request is blocked unless that exact approved portrait still matches its SHA-256 and prompt. A changed or unrelated portrait cannot silently stand in for the master. Each future scene candidate can be reviewed and locked with `approve-scene --number N --sha256 <full-lowercase-sha256>`; `manifest` requires approval records for all four assets before it writes `assets/manifest.json` and runs production-frame validation. The explicit scene approvals are an additional review gate, not a claim of perfect identity consistency.

Only after portrait approval and separate authorization for scene-image costs, preview `scene --number 1` and then run **one** scene with `scene --number 1 --execute --confirm-cost`. Review and approve it before repeating for numbers 2 and 3. Finally run `uv run python experiments/001_emperors_secret/qwen_stills.py manifest`. This writes the four SHA-256 values and immediately invokes the existing production-frame validator. Do not use `manifest` as a substitute for visually checking the four images.

Alibaba's [published 1K image prices](https://help.aliyun.com/en/model-studio/model-pricing) as checked 2026-10-11 put standard `qwen-image-3.0` at **CNY 0.18** for one Beijing portrait and **CNY 0.20** for each Beijing scene (CNY 0.02 input + CNY 0.18 output). In Singapore, the comparable list estimates are **CNY 0.224826** and **CNY 0.247309**. One accepted portrait plus three accepted scenes would be approximately **CNY 0.78** in Beijing or **CNY 0.966753** in Singapore, before any free quota or promotion. The initial approved call would be the portrait only. Verify region, model availability, billing, and current console price immediately before execution; rejected candidates that successfully generate can still incur output charges. The current task stops before every paid request.

For each candidate, compare Lin Yue's face and left-eye beauty mark, center-parted low braided bun and jade hairpin, deep teal robe, and pouch against the locked master. Inspect anatomy, props, camera composition, and consistency of the archive setting. Reject candidates that drift. Reference conditioning is a control, not a guarantee of identical facial identity. Do not call unrelated generated portraits a consistent character set.

Export the approved images as **8-bit RGB PNG without alpha**, exactly **720×1280** (9:16), with no text overlay or watermark. The reference portrait must be at most **9 MiB** and each scene frame at most **14 MiB**. Keep all four in ignored `assets/`; do not commit them. Record lowercase SHA-256 for each basename in `assets/manifest.json`, for example:

```json
{
  "lin_yue_reference.png": "<64 lowercase hexadecimal characters>",
  "scene_01_start.png": "<64 lowercase hexadecimal characters>",
  "scene_02_start.png": "<64 lowercase hexadecimal characters>",
  "scene_03_start.png": "<64 lowercase hexadecimal characters>"
}
```

After all four **real, reviewed** images exist, run from the repository root:

```sh
uv run python experiments/001_emperors_secret/validate.py validate --frames production
uv run python experiments/001_emperors_secret/validate.py preview --frames production
```

The first command checks file presence, PNG format, dimensions, size ceilings, and SHA-256 matches. The second produces six redacted, non-submittable offline I2V request previews using the three scene frames; it never makes an external request. The portrait is validated as an identity source but is not itself an I2V first frame. Until these assets exist, do **not** report production-frame validation or preview as passed; the mock fixture mode checks only the offline request shape.

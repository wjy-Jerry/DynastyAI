# Still-image preparation for Experiment 001

The four complete English prompts and negative prompts are in [`still_prompts.json`](still_prompts.json), with a committed [JSON Schema](still_prompts.schema.json). They are fixed against the Character Bible and Visual Style Bible in [`experiment.json`](experiment.json) by canonical SHA-256 digests. The exact Lin Yue identity anchor appears once in every prompt. The setting is a **fictional** Chinese imperial court with no claimed dynasty or historical accuracy.

| Order | Image | Method | Purpose |
| --- | --- | --- | --- |
| 1 | `assets/lin_yue_reference.png` | Text-to-image; review and lock one master | The sole approved identity reference: Lin Yue's face, beauty mark, bun, jade hairpin, teal robe, and pouch must all be visible. |
| 2 | `assets/scene_01_start.png` | Image-to-image using the **same locked portrait** | Archive desk and freshly sealed decree. |
| 3 | `assets/scene_02_start.png` | Image-to-image using the **same locked portrait** | Candle, decree, barely emerging dragon mark, approaching-guard shadow. |
| 4 | `assets/scene_03_start.png` | Image-to-image using the **same locked portrait** | Lin Yue foreground; emperor is only an unidentifiable silhouette. |

Generate the portrait first and choose **one** visually sound result. If it fails the Character Bible, regenerate and review the portrait *before* any scene frame. Once approved, freeze its bytes and SHA-256. Submit that exact portrait as the image input for **each** scene still, along with that scene's `prompt_en` and `negative_prompt_en`; never use a scene frame or another independent portrait as a substitute reference. A separate image-to-image capable tool/provider must send the portrait as an actual image input, not merely mention its filename in text. For Qwen-Image 3.0, Alibaba's [image generation and editing API reference](https://help.aliyun.com/en/model-studio/qwen-image-generation-and-editing-api-reference) describes the `image` input for image-to-image requests; use the region and credentials matching your account. The existing DynastyAI still-image adapter currently sends text prompts only, so these instructions do **not** claim the app itself can perform reference conditioning. No generation code or request is included in this package.

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

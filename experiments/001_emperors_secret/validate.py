"""Offline schema validation and redacted I2V request previews. No HTTP client exists here."""

import argparse
import hashlib
import json
import struct
import zlib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ROOT = Path(__file__).resolve().parent
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
FRAME_SIZE = (720, 1280)
MAX_FRAME_BYTES = 14 * 1024 * 1024
MAX_REFERENCE_BYTES = 9 * 1024 * 1024


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Dialogue(Strict):
    speaker: Literal["林月"]
    line_zh: str = Field(min_length=1)


class Script(Strict):
    action_zh: str = Field(min_length=1)
    narration_zh: str = Field(min_length=1)
    narration_en: str = Field(min_length=10, max_length=160)
    dialogue: list[Dialogue] = Field(min_length=1, max_length=1)


class Character(Strict):
    id: Literal["lin-yue"]
    name: Literal["Lin Yue (林月)"]
    role: str = Field(min_length=1)
    approximate_age: str = Field(min_length=1)
    appearance: str = Field(min_length=1)
    facial_features: str = Field(min_length=1)
    hairstyle: str = Field(min_length=1)
    costume: str = Field(min_length=1)
    accessories: str = Field(min_length=1)
    personality_visual_impression: str = Field(min_length=1)


class VisualStyle(Strict):
    historical_era: str = Field(min_length=1)
    visual_style: str = Field(min_length=1)
    lighting: str = Field(min_length=1)
    cinematography: str = Field(min_length=1)
    color_mood: str = Field(min_length=1)
    aspect_ratio: Literal["9:16"]


class Comparison(Strict):
    duration_per_scene_seconds: Literal[5]
    resolution_tier: Literal["720p"]
    visual_scoring_only: Literal[True]
    seed: int = Field(ge=0, le=2147483647)
    prompt_rewriting: Literal[False]
    one_take_per_scene: Literal[True]


class ReferenceImageSpec(Strict):
    character_reference_expected_filename: Literal["assets/lin_yue_reference.png"]
    character_reference_description: str = Field(min_length=20)
    scene_frame_format: str = Field(min_length=20)
    fixture_status: str = Field(min_length=20)


class ExpectedOutputs(Strict):
    vidu: str
    wan: str


class Scene(Strict):
    scene_number: int = Field(ge=1, le=3)
    start_second: int = Field(ge=0, le=10)
    duration_seconds: Literal[5]
    script: Script
    start_frame_spec_en: str = Field(min_length=30)
    motion_prompt_en: str = Field(min_length=100, max_length=5000)
    fixture_frame: str
    production_frame: str
    expected_outputs: ExpectedOutputs


class Experiment(Strict):
    schema_version: Literal["1.0"]
    experiment_id: Literal["001_emperors_secret"]
    title: Literal["The Emperor's Secret"]
    story_idea: str = Field(min_length=20)
    genre: Literal["Chinese historical suspense drama"]
    target_duration_seconds: Literal[15]
    output_language: Literal["Simplified Chinese"]
    aspect_ratio: Literal["9:16"]
    comparison: Comparison
    character_bible: Character
    identity_anchor_en: str = Field(min_length=50)
    visual_style: VisualStyle
    reference_image_spec: ReferenceImageSpec
    scenes: list[Scene] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def check_comparison_controls(self):
        for number, scene in enumerate(self.scenes, 1):
            if scene.scene_number != number or scene.start_second != (number - 1) * 5:
                raise ValueError("Scenes must be numbered 1-3 and start at 0, 5, 10 seconds")
            if scene.motion_prompt_en.count(self.identity_anchor_en) != 1:
                raise ValueError(f"Scene {number} must reuse the exact Lin Yue identity anchor")
            if scene.fixture_frame != f"fixtures/scene_0{number}_start.mock.png":
                raise ValueError(f"Scene {number} has the wrong fixture frame")
            if scene.production_frame != f"assets/scene_0{number}_start.png":
                raise ValueError(f"Scene {number} has the wrong production frame")
            if scene.expected_outputs.vidu != f"outputs/vidu_q3_turbo/scene_0{number}.mp4":
                raise ValueError(f"Scene {number} has the wrong Vidu output filename")
            if scene.expected_outputs.wan != f"outputs/wan_2_7_i2v/scene_0{number}.mp4":
                raise ValueError(f"Scene {number} has the wrong Wan output filename")
        if sum(scene.duration_seconds for scene in self.scenes) != self.target_duration_seconds:
            raise ValueError("Scene durations must total 15 seconds")
        return self


class ViduConfig(Strict):
    provider: Literal["vidu"]
    label: str
    endpoint: Literal["https://api.vidu.com/ent/v2/img2video"]
    auth_scheme: Literal["Token"]
    key_environment_variable: Literal["VIDU_API_KEY"]
    model: Literal["viduq3-turbo"]
    duration_seconds: Literal[5]
    resolution: Literal["720p"]
    audio: Literal[False]
    off_peak: Literal[False]
    image_binding: str
    preview_only: Literal[True]


class WanConfig(Strict):
    provider: Literal["wan"]
    label: str
    endpoint: str = Field(
        pattern=r"^https://[^/]+/api/v1/services/aigc/video-generation/video-synthesis$"
    )
    region: str
    auth_scheme: Literal["Bearer"]
    key_environment_variable: Literal["DASHSCOPE_API_KEY"]
    model: Literal["wan2.7-i2v"]
    duration_seconds: Literal[5]
    resolution: Literal["720P"]
    prompt_extend: Literal[False]
    watermark: Literal[False]
    image_binding: str
    preview_only: Literal[True]


class PortraitPrompt(Strict):
    output_file: Literal["assets/lin_yue_reference.png"]
    generation_mode: Literal["text_to_image_master"]
    prompt_en: str = Field(min_length=300)
    negative_prompt_en: str = Field(min_length=30)


class SceneStillPrompt(Strict):
    scene_number: int = Field(ge=1, le=3)
    output_file: str
    generation_mode: Literal["image_to_image_reference"]
    conditioning_reference_file: Literal["assets/lin_yue_reference.png"]
    prompt_en: str = Field(min_length=300)
    negative_prompt_en: str = Field(min_length=30)


class StillPrompts(Strict):
    schema_version: Literal["1.0"]
    experiment_id: Literal["001_emperors_secret"]
    character_bible_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    visual_style_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference_portrait: PortraitPrompt
    scene_start_frames: list[SceneStillPrompt] = Field(min_length=3, max_length=3)


def canonical_digest(value: dict) -> str:
    canonical = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_still_prompts(experiment: Experiment) -> StillPrompts:
    prompts = StillPrompts.model_validate_json((ROOT / "still_prompts.json").read_text("utf-8"))
    if prompts.character_bible_sha256 != canonical_digest(experiment.character_bible.model_dump()):
        raise ValueError("Still prompts do not match the locked Character Bible")
    if prompts.visual_style_sha256 != canonical_digest(experiment.visual_style.model_dump()):
        raise ValueError("Still prompts do not match the locked Visual Style Bible")
    all_prompts = [prompts.reference_portrait.prompt_en] + [
        scene.prompt_en for scene in prompts.scene_start_frames
    ]
    for prompt in all_prompts:
        if prompt.count(experiment.identity_anchor_en) != 1:
            raise ValueError("Every still prompt must reuse the exact Lin Yue identity anchor")
        if any(value not in prompt for value in experiment.visual_style.model_dump().values()):
            raise ValueError("Every still prompt must include the complete Visual Style Bible")
    for number, scene in enumerate(prompts.scene_start_frames, 1):
        if scene.scene_number != number or scene.output_file != f"assets/scene_0{number}_start.png":
            raise ValueError("Still prompt output names must match the three production frames")
    return prompts


def load_package() -> tuple[Experiment, ViduConfig, WanConfig]:
    experiment = Experiment.model_validate_json((ROOT / "experiment.json").read_text("utf-8"))
    vidu = ViduConfig.model_validate_json(
        (ROOT / "providers/vidu_q3_turbo.json").read_text("utf-8")
    )
    wan = WanConfig.model_validate_json((ROOT / "providers/wan_2_7_i2v.json").read_text("utf-8"))
    return experiment, vidu, wan


def rgb_png_digest(data: bytes, name: str, max_bytes: int = MAX_FRAME_BYTES) -> str:
    if len(data) > max_bytes or data[:16] != PNG_SIGNATURE + b"\x00\x00\x00\rIHDR":
        raise ValueError(f"Invalid RGB PNG frame: {name}")
    width, height = struct.unpack(">II", data[16:24])
    if (width, height) != FRAME_SIZE or data[24:26] != b"\x08\x02":
        raise ValueError(f"Frame must be 720x1280, 8-bit RGB PNG without alpha: {name}")
    if data[26:29] != b"\x00\x00\x00":
        raise ValueError(f"Unsupported PNG compression, filter, or interlace: {name}")
    offset = 8
    compressed = bytearray()
    seen_iend = False
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        end = offset + 12 + length
        if end > len(data):
            raise ValueError(f"Truncated PNG chunk: {name}")
        kind = data[offset + 4 : offset + 8]
        content = data[offset + 8 : offset + 8 + length]
        checksum = struct.unpack(">I", data[offset + 8 + length : end])[0]
        if zlib.crc32(kind + content) & 0xFFFFFFFF != checksum:
            raise ValueError(f"Bad PNG checksum: {name}")
        if kind == b"IDAT":
            compressed.extend(content)
        if kind == b"IEND":
            seen_iend = True
            if end != len(data):
                raise ValueError(f"Trailing PNG data: {name}")
            break
        offset = end
    if not seen_iend or not compressed:
        raise ValueError(f"Missing PNG image data: {name}")
    expected_size = (width * 3 + 1) * height
    decoder = zlib.decompressobj()
    try:
        pixels = decoder.decompress(compressed, expected_size + 1)
        pixels += decoder.flush(expected_size + 1 - len(pixels))
    except zlib.error as exc:
        raise ValueError(f"Corrupt PNG pixels: {name}") from exc
    if len(pixels) != expected_size or not decoder.eof or decoder.unconsumed_tail:
        raise ValueError(f"Invalid PNG pixel length: {name}")
    if any(pixels[row * (width * 3 + 1)] > 4 for row in range(height)):
        raise ValueError(f"Invalid PNG row filter: {name}")
    return hashlib.sha256(data).hexdigest()


def frame_digest(path: Path, max_bytes: int = MAX_FRAME_BYTES) -> str:
    return rgb_png_digest(path.read_bytes(), path.name, max_bytes)


def check_frames(experiment: Experiment, source: Literal["fixture", "production"]) -> list[str]:
    manifest_path = ROOT / ("fixtures" if source == "fixture" else "assets") / "manifest.json"
    expected_names = [
        Path(scene.fixture_frame if source == "fixture" else scene.production_frame).name
        for scene in experiment.scenes
    ]
    if source == "production":
        expected_names.append(
            Path(experiment.reference_image_spec.character_reference_expected_filename).name
        )
        missing = [name for name in expected_names if not (ROOT / "assets" / name).is_file()]
        if missing:
            raise FileNotFoundError("Missing production image assets: " + ", ".join(missing))
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Missing image SHA-256 manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text("utf-8"))
    if set(manifest) != set(expected_names):
        raise ValueError("Image manifest must contain exactly the selected assets")
    digests = []
    for scene, name in zip(experiment.scenes, expected_names[:3], strict=True):
        path = ROOT / (scene.fixture_frame if source == "fixture" else scene.production_frame)
        digest = frame_digest(path)
        if manifest[name] != digest:
            raise ValueError(f"Frame SHA-256 does not match manifest: {name}")
        digests.append(digest)
    if source == "production":
        portrait_name = expected_names[-1]
        portrait_digest = frame_digest(ROOT / "assets" / portrait_name, MAX_REFERENCE_BYTES)
        if manifest[portrait_name] != portrait_digest:
            raise ValueError(f"Reference portrait SHA-256 does not match manifest: {portrait_name}")
    return digests


def preview(
    experiment: Experiment,
    vidu: ViduConfig,
    wan: WanConfig,
    digests: list[str],
    source: Literal["fixture", "production"],
) -> dict:
    requests = []
    for scene, digest in zip(experiment.scenes, digests, strict=True):
        frame_file = scene.fixture_frame if source == "fixture" else scene.production_frame
        omitted_data_uri = f"data:image/png;base64,<omitted; local-file-sha256={digest}>"
        for provider in ("vidu", "wan"):
            if provider == "vidu":
                body = {
                    "model": vidu.model,
                    "images": [omitted_data_uri],
                    "prompt": scene.motion_prompt_en,
                    "duration": vidu.duration_seconds,
                    "resolution": vidu.resolution,
                    "audio": vidu.audio,
                    "seed": experiment.comparison.seed,
                    "off_peak": vidu.off_peak,
                }
                endpoint = vidu.endpoint
                headers = {"Content-Type": "application/json"}
                expected_output = scene.expected_outputs.vidu
            else:
                body = {
                    "model": wan.model,
                    "input": {
                        "prompt": scene.motion_prompt_en,
                        "media": [{"type": "first_frame", "url": omitted_data_uri}],
                    },
                    "parameters": {
                        "resolution": wan.resolution,
                        "duration": wan.duration_seconds,
                        "prompt_extend": wan.prompt_extend,
                        "watermark": wan.watermark,
                        "seed": experiment.comparison.seed,
                    },
                }
                endpoint = wan.endpoint
                headers = {"Content-Type": "application/json", "X-DashScope-Async": "enable"}
                expected_output = scene.expected_outputs.wan
            requests.append(
                {
                    "provider": provider,
                    "scene_number": scene.scene_number,
                    "method": "POST",
                    "endpoint_template": endpoint,
                    "headers_without_authorization": headers,
                    "body_preview": body,
                    "source_frame": frame_file,
                    "source_frame_sha256": digest,
                    "motion_prompt_sha256": hashlib.sha256(
                        scene.motion_prompt_en.encode("utf-8")
                    ).hexdigest(),
                    "expected_output": expected_output,
                    "submittable": False,
                }
            )
    return {
        "experiment_id": experiment.experiment_id,
        "offline_only": True,
        "frame_source": source,
        "frames_are_mock": source == "fixture",
        "authorization_included": False,
        "requests": requests,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "preview", "schema"))
    parser.add_argument("--frames", choices=("fixture", "production"), default="fixture")
    parser.add_argument("--write", action="store_true", help="write the generated JSON Schema")
    args = parser.parse_args()
    if args.command == "schema":
        schemas = {
            "experiment.schema.json": Experiment.model_json_schema(),
            "still_prompts.schema.json": StillPrompts.model_json_schema(),
        }
        for name, model_schema in schemas.items():
            schema = json.dumps(model_schema, ensure_ascii=False, indent=2) + "\n"
            path = ROOT / name
            if args.write:
                path.write_text(schema, encoding="utf-8")
            elif path.read_text(encoding="utf-8") != schema:
                raise SystemExit(f"Schema drift in {name}; regenerate with schema --write.")
        print(
            "Wrote both JSON Schemas."
            if args.write
            else "Both committed JSON Schemas match the Pydantic models."
        )
        return
    experiment, vidu, wan = load_package()
    load_still_prompts(experiment)
    digests = check_frames(experiment, args.frames)
    if args.command == "preview":
        print(json.dumps(preview(experiment, vidu, wan, digests, args.frames), indent=2))
    else:
        count = "four" if args.frames == "production" else "three"
        print(f"Validated experiment, still prompts, templates, and {count} {args.frames} images.")


if __name__ == "__main__":
    main()

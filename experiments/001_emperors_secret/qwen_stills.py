"""Experiment 001 Qwen stills. Dry-run by default; never submits a video request."""

import argparse
import base64
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from validate import (
    MAX_FRAME_BYTES,
    MAX_REFERENCE_BYTES,
    check_frames,
    frame_digest,
    load_package,
    load_still_prompts,
    rgb_png_digest,
)

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
MODEL = "qwen-image-3.0"
SIZE = "720x1280"
REGION_HOSTS = {
    "beijing": "cn-beijing",
    "singapore": "ap-southeast-1",
    "virginia": "us-east-1",
    "frankfurt": "eu-central-1",
    "tokyo": "ap-northeast-1",
}
# CNY, 1K output tier, Alibaba list prices checked 2026-10-11; verify before live use.
OUTPUT_CNY = {
    "beijing": 0.18,
    "singapore": 0.224826,
    "virginia": 0.18,
    "frankfurt": 0.18,
    "tokyo": 0.18,
}
INPUT_CNY = {
    "beijing": 0.02,
    "singapore": 0.022483,
    "virginia": 0.02,
    "frankfurt": 0.02,
    "tokyo": 0.02,
}
RESULT_HOST = re.compile(r"dashscope-result-[a-z0-9-]+\.oss-[a-z0-9-]+\.aliyuncs\.com\Z")
WORKSPACE = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{1,62}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class Config:
    region: str
    workspace_id: str
    api_key: str = ""

    @classmethod
    def from_env(cls):
        return cls(
            os.getenv("QWEN_IMAGE_REGION", "beijing").strip().lower(),
            os.getenv("QWEN_IMAGE_WORKSPACE_ID", "").strip(),
            os.getenv("DASHSCOPE_API_KEY", ""),
        )

    def endpoint(self):
        if self.region not in REGION_HOSTS:
            raise ValueError(
                "QWEN_IMAGE_REGION must be beijing, singapore, virginia, frankfurt, or tokyo"
            )
        if not WORKSPACE.fullmatch(self.workspace_id):
            raise ValueError("Set a valid QWEN_IMAGE_WORKSPACE_ID for the chosen region")
        host = REGION_HOSTS[self.region]
        return f"https://{self.workspace_id}.{host}.maas.aliyuncs.com/compatible-mode/v1/images/generations"


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def text_digest(value: str) -> str:
    return digest(value.encode("utf-8"))


def _paths(kind: str, scene_number: int | None = None) -> tuple[Path, Path, Path]:
    if kind == "portrait":
        stem = "lin_yue_reference"
    elif kind == "scene" and scene_number in (1, 2, 3):
        stem = f"scene_0{scene_number}_start"
    else:
        raise ValueError("Select portrait or scene 1, 2, or 3")
    return (
        ASSETS / f"{stem}.png",
        ASSETS / f"{stem}.generation.json",
        ASSETS / f"{stem}.approval.json",
    )


def _read_json(path: Path) -> dict:
    if not path.is_file():
        raise ValueError(f"Missing {path.name}; generate and review the asset first")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Invalid {path.name}")
    return value


def _prompt(kind: str, scene_number: int | None = None):
    experiment, _, _ = load_package()
    stills = load_still_prompts(experiment)
    if kind == "portrait":
        return stills.reference_portrait
    if kind == "scene" and scene_number in (1, 2, 3):
        return stills.scene_start_frames[scene_number - 1]
    raise ValueError("Select portrait or scene 1, 2, or 3")


def approved_portrait() -> tuple[bytes, str]:
    image_path, record_path, approval_path = _paths("portrait")
    record = _read_json(record_path)
    approval = _read_json(approval_path)
    image = image_path.read_bytes()
    image_sha = rgb_png_digest(image, image_path.name, MAX_REFERENCE_BYTES)
    prompt_sha = text_digest(_prompt("portrait").prompt_en)
    if not (
        record.get("sha256") == approval.get("sha256") == image_sha
        and record.get("prompt_sha256") == approval.get("prompt_sha256") == prompt_sha
        and record.get("negative_prompt_sha256")
        == text_digest(_prompt("portrait").negative_prompt_en)
        and record.get("model") == MODEL
        and record.get("mode") == "text_to_image_master"
    ):
        raise ValueError(
            "Portrait approval no longer matches its bytes, prompt, and generation record"
        )
    return image, image_sha


def build_body(kind: str, scene_number: int | None = None) -> tuple[dict, str | None]:
    item = _prompt(kind, scene_number)
    body = {
        "model": MODEL,
        "prompt": item.prompt_en,
        "negative_prompt": item.negative_prompt_en,
        "size": SIZE,
        "n": 1,
        "prompt_extend": False,
        "enable_thinking": False,
        "watermark": False,
    }
    if kind == "scene":
        image, reference_sha = approved_portrait()
        body["image"] = "data:image/png;base64," + base64.b64encode(image).decode("ascii")
        return body, reference_sha
    return body, None


def _result_url(response: dict) -> str:
    data = response.get("data")
    if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
        raise ValueError("Qwen returned no single image result")
    value = data[0].get("url")
    if not isinstance(value, str) or value.strip() != value or any(c.isspace() for c in value):
        raise ValueError("Qwen returned an invalid image URL")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not RESULT_HOST.fullmatch(parsed.hostname)
        or parsed.username
        or parsed.password
        or parsed.port is not None
        or parsed.fragment
    ):
        raise ValueError("Qwen returned an untrusted image URL")
    return value


def request_image(config: Config, body: dict, client: httpx.Client, max_bytes: int) -> bytes:
    if not config.api_key.strip():
        raise ValueError("Set DASHSCOPE_API_KEY in the local environment before a paid call")
    response = client.post(
        config.endpoint(),
        headers={"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"},
        json=body,
        follow_redirects=False,
    )
    if response.is_redirect:
        raise ValueError("Qwen API redirected the generation request")
    response.raise_for_status()
    try:
        url = _result_url(response.json())
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Qwen returned invalid JSON") from exc
    # Signed result URLs are untrusted. Never send the key on GET or follow redirects.
    with client.stream("GET", url, follow_redirects=False) as download:
        if download.is_redirect:
            raise ValueError("Qwen image download redirected")
        download.raise_for_status()
        if download.headers.get("content-type", "").split(";")[0].lower() != "image/png":
            raise ValueError("Qwen image download is not PNG")
        size = download.headers.get("content-length")
        if size is not None and (not size.isdecimal() or int(size) > max_bytes):
            raise ValueError("Qwen image download exceeds the asset size limit")
        image = bytearray()
        for chunk in download.iter_bytes():
            image.extend(chunk)
            if len(image) > max_bytes:
                raise ValueError("Qwen image download exceeds the asset size limit")
    rgb_png_digest(image, "Qwen output", max_bytes)
    return bytes(image)


def _write_once(path: Path, data: bytes) -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output:
        output.write(data)


def _write_json_once(path: Path, value: dict) -> None:
    _write_once(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def generate(kind: str, scene_number: int | None, config: Config, client: httpx.Client) -> str:
    image_path, record_path, _ = _paths(kind, scene_number)
    if image_path.exists() or record_path.exists():
        raise ValueError(f"{image_path.name} already exists; no automatic overwrite or retry")
    body, reference_sha = build_body(kind, scene_number)
    max_bytes = MAX_REFERENCE_BYTES if kind == "portrait" else MAX_FRAME_BYTES
    image = request_image(config, body, client, max_bytes)
    image_sha = digest(image)
    item = _prompt(kind, scene_number)
    record = {
        "model": MODEL,
        "mode": item.generation_mode,
        "sha256": image_sha,
        "prompt_sha256": text_digest(item.prompt_en),
        "negative_prompt_sha256": text_digest(item.negative_prompt_en),
        "reference_sha256": reference_sha,
    }
    _write_once(image_path, image)
    _write_json_once(record_path, record)
    return image_sha


def approve(kind: str, scene_number: int | None, reviewed_sha: str) -> None:
    if not SHA256.fullmatch(reviewed_sha):
        raise ValueError("Provide the complete lowercase SHA-256 of the visually reviewed image")
    image_path, record_path, approval_path = _paths(kind, scene_number)
    record = _read_json(record_path)
    actual_sha = frame_digest(
        image_path, MAX_REFERENCE_BYTES if kind == "portrait" else MAX_FRAME_BYTES
    )
    if actual_sha != reviewed_sha or record.get("sha256") != actual_sha:
        raise ValueError("Reviewed SHA-256 does not match the saved image and generation record")
    item = _prompt(kind, scene_number)
    if record.get("prompt_sha256") != text_digest(item.prompt_en):
        raise ValueError("Prompt changed since this image was generated")
    if record.get("negative_prompt_sha256") != text_digest(item.negative_prompt_en):
        raise ValueError("Negative prompt changed since this image was generated")
    if record.get("model") != MODEL or record.get("mode") != item.generation_mode:
        raise ValueError("Generation record does not match this Qwen experiment")
    if kind == "scene" and record.get("reference_sha256") != approved_portrait()[1]:
        raise ValueError("Scene was not conditioned on the approved portrait")
    _write_json_once(
        approval_path, {"sha256": actual_sha, "prompt_sha256": record["prompt_sha256"]}
    )


def write_manifest() -> dict:
    _, portrait_sha = approved_portrait()
    manifest = {"lin_yue_reference.png": portrait_sha}
    for number in (1, 2, 3):
        image_path, record_path, approval_path = _paths("scene", number)
        record = _read_json(record_path)
        approval = _read_json(approval_path)
        image_sha = frame_digest(image_path)
        prompt = _prompt("scene", number)
        if not (
            approval.get("sha256") == record.get("sha256") == image_sha
            and approval.get("prompt_sha256")
            == record.get("prompt_sha256")
            == text_digest(prompt.prompt_en)
            and record.get("reference_sha256") == portrait_sha
            and record.get("negative_prompt_sha256") == text_digest(prompt.negative_prompt_en)
            and record.get("model") == MODEL
            and record.get("mode") == "image_to_image_reference"
        ):
            raise ValueError(f"Scene {number} approval, prompt, or portrait reference has changed")
        manifest[image_path.name] = image_sha
    _write_json_once(ASSETS / "manifest.json", manifest)
    experiment, _, _ = load_package()
    check_frames(experiment, "production")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("portrait", "scene"):
        command = sub.add_parser(
            name, help="preview by default; one paid request only with all gates"
        )
        if name == "scene":
            command.add_argument("--number", type=int, required=True, choices=(1, 2, 3))
        command.add_argument("--execute", action="store_true")
        command.add_argument("--confirm-cost", action="store_true")
    for name in ("approve-portrait", "approve-scene"):
        command = sub.add_parser(name)
        if name == "approve-scene":
            command.add_argument("--number", type=int, required=True, choices=(1, 2, 3))
        command.add_argument("--sha256", required=True)
    sub.add_parser("manifest")
    args = parser.parse_args()
    try:
        if args.command in ("portrait", "scene"):
            kind = args.command
            number = getattr(args, "number", None)
            config = Config.from_env()
            body, reference_sha = build_body(kind, number)
            amount = OUTPUT_CNY[config.region] + (
                INPUT_CNY[config.region] if kind == "scene" else 0
            )
            preview = dict(body)
            if reference_sha:
                preview["image"] = f"<approved portrait; sha256={reference_sha}; base64 omitted>"
            print(
                json.dumps(
                    {
                        "dry_run": not args.execute,
                        "model": MODEL,
                        "region": config.region,
                        "estimated_cny": amount,
                        "endpoint": config.endpoint(),
                        "body_preview": preview,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            if args.execute:
                if not args.confirm_cost or os.getenv("EXPERIMENT_001_ENABLE_PAID_CALLS") != "true":
                    raise ValueError(
                        "Paid call blocked: require --confirm-cost and "
                        "EXPERIMENT_001_ENABLE_PAID_CALLS=true"
                    )
                with httpx.Client(timeout=600, follow_redirects=False) as client:
                    image_sha = generate(kind, number, config, client)
                print(f"Saved one candidate {kind}; SHA-256 {image_sha}. Human review is required.")
        elif args.command == "approve-portrait":
            approve("portrait", None, args.sha256)
            print("Portrait approval recorded for the exact reviewed SHA-256.")
        elif args.command == "approve-scene":
            approve("scene", args.number, args.sha256)
            print(f"Scene {args.number} approval recorded for the exact reviewed SHA-256.")
        else:
            print(json.dumps(write_manifest(), indent=2))
    except (ValueError, OSError, httpx.HTTPError, KeyError) as exc:
        # Never print credential-bearing headers, request bodies, or signed URLs.
        if isinstance(exc, httpx.HTTPStatusError):
            message = f"Qwen request failed with HTTP {exc.response.status_code}; no retry was made"
        elif isinstance(exc, httpx.HTTPError):
            message = "Qwen request or result download failed; no retry was made"
        else:
            message = str(exc)
        print(message, file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()

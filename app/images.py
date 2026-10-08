import base64
import binascii
import hashlib
import re
import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx

from app.config import Settings
from app.phase2_models import ImageAsset, ProjectV2, SceneV2


class ImageProviderError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        self.status_code = status_code
        super().__init__(message)


@dataclass(frozen=True)
class GeneratedImage:
    data: bytes
    extension: str
    width: int
    height: int
    model: str
    provider: str
    is_mock: bool


class ImageProvider(Protocol):
    async def generate(self, prompt: str, scene_number: int) -> GeneratedImage: ...


class MockImageProvider:
    async def generate(self, prompt: str, scene_number: int) -> GeneratedImage:
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]
        svg = f"""<svg xmlns="http://www.w3.org/2000/svg"
 width="360" height="640" viewBox="0 0 360 640">
<rect width="360" height="640" fill="#182a24"/>
<rect x="18" y="18" width="324" height="604"
 fill="none" stroke="#ba9b60" stroke-width="2"/>
<circle cx="180" cy="225" r="75" fill="#36594c"/>
<path d="M36 490 Q180 320 324 490V604H36Z" fill="#284538"/>
<text x="180" y="92" fill="#e5ce9a" text-anchor="middle"
 font-size="22" font-family="serif">DynastyAI</text>
<text x="180" y="270" fill="#e5ce9a" text-anchor="middle"
 font-size="76" font-family="serif">朝</text>
<text x="180" y="535" fill="white" text-anchor="middle"
 font-size="21" font-family="sans-serif">SCENE {scene_number:02}</text>
<text x="180" y="565" fill="#ffdd96" text-anchor="middle"
 font-size="14" font-family="sans-serif">MOCK PLACEHOLDER</text>
<text x="180" y="587" fill="#ffdd96" text-anchor="middle"
 font-size="12" font-family="sans-serif">NOT AI GENERATED · {digest}</text>
</svg>"""
        return GeneratedImage(
            data=svg.encode("utf-8"),
            extension="svg",
            width=360,
            height=640,
            model="local-placeholder-v1",
            provider="mock",
            is_mock=True,
        )


class OpenAIImageProvider:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def generate(self, prompt: str, scene_number: int) -> GeneratedImage:
        if not self.settings.image_api_key.strip():
            raise ImageProviderError("Set IMAGE_API_KEY in .env, or use IMAGE_PROVIDER=mock.", 503)
        try:
            async with httpx.AsyncClient(timeout=self.settings.image_timeout_seconds) as client:
                response = await client.post(
                    self.settings.image_api_base_url.rstrip("/") + "/images/generations",
                    headers={"Authorization": f"Bearer {self.settings.image_api_key}"},
                    json={
                        "model": self.settings.image_model,
                        "prompt": prompt,
                        "n": 1,
                        "size": "1152x2048",
                        "output_format": "png",
                        "quality": "medium",
                    },
                )
                response.raise_for_status()
                encoded = response.json()["data"][0]["b64_json"]
                data = base64.b64decode(encoded, validate=True)
                if len(data) > 25 * 1024 * 1024 or len(data) < 24:
                    raise ValueError("Unexpected image size")
                if data[:16] != b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR":
                    raise ValueError("Provider did not return PNG data")
                width, height = struct.unpack(">II", data[16:24])
                if width < 1 or height < 1 or width * 16 != height * 9:
                    raise ValueError("Provider did not return a 9:16 image")
                return GeneratedImage(
                    data=data,
                    extension="png",
                    width=width,
                    height=height,
                    model=self.settings.image_model,
                    provider="openai",
                    is_mock=False,
                )
        except httpx.TimeoutException as exc:
            raise ImageProviderError(
                "Image generation timed out. Please retry this scene.", 504
            ) from exc
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            message = (
                "Image provider rejected the API credentials. Check IMAGE_API_KEY."
                if code in (401, 403)
                else "Image provider is rate limiting requests. Retry this scene later."
                if code == 429
                else "Image provider could not generate this scene."
            )
            raise ImageProviderError(message, 503 if code == 429 else 502) from exc
        except httpx.RequestError as exc:
            raise ImageProviderError("Unable to reach the image provider. Check its URL.") from exc
        except (ValueError, KeyError, IndexError, TypeError, binascii.Error) as exc:
            raise ImageProviderError("Image provider returned invalid image data.") from exc


_MAX_IMAGE_BYTES = 25 * 1024 * 1024
_QWEN_RESULT_HOST = re.compile(r"dashscope-result-[a-z0-9-]+\.oss-[a-z0-9-]+\.aliyuncs\.com\Z")


def _qwen_result_url(value: str) -> str:
    """Only fetch signed PNG results from Alibaba's documented OSS result hosts."""
    if not isinstance(value, str) or value.strip() != value or any(c.isspace() for c in value):
        raise ValueError("Invalid result URL")
    url = urlsplit(value)
    if (
        url.scheme != "https"
        or not url.hostname
        or not _QWEN_RESULT_HOST.fullmatch(url.hostname)
        or url.username
        or url.password
        or url.port is not None
        or url.fragment
    ):
        raise ValueError("Untrusted result URL")
    return value


def _png_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) > _MAX_IMAGE_BYTES or len(data) < 24:
        raise ValueError("Unexpected image size")
    if data[:16] != b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR":
        raise ValueError("Provider did not return PNG data")
    width, height = struct.unpack(">II", data[16:24])
    if width < 1 or height < 1 or width * 16 != height * 9:
        raise ValueError("Provider did not return a 9:16 image")
    return width, height


class AlibabaImageProvider:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def generate(self, prompt: str, scene_number: int) -> GeneratedImage:
        if not self.settings.image_api_key.strip():
            raise ImageProviderError("Set IMAGE_API_KEY in .env, or use IMAGE_PROVIDER=mock.", 503)
        try:
            async with httpx.AsyncClient(timeout=self.settings.image_timeout_seconds) as client:
                response = await client.post(
                    self.settings.image_api_base_url.rstrip("/") + "/images/generations",
                    headers={"Authorization": f"Bearer {self.settings.image_api_key}"},
                    json={
                        "model": self.settings.image_model,
                        "prompt": prompt,
                        "n": 1,
                        "size": "1152x2048",
                        "prompt_extend": False,
                        "enable_thinking": False,
                    },
                )
                response.raise_for_status()
            url = _qwen_result_url(response.json()["data"][0]["url"])
            # The signed URL is untrusted provider output. Never forward the API
            # key, follow redirects, or retain the expiring URL in project JSON.
            async with httpx.AsyncClient(
                timeout=self.settings.image_timeout_seconds, follow_redirects=False
            ) as client:
                async with client.stream("GET", url) as image_response:
                    image_response.raise_for_status()
                    if image_response.is_redirect:
                        raise ValueError("Image download redirected")
                    if (
                        image_response.headers.get("content-type", "").split(";")[0].lower()
                        != "image/png"
                    ):
                        raise ValueError("Image download is not PNG")
                    content_length = image_response.headers.get("content-length")
                    if content_length and int(content_length) > _MAX_IMAGE_BYTES:
                        raise ValueError("Image download is too large")
                    data = bytearray()
                    async for chunk in image_response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > _MAX_IMAGE_BYTES:
                            raise ValueError("Image download is too large")
            width, height = _png_dimensions(data)
            return GeneratedImage(
                data=bytes(data),
                extension="png",
                width=width,
                height=height,
                model=self.settings.image_model,
                provider="alibaba",
                is_mock=False,
            )
        except httpx.TimeoutException as exc:
            raise ImageProviderError(
                "Image generation or download timed out. Please retry this scene.", 504
            ) from exc
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            message = (
                "Image provider rejected the API credentials. Check IMAGE_API_KEY."
                if code in (401, 403) and exc.request.method == "POST"
                else "Image provider is rate limiting requests. Retry this scene later."
                if code == 429 and exc.request.method == "POST"
                else "Image provider could not generate or download this scene."
            )
            raise ImageProviderError(message, 503 if code == 429 else 502) from exc
        except httpx.RequestError as exc:
            raise ImageProviderError(
                "Unable to reach the image provider or download its result."
            ) from exc
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ImageProviderError(
                "Image provider returned invalid image data or an unsafe URL."
            ) from exc


def get_provider(settings: Settings) -> ImageProvider:
    if settings.image_provider == "mock":
        return MockImageProvider()
    if settings.image_provider == "openai":
        return OpenAIImageProvider(settings)
    if settings.image_provider == "alibaba":
        return AlibabaImageProvider(settings)
    raise ImageProviderError("IMAGE_PROVIDER must be 'mock', 'openai', or 'alibaba'.", 503)


def asset_directory(settings: Settings) -> Path:
    return Path(settings.asset_dir).expanduser().resolve()


def asset_path(settings: Settings, project_id: UUID, asset_id: UUID, extension: str) -> Path:
    return asset_directory(settings) / str(project_id) / f"{asset_id}.{extension}"


async def generate_scene_image(
    project: ProjectV2, scene: SceneV2, settings: Settings
) -> ImageAsset:
    provider = get_provider(settings)
    result = await provider.generate(scene.final_image_prompt, scene.scene_number)
    asset_id = uuid4()
    try:
        path = asset_path(settings, project.project_id, asset_id, result.extension)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as output:
            output.write(result.data)
    except OSError as exc:
        raise ImageProviderError("Unable to save the generated image locally.", 500) from exc
    return ImageAsset(
        asset_id=asset_id,
        project_id=project.project_id,
        scene_number=scene.scene_number,
        url=f"/api/assets/{project.project_id}/{asset_id}",
        provider=result.provider,
        model=result.model,
        is_mock=result.is_mock,
        created_at=datetime.now(timezone.utc),
        prompt_sha256=hashlib.sha256(scene.final_image_prompt.encode("utf-8")).hexdigest(),
        width=result.width,
        height=result.height,
    )

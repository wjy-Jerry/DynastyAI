import hashlib
import json
import struct
import zlib

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.images import AlibabaImageProvider, MockImageProvider, OpenAIImageProvider, get_provider
from app.main import app, get_settings
from app.models import StoryRequest
from app.phase2 import demo_characters
from app.storyboard import demo_storyboard

BRIEF = {
    "story_idea": "A palace physician discovers a conspiracy against the emperor.",
    "genre": "Palace intrigue",
    "target_duration": 60,
    "output_language": "English",
}
RESULT_URL = "https://dashscope-result-sz.oss-cn-shenzhen.aliyuncs.com/result.png?Expires=123&Signature=secret"


def tiny_png(width=9, height=16):
    def chunk(kind, data):
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    rows = (b"\x00" + b"\x00\x00\x00" * width) * height
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


@pytest.fixture
def client(tmp_path):
    app.dependency_overrides[get_settings] = lambda: Settings(
        demo_mode=True, image_provider="mock", asset_dir=str(tmp_path / "assets")
    )
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def qwen_image_settings(client, monkeypatch, tmp_path, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(
        "app.images.httpx.AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    app.dependency_overrides[get_settings] = lambda: Settings(
        image_provider="alibaba",
        image_api_key="fake-qwen-key",
        image_api_base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        image_model="qwen-image-3.0",
        asset_dir=str(tmp_path / "assets"),
    )


def test_provider_selection_and_missing_key(client, tmp_path):
    assert isinstance(get_provider(Settings(image_provider="alibaba")), AlibabaImageProvider)
    assert isinstance(get_provider(Settings(image_provider="openai")), OpenAIImageProvider)
    assert isinstance(get_provider(Settings(image_provider="mock")), MockImageProvider)
    project = client.post("/api/projects", json=BRIEF).json()
    app.dependency_overrides[get_settings] = lambda: Settings(
        image_provider="alibaba", image_api_key="", asset_dir=str(tmp_path / "assets")
    )
    assert client.get("/api/image-health").json() == {"provider": "alibaba", "configured": False}
    response = client.post("/api/images/scenes/1", json=project)
    assert response.status_code == 503 and "IMAGE_API_KEY" in response.text


def test_qwen_image_url_download_persistence_and_regeneration(client, monkeypatch, tmp_path):
    project = client.post("/api/projects", json=BRIEF).json()
    seen_prompts = []

    def handler(request):
        if request.method == "POST":
            assert str(request.url) == (
                "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/images/generations"
            )
            assert request.headers["authorization"] == "Bearer fake-qwen-key"
            body = json.loads(request.content)
            assert body == {
                "model": "qwen-image-3.0",
                "prompt": body["prompt"],
                "n": 1,
                "size": "1152x2048",
                "prompt_extend": False,
                "enable_thinking": False,
            }
            seen_prompts.append(body["prompt"])
            return httpx.Response(200, json={"data": [{"url": RESULT_URL}]})
        assert str(request.url) == RESULT_URL
        assert "authorization" not in request.headers
        return httpx.Response(200, content=tiny_png(), headers={"Content-Type": "image/png"})

    qwen_image_settings(client, monkeypatch, tmp_path, handler)
    assert client.get("/api/image-health").json() == {"provider": "alibaba", "configured": True}
    assets = [
        client.post(f"/api/images/scenes/{number}", json=project).json()["image_asset"]
        for number in (1, 2, 1)
    ]
    assert seen_prompts == [project["scenes"][i]["final_image_prompt"] for i in (0, 1, 0)]
    assert assets[0]["asset_id"] != assets[2]["asset_id"]
    assert all(asset["provider"] == "alibaba" and not asset["is_mock"] for asset in assets)
    assert all(asset["width"] * 16 == asset["height"] * 9 for asset in assets)
    assert assets[0]["prompt_sha256"] == hashlib.sha256(seen_prompts[0].encode()).hexdigest()
    assert RESULT_URL not in json.dumps(assets)
    assert client.get(assets[2]["url"]).content == tiny_png()
    assert len(list((tmp_path / "assets").rglob("*.png"))) == 3
    project["scenes"][0]["image_asset"] = assets[2]
    assert client.post("/api/projects/validate", json=project).json() == project


@pytest.mark.parametrize(
    "url",
    [
        "http://dashscope-result-sz.oss-cn-shenzhen.aliyuncs.com/x.png",
        "https://127.0.0.1/x.png",
        "https://dashscope-result-sz.oss-cn-shenzhen.aliyuncs.com.evil.test/x.png",
        "https://dashscope-result-sz.oss-cn-shenzhen.aliyuncs.com@evil.test/x.png",
        "https://dashscope-result-sz.oss-cn-shenzhen.aliyuncs.com:8443/x.png",
        "https://dashscope-result-sz.oss-cn-shenzhen.aliyuncs.com/x.png#fragment",
    ],
)
def test_qwen_rejects_untrusted_url_without_fetch(client, monkeypatch, tmp_path, url):
    project = client.post("/api/projects", json=BRIEF).json()
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"data": [{"url": url}]})

    qwen_image_settings(client, monkeypatch, tmp_path, handler)
    response = client.post("/api/images/scenes/1", json=project)
    assert response.status_code == 502
    assert len(calls) == 1
    assert not list((tmp_path / "assets").rglob("*.png"))


@pytest.mark.parametrize("download", ["redirect", "html", "oversize", "wrong_ratio"])
def test_qwen_rejects_invalid_download(client, monkeypatch, tmp_path, download):
    project = client.post("/api/projects", json=BRIEF).json()

    def handler(request):
        if request.method == "POST":
            return httpx.Response(200, json={"data": [{"url": RESULT_URL}]})
        if download == "redirect":
            return httpx.Response(302, headers={"Location": "http://127.0.0.1/private"})
        if download == "html":
            return httpx.Response(
                200, content=b"<html>bad</html>", headers={"Content-Type": "text/html"}
            )
        if download == "oversize":
            return httpx.Response(
                200, headers={"Content-Type": "image/png", "Content-Length": str(26 * 1024 * 1024)}
            )
        return httpx.Response(200, content=tiny_png(16, 9), headers={"Content-Type": "image/png"})

    qwen_image_settings(client, monkeypatch, tmp_path, handler)
    response = client.post("/api/images/scenes/1", json=project)
    assert response.status_code == 502
    assert not list((tmp_path / "assets").rglob("*.png"))


@pytest.mark.parametrize("code,expected", [(401, 502), (429, 503), (500, 502)])
def test_qwen_api_errors_are_sanitized(client, monkeypatch, tmp_path, code, expected):
    project = client.post("/api/projects", json=BRIEF).json()
    qwen_image_settings(
        client,
        monkeypatch,
        tmp_path,
        lambda _: httpx.Response(code, text="secret signed URL and private details"),
    )
    response = client.post("/api/images/scenes/1", json=project)
    assert response.status_code == expected
    assert "private details" not in response.text


@pytest.mark.parametrize("version", ["1", "2"])
def test_qwen_storyboard_json_contract(client, monkeypatch, version):
    story_request = StoryRequest(**BRIEF)
    board = demo_storyboard(story_request)
    draft = {
        "title": board.title,
        "scenes": [scene.model_dump() for scene in board.scenes],
        "character_bible": [character.model_dump() for character in demo_characters(story_request)],
        "visual_style": {
            "historical_era": "Fictional Chinese court",
            "visual_style": "Cinematic",
            "lighting": "Lantern light",
            "cinematography": "Close shots",
            "color_mood": "Jade and amber",
            "aspect_ratio": "9:16",
        },
    }

    def handler(request):
        assert (
            str(request.url)
            == "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions"
        )
        assert request.headers["authorization"] == "Bearer fake-qwen-key"
        body = json.loads(request.content)
        assert body["model"] == "qwen3.7-flash"
        assert body["response_format"] == {"type": "json_object"}
        assert body["enable_thinking"] is False
        assert "max_tokens" not in body
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(draft if version == "2" else board.model_dump())
                        }
                    }
                ]
            },
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        "app.storyboard.httpx.AsyncClient" if version == "1" else "app.phase2.httpx.AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    app.dependency_overrides[get_settings] = lambda: Settings(
        demo_mode=False,
        llm_provider="alibaba",
        llm_api_key="fake-qwen-key",
        llm_base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        llm_model="qwen3.7-flash",
    )
    response = client.post("/api/storyboards", json=BRIEF, headers={"X-DynastyAI-Version": version})
    assert response.status_code == 200, response.text
    assert response.json()["schema_version"] == ("2.0" if version == "2" else "1.0")

import base64
import hashlib
import json
import struct
import zlib

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app, get_settings
from app.models import Project, StoryRequest
from app.phase2 import demo_characters
from app.phase2_models import ProjectV2
from app.prompts import character_block, compose_prompt, prompt_is_current
from app.storyboard import demo_storyboard

REQUEST = {
    "story_idea": "A palace physician discovers a conspiracy against the emperor.",
    "genre": "Palace intrigue",
    "target_duration": 60,
    "output_language": "English",
}


@pytest.fixture
def client(tmp_path):
    app.dependency_overrides[get_settings] = lambda: Settings(
        demo_mode=True, image_provider="mock", asset_dir=str(tmp_path / "assets")
    )
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def create_project(client):
    response = client.post("/api/projects", json=REQUEST)
    assert response.status_code == 200, response.text
    return response.json()


def test_character_bible_validation_and_links(client):
    project = create_project(client)
    assert project["schema_version"] == "2.0"
    assert project["visual_style"]["aspect_ratio"] == "9:16"
    assert project["character_bible"][0]["facial_features"]
    assert client.post("/api/projects/validate", json=project).json() == project
    project["character_bible"][0]["facial_features"] = ""
    assert client.post("/api/projects/validate", json=project).status_code == 422


@pytest.mark.parametrize(
    "mutation", ["duplicate_id", "duplicate_name", "missing_id", "wrong_name", "bad_ratio"]
)
def test_invalid_character_or_style_rejected(client, mutation):
    project = create_project(client)
    if mutation == "duplicate_id":
        project["character_bible"][1]["id"] = project["character_bible"][0]["id"]
    elif mutation == "duplicate_name":
        project["character_bible"][1]["name"] = project["character_bible"][0]["name"]
    elif mutation == "missing_id":
        project["scenes"][0]["character_ids"][0] = "absent-id"
    elif mutation == "wrong_name":
        project["scenes"][0]["characters"][0] = "Other name"
    else:
        project["visual_style"]["aspect_ratio"] = "1:1"
    assert client.post("/api/projects/validate", json=project).status_code == 422


def test_prompt_composition_reuses_exact_identity(client):
    project = ProjectV2.model_validate(create_project(client))
    identity = character_block(project.character_bible[0])
    assert sum(identity in scene.final_image_prompt for scene in project.scenes) == 3
    assert "Facial features:" in identity
    assert "Costume:" in identity
    for scene in project.scenes:
        assert scene.final_image_prompt == compose_prompt(
            scene, project.character_bible, project.visual_style
        )
        assert prompt_is_current(project, scene)
        assert scene.visual_prompt in scene.final_image_prompt
        assert scene.camera_description in scene.final_image_prompt
    project.character_bible[0].facial_features = "New distinguishing scar"
    assert not prompt_is_current(project, project.scenes[0])


def test_refresh_prompts_and_edited_final_prompt_sent_verbatim(client, tmp_path):
    project = create_project(client)
    project["character_bible"][0]["facial_features"] = "A tiny silver eyebrow scar"
    conflict = client.post("/api/images/scenes/1", json=project)
    assert conflict.status_code == 409
    assert not list((tmp_path / "assets").glob("**/*.*"))
    refreshed = client.post("/api/projects/prompts/refresh", json=project)
    assert refreshed.status_code == 200, refreshed.text
    project = refreshed.json()
    assert "A tiny silver eyebrow scar" in project["scenes"][0]["final_image_prompt"]
    project["scenes"][0]["final_image_prompt"] += "\nAdditional direction: flying petals."
    result = client.post("/api/images/scenes/1", json=project)
    assert result.status_code == 200, result.text
    asset = result.json()["image_asset"]
    assert (
        asset["prompt_sha256"]
        == hashlib.sha256(project["scenes"][0]["final_image_prompt"].encode()).hexdigest()
    )


def test_mock_images_per_scene_regeneration_and_asset_persistence(client, tmp_path):
    project = create_project(client)
    first = client.post("/api/images/scenes/1", json=project).json()["image_asset"]
    second = client.post("/api/images/scenes/2", json=project).json()["image_asset"]
    replacement = client.post("/api/images/scenes/1", json=project).json()["image_asset"]
    assert first["asset_id"] != replacement["asset_id"]
    assert second["asset_id"] not in (first["asset_id"], replacement["asset_id"])
    assert all(
        asset["is_mock"] and asset["provider"] == "mock" for asset in (first, second, replacement)
    )
    assert all(asset["width"] * 16 == asset["height"] * 9 for asset in (first, second))
    response = client.get(replacement["url"])
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert b"MOCK PLACEHOLDER" in response.content
    assert b"NOT AI GENERATED" in response.content
    assert client.get(second["url"]).status_code == 200
    assert len(list((tmp_path / "assets").rglob("*.svg"))) == 3
    project["scenes"][0]["image_asset"] = replacement
    project["scenes"][1]["image_asset"] = second
    assert client.post("/api/projects/validate", json=project).json() == project
    project["scenes"][0]["image_asset"]["url"] = second["url"]
    assert client.post("/api/projects/validate", json=project).status_code == 422
    assert (
        client.get(
            "/api/assets/00000000-0000-0000-0000-000000000000/00000000-0000-0000-0000-000000000000"
        ).status_code
        == 404
    )


def test_phase1_migration_preserves_story_and_marks_missing_descriptions(client):
    request = StoryRequest(**REQUEST)
    old = Project(
        **demo_storyboard(request).model_dump(), request=request, generation_mode="demo"
    ).model_dump(mode="json")
    response = client.post("/api/projects/migrate", json=old)
    assert response.status_code == 200, response.text
    new = response.json()
    assert new["schema_version"] == "2.0"
    assert new["migrated_from"] == "1.0"
    assert new["title"] == old["title"]
    assert [s["narration"] for s in new["scenes"]] == [s["narration"] for s in old["scenes"]]
    assert "unspecified" in new["character_bible"][0]["appearance"]
    assert client.post("/api/projects/validate", json=old).json() == old
    assert client.post("/api/projects/validate", json=new).json() == new


def test_unsupported_version_is_helpful(client):
    response = client.post("/api/projects/validate", json={"schema_version": "3.0"})
    assert response.status_code == 422
    assert "Supported versions: 1.0 and 2.0" in response.text


def test_mock_provider_does_not_require_any_credentials(client):
    assert client.get("/api/image-health").json() == {"provider": "mock", "configured": True}
    assert client.post("/api/images/scenes/1", json=create_project(client)).status_code == 200


def test_real_provider_missing_key_is_actionable(client, tmp_path):
    project = create_project(client)
    app.dependency_overrides[get_settings] = lambda: Settings(
        image_provider="openai", image_api_key="", asset_dir=str(tmp_path / "assets")
    )
    assert client.get("/api/image-health").json() == {"provider": "openai", "configured": False}
    response = client.post("/api/images/scenes/1", json=project)
    assert response.status_code == 503
    assert "IMAGE_API_KEY" in response.text


def png_chunk(kind, payload):
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def tiny_png(width=9, height=16):
    rows = (b"\x00" + b"\x00\x00\x00" * width) * height
    return (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + png_chunk(b"IDAT", zlib.compress(rows))
        + png_chunk(b"IEND", b"")
    )


def real_provider_settings(client, monkeypatch, tmp_path, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(
        "app.images.httpx.AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    app.dependency_overrides[get_settings] = lambda: Settings(
        image_provider="openai",
        image_api_key="fake-test-key",
        image_api_base_url="https://image.example/v1",
        image_model="gpt-image-2.5-flare",
        asset_dir=str(tmp_path / "assets"),
    )


def test_real_provider_request_contract_without_billable_call(client, monkeypatch, tmp_path):
    project = create_project(client)

    def handler(request):
        assert request.url == "https://image.example/v1/images/generations"
        assert request.headers["authorization"] == "Bearer fake-test-key"
        body = json.loads(request.content)
        assert body["prompt"] == project["scenes"][0]["final_image_prompt"]
        assert body["size"] == "1152x2048"
        assert body["n"] == 1
        assert body["output_format"] == "png"
        return httpx.Response(
            200, json={"data": [{"b64_json": base64.b64encode(tiny_png()).decode()}]}
        )

    real_provider_settings(client, monkeypatch, tmp_path, handler)
    response = client.post("/api/images/scenes/1", json=project)
    assert response.status_code == 200, response.text
    asset = response.json()["image_asset"]
    assert asset["provider"] == "openai" and not asset["is_mock"]
    assert client.get(asset["url"]).content == tiny_png()


@pytest.mark.parametrize("code,expected", [(401, 502), (403, 502), (429, 503), (500, 502)])
def test_real_provider_errors_are_sanitized(client, monkeypatch, tmp_path, code, expected):
    project = create_project(client)
    real_provider_settings(
        client,
        monkeypatch,
        tmp_path,
        lambda _: httpx.Response(code, text="private provider failure"),
    )
    response = client.post("/api/images/scenes/1", json=project)
    assert response.status_code == expected
    assert "private provider failure" not in response.text


def test_real_provider_invalid_image_is_rejected(client, monkeypatch, tmp_path):
    project = create_project(client)
    real_provider_settings(
        client,
        monkeypatch,
        tmp_path,
        lambda _: httpx.Response(
            200, json={"data": [{"b64_json": base64.b64encode(b"bad").decode()}]}
        ),
    )
    response = client.post("/api/images/scenes/1", json=project)
    assert response.status_code == 502
    assert not list((tmp_path / "assets").rglob("*.png"))


def test_real_provider_wrong_aspect_ratio_is_rejected(client, monkeypatch, tmp_path):
    project = create_project(client)
    encoded = base64.b64encode(tiny_png(16, 9)).decode()
    real_provider_settings(
        client,
        monkeypatch,
        tmp_path,
        lambda _: httpx.Response(200, json={"data": [{"b64_json": encoded}]}),
    )
    response = client.post("/api/images/scenes/1", json=project)
    assert response.status_code == 502
    assert not list((tmp_path / "assets").rglob("*.png"))


def test_real_provider_timeout_is_actionable(client, monkeypatch, tmp_path):
    project = create_project(client)

    def handler(request):
        raise httpx.ReadTimeout("provider secret", request=request)

    real_provider_settings(client, monkeypatch, tmp_path, handler)
    response = client.post("/api/images/scenes/1", json=project)
    assert response.status_code == 504
    assert "retry this scene" in response.text
    assert "provider secret" not in response.text


def test_llm_creates_storyboard_and_bible_together(client, monkeypatch):
    request = StoryRequest(**REQUEST)
    board = demo_storyboard(request)
    draft = {
        "title": board.title,
        "scenes": [scene.model_dump() for scene in board.scenes],
        "character_bible": [c.model_dump() for c in demo_characters(request)],
        "visual_style": {
            "historical_era": "Fictional Chinese court",
            "visual_style": "Cinematic",
            "lighting": "Lantern light",
            "cinematography": "Close shots",
            "color_mood": "Jade and amber",
            "aspect_ratio": "9:16",
        },
    }
    original = httpx.AsyncClient

    def handler(http_request):
        payload = json.loads(http_request.content)
        assert "Character Bible" in payload["messages"][0]["content"]
        assert "character_bible" in payload["messages"][0]["content"]
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(draft)}}]})

    monkeypatch.setattr(
        "app.phase2.httpx.AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    app.dependency_overrides[get_settings] = lambda: Settings(
        demo_mode=False, llm_api_key="fake-test-key"
    )
    response = client.post("/api/projects", json=REQUEST)
    assert response.status_code == 200, response.text
    assert response.json()["generation_mode"] == "llm"
    assert len(response.json()["character_bible"]) == 2

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app, get_settings
from app.storyboard import demo_storyboard

REQUEST = {
    "story_idea": "A palace physician discovers a conspiracy against the emperor.",
    "genre": "Palace intrigue",
    "target_duration": 60,
    "output_language": "English",
}


@pytest.fixture
def client():
    app.dependency_overrides[get_settings] = lambda: Settings(demo_mode=True)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_page_and_health(client):
    assert client.get("/").status_code == 200
    assert "DynastyAI" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/styles.css").status_code == 200
    assert client.get("/api/health").json() == {
        "status": "ok",
        "mode": "demo",
        "configured": True,
    }


@pytest.mark.parametrize("language", ["English", "Simplified Chinese", "Traditional Chinese"])
@pytest.mark.parametrize("duration", [15, 31, 60, 180])
def test_demo_complete_schema_and_exact_duration(client, language, duration):
    response = client.post(
        "/api/storyboards",
        json={
            **REQUEST,
            "output_language": language,
            "target_duration": duration,
        },
    )
    assert response.status_code == 200
    project = response.json()
    assert project["generation_mode"] == "demo"
    assert project["schema_version"] == "1.0"
    assert sum(s["duration"] for s in project["scenes"]) == duration
    assert [s["scene_number"] for s in project["scenes"]] == [1, 2, 3]
    for scene in project["scenes"]:
        assert set(scene) == {
            "scene_number",
            "duration",
            "narration",
            "dialogue",
            "visual_prompt",
            "characters",
            "camera_description",
        }
    assert client.post("/api/projects/validate", json=project).json() == project


@pytest.mark.parametrize(
    "change",
    [
        {"story_idea": "tiny"},
        {"story_idea": " " * 20},
        {"story_idea": "x" * 4001},
        {"target_duration": 0},
        {"target_duration": 181},
        {"target_duration": 30.5},
        {"target_duration": True},
        {"genre": "unknown"},
        {"output_language": "unknown"},
    ],
)
def test_invalid_briefs(client, change):
    assert client.post("/api/storyboards", json={**REQUEST, **change}).status_code == 422


def test_edits_round_trip_and_validation(client):
    project = client.post("/api/storyboards", json=REQUEST).json()
    project["scenes"][0]["narration"] = "A revised opening."
    project["title"] = "Edited title"
    response = client.post("/api/projects/validate", json=project)
    assert response.status_code == 200
    assert response.json() == project
    project["scenes"][0]["duration"] = 99
    assert client.post("/api/projects/validate", json=project).status_code == 422


@pytest.mark.parametrize("mutation", ["number", "speaker", "characters", "empty_prompt", "extra"])
def test_invalid_projects(client, mutation):
    project = client.post("/api/storyboards", json=REQUEST).json()
    scene = project["scenes"][0]
    if mutation == "number":
        scene["scene_number"] = 5
    elif mutation == "speaker":
        scene["dialogue"][0]["character"] = "Unknown"
    elif mutation == "characters":
        scene["characters"] = [""]
    elif mutation == "empty_prompt":
        scene["visual_prompt"] = ""
    else:
        project["unexpected"] = "field"
    assert client.post("/api/projects/validate", json=project).status_code == 422


def test_missing_key_is_actionable(client):
    app.dependency_overrides[get_settings] = lambda: Settings(demo_mode=False, llm_api_key="")
    response = client.post("/api/storyboards", json=REQUEST)
    assert response.status_code == 503
    assert "LLM_API_KEY" in response.json()["detail"]


def mock_provider(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(
        "app.storyboard.httpx.AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    app.dependency_overrides[get_settings] = lambda: Settings(
        demo_mode=False,
        llm_api_key="test-key-not-a-real-secret",
        llm_base_url="https://llm.example/v1",
        llm_model="test-model",
    )


def test_llm_request_and_response(client, monkeypatch):
    def handler(request):
        assert request.url == "https://llm.example/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-key-not-a-real-secret"
        body = json.loads(request.content)
        assert body["model"] == "test-model"
        assert body["response_format"] == {"type": "json_object"}
        assert json.loads(body["messages"][1]["content"]) == REQUEST
        from app.models import StoryRequest

        board = demo_storyboard(StoryRequest(**REQUEST))
        return httpx.Response(
            200, json={"choices": [{"message": {"content": board.model_dump_json()}}]}
        )

    mock_provider(monkeypatch, handler)
    response = client.post("/api/storyboards", json=REQUEST)
    assert response.status_code == 200
    assert response.json()["generation_mode"] == "llm"
    assert "test-key" not in response.text


@pytest.mark.parametrize(
    "provider_status,expected", [(401, 502), (403, 502), (429, 503), (500, 502)]
)
def test_provider_error_sanitized(client, monkeypatch, provider_status, expected):
    mock_provider(
        monkeypatch, lambda _: httpx.Response(provider_status, text="secret provider error")
    )
    response = client.post("/api/storyboards", json=REQUEST)
    assert response.status_code == expected
    assert "secret provider error" not in response.text


def test_timeout(client, monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout("private details", request=request)

    mock_provider(monkeypatch, handler)
    response = client.post("/api/storyboards", json=REQUEST)
    assert response.status_code == 504
    assert "timed out" in response.text


def test_connection_error(client, monkeypatch):
    def handler(request):
        raise httpx.ConnectError("private network details", request=request)

    mock_provider(monkeypatch, handler)
    response = client.post("/api/storyboards", json=REQUEST)
    assert response.status_code == 502
    assert "private network details" not in response.text


@pytest.mark.parametrize("content", ["not json", "{}", '{"title":"Bad","scenes":[]}'])
def test_invalid_llm_output(client, monkeypatch, content):
    mock_provider(
        monkeypatch,
        lambda _: httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content}}],
            },
        ),
    )
    assert client.post("/api/storyboards", json=REQUEST).status_code == 502


def test_llm_duration_mismatch(client, monkeypatch):
    from app.models import StoryRequest

    board = demo_storyboard(StoryRequest(**REQUEST)).model_dump()
    board["scenes"][0]["duration"] += 1
    mock_provider(
        monkeypatch,
        lambda _: httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(board)}}],
            },
        ),
    )
    response = client.post("/api/storyboards", json=REQUEST)
    assert response.status_code == 502
    assert "durations" in response.text

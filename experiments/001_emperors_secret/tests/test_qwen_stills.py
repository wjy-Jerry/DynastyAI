"""Offline request, approval, and asset tests; no provider calls or real images."""

import base64
import json
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import qwen_stills as qwen  # noqa: E402
import validate as validation  # noqa: E402


@pytest.fixture
def asset_area(tmp_path, monkeypatch):
    assets = tmp_path / "assets"
    monkeypatch.setattr(qwen, "ASSETS", assets)
    return assets


def _png():
    return (ROOT / "fixtures/scene_01_start.mock.png").read_bytes()


def _client(calls, image=None, result=None, content_type="image/png", status=200):
    image = _png() if image is None else image
    url = "https://dashscope-result-sz.oss-cn-shenzhen.aliyuncs.com/example.png?Expires=1"

    def handle(request):
        calls.append(request)
        if request.method == "POST":
            return httpx.Response(
                status, json=result if result is not None else {"data": [{"url": url}]}
            )
        return httpx.Response(200, content=image, headers={"content-type": content_type})

    return httpx.Client(transport=httpx.MockTransport(handle), follow_redirects=False)


def _config():
    return qwen.Config("beijing", "workspace123", "test-only-secret")


def test_portrait_is_one_text_only_request_and_writes_candidate(asset_area):
    calls = []
    with _client(calls) as client:
        sha = qwen.generate("portrait", None, _config(), client)
    post, download = calls
    payload = json.loads(post.content)
    assert post.url.path.endswith("/compatible-mode/v1/images/generations")
    assert payload["model"] == "qwen-image-3.0"
    assert payload["size"] == "720x1280" and payload["n"] == 1
    assert payload["prompt_extend"] is False
    assert "image" not in payload
    assert payload["prompt"] == qwen._prompt("portrait").prompt_en
    assert payload["negative_prompt"] == qwen._prompt("portrait").negative_prompt_en
    assert "authorization" not in download.headers
    assert qwen.digest(_png()) == sha
    assert (asset_area / "lin_yue_reference.png").read_bytes() == _png()
    with _client([]) as client, pytest.raises(ValueError, match="already exists"):
        qwen.generate("portrait", None, _config(), client)


def test_scene_requires_human_approval_and_submits_exact_reference(asset_area):
    calls = []
    with _client(calls) as client:
        portrait_sha = qwen.generate("portrait", None, _config(), client)
    with _client(calls) as client, pytest.raises(ValueError, match="approval"):
        qwen.generate("scene", 1, _config(), client)
    assert len(calls) == 2
    with pytest.raises(ValueError, match="does not match"):
        qwen.approve("portrait", None, "0" * 64)
    qwen.approve("portrait", None, portrait_sha)
    for number in (1, 2, 3):
        scene_calls = []
        with _client(scene_calls) as client:
            qwen.generate("scene", number, _config(), client)
        payload = json.loads(scene_calls[0].content)
        assert payload["image"] == "data:image/png;base64," + base64.b64encode(_png()).decode()
        assert payload["prompt"] == qwen._prompt("scene", number).prompt_en
        assert payload["negative_prompt"] == qwen._prompt("scene", number).negative_prompt_en
        record = json.loads((asset_area / f"scene_0{number}_start.generation.json").read_text())
        assert record["reference_sha256"] == portrait_sha
        assert "authorization" not in scene_calls[1].headers


@pytest.mark.parametrize(
    "response,image,content_type,error",
    [
        ({"data": []}, None, "image/png", "single image"),
        ({"data": [{"url": "http://example.com/a.png"}]}, None, "image/png", "untrusted"),
        (
            {
                "data": [
                    {"url": "https://dashscope-result-sz.oss-cn-shenzhen.aliyuncs.com.evil.com/x"}
                ]
            },
            None,
            "image/png",
            "untrusted",
        ),
        (None, None, "text/html", "not PNG"),
        (None, b"not a png", "image/png", "Invalid RGB PNG"),
    ],
)
def test_invalid_responses_are_rejected_without_assets(
    asset_area, response, image, content_type, error
):
    calls = []
    with _client(calls, image=image, result=response, content_type=content_type) as client:
        with pytest.raises(ValueError, match=error):
            qwen.generate("portrait", None, _config(), client)
    assert not (asset_area / "lin_yue_reference.png").exists()


def test_http_failure_has_no_retry_or_asset(asset_area):
    calls = []
    with _client(calls, status=500) as client:
        with pytest.raises(httpx.HTTPStatusError):
            qwen.generate("portrait", None, _config(), client)
    assert len(calls) == 1
    assert not (asset_area / "lin_yue_reference.png").exists()


def test_configuration_rejects_untrusted_workspace_or_region():
    with pytest.raises(ValueError, match="WORKSPACE_ID"):
        qwen.Config("beijing", "example.com/redirect", "secret").endpoint()
    with pytest.raises(ValueError, match="QWEN_IMAGE_REGION"):
        qwen.Config("other", "workspace123", "secret").endpoint()


def test_download_redirect_is_not_followed(asset_area):
    calls = []

    def handle(request):
        calls.append(request)
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"url": "https://dashscope-result-sz.oss-cn-shenzhen.aliyuncs.com/a.png"}
                    ]
                },
            )
        return httpx.Response(302, headers={"Location": "https://example.com/redirect"})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(ValueError, match="redirected"):
            qwen.generate("portrait", None, _config(), client)
    assert len(calls) == 2
    assert not (asset_area / "lin_yue_reference.png").exists()


def test_asset_approval_and_manifest_require_exact_bytes_and_prompts(asset_area, monkeypatch):
    with _client([]) as client:
        portrait_sha = qwen.generate("portrait", None, _config(), client)
    qwen.approve("portrait", None, portrait_sha)
    with pytest.raises(ValueError, match="Missing scene_01"):
        qwen.write_manifest()
    for number in (1, 2, 3):
        with _client([]) as client:
            scene_sha = qwen.generate("scene", number, _config(), client)
        qwen.approve("scene", number, scene_sha)
    experiment, vidu, wan = validation.load_package()
    stills = validation.load_still_prompts(experiment)
    monkeypatch.setattr(qwen, "load_package", lambda: (experiment, vidu, wan))
    monkeypatch.setattr(qwen, "load_still_prompts", lambda _: stills)
    monkeypatch.setattr(validation, "ROOT", asset_area.parent)
    manifest = qwen.write_manifest()
    assert set(manifest) == {
        "lin_yue_reference.png",
        "scene_01_start.png",
        "scene_02_start.png",
        "scene_03_start.png",
    }
    assert all(value == portrait_sha for value in manifest.values())  # same test fixture bytes
    assert validation.check_frames(experiment, "production")
    (asset_area / "lin_yue_reference.png").write_bytes(b"changed")
    with pytest.raises(ValueError):
        qwen.approved_portrait()


def test_dry_run_requires_no_api_key_or_network(asset_area, monkeypatch, capsys):
    monkeypatch.setenv("QWEN_IMAGE_REGION", "beijing")
    monkeypatch.setenv("QWEN_IMAGE_WORKSPACE_ID", "workspace123")
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["qwen_stills.py", "portrait"])
    qwen.main()
    preview = json.loads(capsys.readouterr().out)
    assert preview["dry_run"] is True
    assert preview["estimated_cny"] == 0.18
    assert "image" not in preview["body_preview"]
    assert not asset_area.exists()


def test_execute_gate_blocks_without_two_opt_ins(asset_area, monkeypatch, capsys):
    monkeypatch.setenv("QWEN_IMAGE_REGION", "beijing")
    monkeypatch.setenv("QWEN_IMAGE_WORKSPACE_ID", "workspace123")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-only-secret")
    monkeypatch.delenv("EXPERIMENT_001_ENABLE_PAID_CALLS", raising=False)
    monkeypatch.setattr(sys, "argv", ["qwen_stills.py", "portrait", "--execute"])
    with pytest.raises(SystemExit):
        qwen.main()
    assert "Paid call blocked" in capsys.readouterr().err
    assert not asset_area.exists()

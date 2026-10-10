"""Contract checks only: no credentials, HTTP clients, or video tasks."""

import csv
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("experiment_001_validation", ROOT / "validate.py")
validation = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = validation
spec.loader.exec_module(validation)


def test_schema_templates_and_deterministic_fixtures():
    experiment, vidu, wan = validation.load_package()
    stills = validation.load_still_prompts(experiment)
    assert experiment.target_duration_seconds == 15
    assert experiment.visual_style.aspect_ratio == "9:16"
    assert vidu.model == "viduq3-turbo" and wan.model == "wan2.7-i2v"
    digests = validation.check_frames(experiment, "fixture")
    assert len(set(digests)) == 3
    schema = (
        json.dumps(experiment.__class__.model_json_schema(), ensure_ascii=False, indent=2) + "\n"
    )
    assert (ROOT / "experiment.schema.json").read_text(encoding="utf-8") == schema
    still_schema = (
        json.dumps(stills.__class__.model_json_schema(), ensure_ascii=False, indent=2) + "\n"
    )
    assert (ROOT / "still_prompts.schema.json").read_text(encoding="utf-8") == still_schema
    fixture_spec = importlib.util.spec_from_file_location(
        "experiment_001_fixtures", ROOT / "make_fixtures.py"
    )
    fixtures = importlib.util.module_from_spec(fixture_spec)
    sys.modules[fixture_spec.name] = fixtures
    fixture_spec.loader.exec_module(fixtures)
    for scene in experiment.scenes:
        expected = fixtures.fixture_png(scene.scene_number)
        assert hashlib.sha256(expected).hexdigest() == digests[scene.scene_number - 1]


def test_both_previews_bind_identical_frames_and_prompts_without_auth():
    experiment, vidu, wan = validation.load_package()
    package = validation.preview(
        experiment, vidu, wan, validation.check_frames(experiment, "fixture"), "fixture"
    )
    assert package["offline_only"] is True
    assert package["authorization_included"] is False
    assert package["frames_are_mock"] is True
    assert len(package["requests"]) == 6
    for scene in experiment.scenes:
        pair = [
            request
            for request in package["requests"]
            if request["scene_number"] == scene.scene_number
        ]
        assert {request["provider"] for request in pair} == {"vidu", "wan"}
        assert pair[0]["source_frame"] == pair[1]["source_frame"]
        assert pair[0]["source_frame_sha256"] == pair[1]["source_frame_sha256"]
        assert pair[0]["motion_prompt_sha256"] == pair[1]["motion_prompt_sha256"]
        assert pair[0]["body_preview"]["prompt"] == scene.motion_prompt_en
        assert pair[1]["body_preview"]["input"]["prompt"] == scene.motion_prompt_en
        assert all(request["submittable"] is False for request in pair)
        assert all(
            "Authorization" not in request["headers_without_authorization"] for request in pair
        )
        assert pair[0]["body_preview"]["images"][0].startswith("data:image/png;base64,<omitted")
        assert pair[1]["body_preview"]["input"]["media"][0]["type"] == "first_frame"
        assert pair[1]["headers_without_authorization"]["X-DashScope-Async"] == "enable"
        assert pair[0]["body_preview"]["duration"] == 5
        assert pair[1]["body_preview"]["parameters"]["duration"] == 5


@pytest.mark.parametrize("change", ["duration", "identity", "fixture_path", "extra_field"])
def test_schema_rejects_broken_controls(change):
    source = json.loads((ROOT / "experiment.json").read_text(encoding="utf-8"))
    if change == "duration":
        source["scenes"][1]["duration_seconds"] = 6
    elif change == "identity":
        source["scenes"][0]["motion_prompt_en"] = "A different face. " * 10
    elif change == "fixture_path":
        source["scenes"][2]["fixture_frame"] = "../../private.png"
    else:
        source["scenes"][0]["provider_api_key"] = "never-commit"
    with pytest.raises(ValidationError):
        validation.Experiment.model_validate(source)


@pytest.mark.parametrize("change", ["bad_model", "bad_duration", "bad_rewrite"])
def test_provider_template_validation_rejects_drift(change):
    source = json.loads((ROOT / "providers/wan_2_7_i2v.json").read_text(encoding="utf-8"))
    if change == "bad_model":
        source["model"] = "wan2.6-i2v"
    elif change == "bad_duration":
        source["duration_seconds"] = 10
    else:
        source["prompt_extend"] = True
    with pytest.raises(ValidationError):
        validation.WanConfig.model_validate(source)


def test_frame_validator_rejects_corruption_and_alpha(tmp_path):
    original = (ROOT / "fixtures/scene_01_start.mock.png").read_bytes()
    damaged = tmp_path / "bad.png"
    damaged.write_bytes(original[:-5])
    with pytest.raises(ValueError):
        validation.frame_digest(damaged)
    alpha = bytearray(original)
    alpha[25] = 6
    damaged.write_bytes(alpha)
    with pytest.raises(ValueError):
        validation.frame_digest(damaged)


def test_blind_scorecard_has_eight_anonymous_rows():
    with (ROOT / "blind_scorecard.csv").open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == 8
    assert [row["anonymous_id"] for row in rows] == [
        "A-01",
        "A-02",
        "A-03",
        "B-01",
        "B-02",
        "B-03",
        "A-SET",
        "B-SET",
    ]
    assert all(None not in row for row in rows)
    assert not any(
        "vidu" in json.dumps(row).lower() or "wan" in json.dumps(row).lower() for row in rows
    )


def test_readable_script_matches_machine_source():
    experiment, _, _ = validation.load_package()
    script = (ROOT / "script.md").read_text(encoding="utf-8")
    for scene in experiment.scenes:
        assert scene.script.action_zh in script
        assert scene.script.narration_zh in script
        assert scene.script.narration_en in script
        assert scene.script.dialogue[0].line_zh in script


def test_still_prompts_lock_character_style_and_one_shared_reference():
    experiment, _, _ = validation.load_package()
    stills = validation.load_still_prompts(experiment)
    assert stills.reference_portrait.output_file == "assets/lin_yue_reference.png"
    assert [item.output_file for item in stills.scene_start_frames] == [
        f"assets/scene_0{number}_start.png" for number in range(1, 4)
    ]
    for item in stills.scene_start_frames:
        assert item.conditioning_reference_file == stills.reference_portrait.output_file
    for prompt in [stills.reference_portrait.prompt_en] + [
        item.prompt_en for item in stills.scene_start_frames
    ]:
        assert prompt.count(experiment.identity_anchor_en) == 1
        assert all(value in prompt for value in experiment.visual_style.model_dump().values())


@pytest.mark.parametrize("change", ["character_digest", "style_digest", "reference", "scene_order"])
def test_still_prompt_validation_rejects_drift(change, monkeypatch, tmp_path):
    experiment, _, _ = validation.load_package()
    source = json.loads((ROOT / "still_prompts.json").read_text(encoding="utf-8"))
    if change == "character_digest":
        source["character_bible_sha256"] = "0" * 64
    elif change == "style_digest":
        source["visual_style_sha256"] = "0" * 64
    elif change == "reference":
        source["scene_start_frames"][1]["conditioning_reference_file"] = "assets/other.png"
    else:
        source["scene_start_frames"][0]["scene_number"] = 2
    (tmp_path / "still_prompts.json").write_text(json.dumps(source), encoding="utf-8")
    monkeypatch.setattr(validation, "ROOT", tmp_path)
    with pytest.raises((ValidationError, ValueError)):
        validation.load_still_prompts(experiment)


def test_production_frames_require_all_four_real_assets(monkeypatch, tmp_path):
    experiment, _, _ = validation.load_package()
    monkeypatch.setattr(validation, "ROOT", tmp_path)
    with pytest.raises(FileNotFoundError) as error:
        validation.check_frames(experiment, "production")
    for name in (
        "scene_01_start.png",
        "scene_02_start.png",
        "scene_03_start.png",
        "lin_yue_reference.png",
    ):
        assert name in str(error.value)

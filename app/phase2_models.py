from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, field_validator, model_validator

from app.models import Scene, StoryRequest, StrictModel


class Character(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,39}$")
    name: str = Field(min_length=1, max_length=100)
    role: str = Field(min_length=1, max_length=200)
    approximate_age: str = Field(min_length=1, max_length=100)
    appearance: str = Field(min_length=1, max_length=1000)
    facial_features: str = Field(min_length=1, max_length=1000)
    hairstyle: str = Field(min_length=1, max_length=1000)
    costume: str = Field(min_length=1, max_length=1000)
    accessories: str = Field(min_length=1, max_length=1000)
    personality_visual_impression: str = Field(min_length=1, max_length=1000)


class VisualStyle(StrictModel):
    historical_era: str = Field(min_length=1, max_length=300)
    visual_style: str = Field(min_length=1, max_length=500)
    lighting: str = Field(min_length=1, max_length=500)
    cinematography: str = Field(min_length=1, max_length=500)
    color_mood: str = Field(min_length=1, max_length=500)
    aspect_ratio: Literal["9:16"] = "9:16"


class ImageAsset(StrictModel):
    asset_id: UUID
    project_id: UUID
    scene_number: int = Field(ge=1)
    url: str = Field(pattern=r"^/api/assets/[0-9a-f-]+/[0-9a-f-]+$")
    provider: Literal["mock", "openai", "alibaba"]
    model: str = Field(min_length=1, max_length=100)
    is_mock: bool
    created_at: datetime
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    width: int = Field(ge=1)
    height: int = Field(ge=1)

    @model_validator(mode="after")
    def check_reference(self):
        if self.url != f"/api/assets/{self.project_id}/{self.asset_id}":
            raise ValueError("Image URL must match its project and asset IDs")
        if self.is_mock != (self.provider == "mock"):
            raise ValueError("Mock label must match image provider")
        return self


class SceneV2(Scene):
    character_ids: list[str] = Field(min_length=1, max_length=20)
    final_image_prompt: str = Field(min_length=1, max_length=16000)
    image_asset: ImageAsset | None = None

    @field_validator("character_ids")
    @classmethod
    def distinct_character_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("Character IDs cannot be repeated in a scene")
        return value


class ProjectV2(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    project_id: UUID = Field(default_factory=uuid4)
    title: str = Field(min_length=1, max_length=200)
    request: StoryRequest
    generation_mode: Literal["llm", "demo"]
    scenes: list[SceneV2] = Field(min_length=1, max_length=18)
    character_bible: list[Character] = Field(min_length=1, max_length=30)
    visual_style: VisualStyle
    migrated_from: Literal["1.0"] | None = None

    @model_validator(mode="after")
    def check_project(self):
        if [s.scene_number for s in self.scenes] != list(range(1, len(self.scenes) + 1)):
            raise ValueError("Scene numbers must be consecutive, beginning at 1")
        if sum(s.duration for s in self.scenes) != self.request.target_duration:
            raise ValueError("Scene durations must sum to the target duration")
        ids = [character.id for character in self.character_bible]
        names = [character.name for character in self.character_bible]
        if len(ids) != len(set(ids)) or len(names) != len(set(names)):
            raise ValueError("Character IDs and names must be unique")
        by_id = {character.id: character for character in self.character_bible}
        for scene in self.scenes:
            if any(identifier not in by_id for identifier in scene.character_ids):
                raise ValueError(f"Scene {scene.scene_number} references an unknown character ID")
            expected_names = [by_id[identifier].name for identifier in scene.character_ids]
            if scene.characters != expected_names:
                raise ValueError(
                    f"Scene {scene.scene_number} names must match its Character Bible IDs in order"
                )
            if scene.image_asset and (
                scene.image_asset.project_id != self.project_id
                or scene.image_asset.scene_number != scene.scene_number
            ):
                raise ValueError(f"Scene {scene.scene_number} image asset belongs to another scene")
        return self


class ProjectDraft(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    scenes: list[Scene] = Field(min_length=1, max_length=18)
    character_bible: list[Character] = Field(min_length=1, max_length=30)
    visual_style: VisualStyle


class ImageResult(StrictModel):
    image_asset: ImageAsset

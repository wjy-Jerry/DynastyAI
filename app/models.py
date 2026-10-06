from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class StoryRequest(StrictModel):
    story_idea: str = Field(min_length=10, max_length=4000)
    genre: Literal["Palace intrigue", "Romance", "Wuxia", "Mystery", "Historical adventure"]
    target_duration: int = Field(ge=15, le=180, strict=True)
    output_language: Literal["English", "Simplified Chinese", "Traditional Chinese"]


class Dialogue(StrictModel):
    character: str = Field(min_length=1, max_length=100)
    line: str = Field(min_length=1, max_length=2000)


class Scene(StrictModel):
    scene_number: int = Field(ge=1, strict=True)
    duration: int = Field(ge=1, le=180, strict=True)
    narration: str = Field(max_length=3000)
    dialogue: list[Dialogue] = Field(max_length=30)
    visual_prompt: str = Field(min_length=1, max_length=4000)
    characters: list[str] = Field(min_length=1, max_length=20)
    camera_description: str = Field(min_length=1, max_length=2000)

    @field_validator("characters")
    @classmethod
    def valid_characters(cls, value: list[str]) -> list[str]:
        if any(not name.strip() or len(name) > 100 for name in value):
            raise ValueError("Character names must contain 1 to 100 characters")
        return [name.strip() for name in value]

    @model_validator(mode="after")
    def check_speakers(self):
        if any(line.character not in self.characters for line in self.dialogue):
            raise ValueError("Every dialogue speaker must be listed in characters")
        return self


class Storyboard(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    scenes: list[Scene] = Field(min_length=1, max_length=18)

    @model_validator(mode="after")
    def ordered_scenes(self):
        if [s.scene_number for s in self.scenes] != list(range(1, len(self.scenes) + 1)):
            raise ValueError("Scene numbers must be consecutive, beginning at 1")
        return self


class Project(Storyboard):
    schema_version: Literal["1.0"] = "1.0"
    request: StoryRequest
    generation_mode: Literal["llm", "demo"]

    @model_validator(mode="after")
    def total_duration(self):
        if sum(s.duration for s in self.scenes) != self.request.target_duration:
            raise ValueError("Scene durations must sum to the requested target duration")
        return self

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


class VisualType(str, Enum):
    TITLE = "title"
    TEXT = "text"
    DIAGRAM = "diagram"
    IMAGE = "image"
    QUOTE = "quote"
    CODE = "code"
    CHART = "chart"


class Scene(BaseModel):
    id: str = Field(min_length=1)
    section_id: str = Field(min_length=1)
    duration_sec: float = Field(gt=0, le=600)
    narration: str = ""
    visual_type: VisualType
    visual_prompt: str = ""
    screen_text: str = Field(default="", max_length=80)
    transition: str = Field(default="fade", min_length=1)
    source_refs: list[str] = Field(default_factory=list)


class Storyboard(BaseModel):
    title: str = Field(min_length=1)
    target_duration_sec: int = Field(ge=30, le=3600)
    scenes: list[Scene] = Field(min_length=1)

    @field_validator("scenes")
    @classmethod
    def scene_ids_are_unique(cls, scenes: list[Scene]) -> list[Scene]:
        identifiers = [scene.id for scene in scenes]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("storyboard scene id 必须唯一")
        return scenes

    @model_validator(mode="after")
    def duration_is_reasonable(self) -> "Storyboard":
        total = sum(scene.duration_sec for scene in self.scenes)
        tolerance = max(15.0, self.target_duration_sec * 0.2)
        if abs(total - self.target_duration_sec) > tolerance:
            raise ValueError("scene 总时长与 target_duration_sec 偏差超过 20%")
        return self

    @property
    def total_duration_sec(self) -> float:
        return sum(scene.duration_sec for scene in self.scenes)

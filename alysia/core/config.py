from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RuntimeSettings(BaseSettings):
    """从环境变量读取的最小运行设置。"""

    model_config = SettingsConfigDict(
        env_prefix="ALYSIA_",
        env_file=".env",
        extra="ignore",
    )

    config_file: Path = Path("config.yaml")


class ResourceConfig(BaseModel):
    gpu_execution: str = "serial"
    max_concurrent_gpu_models: int = Field(default=1, ge=1, le=1)


class LLMConfig(BaseModel):
    provider: Literal["mock", "ollama", "cloud"] = "mock"
    model: str = "qwen3.5:4b"
    base_url: str = "http://127.0.0.1:11434"
    timeout_sec: float = Field(default=120.0, gt=0)


class ContentConfig(BaseModel):
    language: str = "zh-CN"
    min_duration_sec: int = Field(default=120, ge=30)
    max_duration_sec: int = Field(default=300, ge=30)
    default_duration_sec: int = Field(default=180, ge=30)

    @model_validator(mode="after")
    def durations_are_ordered(self) -> "ContentConfig":
        if self.min_duration_sec > self.max_duration_sec:
            raise ValueError("min_duration_sec 不能大于 max_duration_sec")
        if not self.min_duration_sec <= self.default_duration_sec <= self.max_duration_sec:
            raise ValueError("default_duration_sec 必须位于时长范围内")
        return self


class ResearchConfig(BaseModel):
    provider: Literal["mock", "web"] = "mock"
    max_sources: int = Field(default=5, ge=1, le=20)


class PipelineRuntimeConfig(BaseModel):
    retries: int = Field(default=1, ge=0, le=5)
    runs_dir: Path = Path("runs")


class AlysiaConfig(BaseModel):
    project: dict[str, Any] = Field(default_factory=dict)
    video: dict[str, Any] = Field(default_factory=dict)
    resources: ResourceConfig = Field(default_factory=ResourceConfig)
    providers: dict[str, Any] = Field(default_factory=dict)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    content: ContentConfig = Field(default_factory=ContentConfig)
    research: ResearchConfig = Field(default_factory=ResearchConfig)
    runtime: PipelineRuntimeConfig = Field(default_factory=PipelineRuntimeConfig)


def load_config(path: Path | None = None) -> AlysiaConfig:
    """读取 YAML 配置；缺少本地配置时回退到仓库示例配置。"""
    config_path = path or RuntimeSettings().config_file
    if path is None and not config_path.exists():
        config_path = Path("config.example.yaml")
    with config_path.open("r", encoding="utf-8") as stream:
        payload = yaml.safe_load(stream) or {}
    return AlysiaConfig.model_validate(payload)

from enum import Enum


class Stage(str, Enum):
    CREATED = "created"
    RESEARCHING = "researching"
    WRITING = "writing"
    STORYBOARDING = "storyboarding"
    GENERATING_ASSETS = "generating_assets"
    GENERATING_VOICE = "generating_voice"
    GENERATING_SUBTITLES = "generating_subtitles"
    RENDERING = "rendering"
    QA = "qa"
    COMPLETED = "completed"
    FAILED = "failed"


from __future__ import annotations

from collections import Counter

from alysia.core.run import RunManager, RunState
from alysia.schemas import ContentFingerprint


def _character_count(text: str) -> int:
    return len("".join(text.split()))


class ContentFingerprintBuilder:
    def __init__(self, manager: RunManager) -> None:
        self.manager = manager

    def build(self, state: RunState) -> ContentFingerprint:
        script = self._read(state, "script")
        storyboard = self._read(state, "storyboard")
        sources = self._read(state, "research")
        subtitles = self._read_optional(state, "subtitles_json") or {"segments": []}
        package = self._read_optional(state, "publish_package") or {}
        publish_metadata = self._read_optional(state, "publish_metadata") or {}
        video_qa = self._read_optional(state, "video_qa_report") or {}
        audio_manifest = self._read_optional(state, "audio_manifest") or {}

        scenes = storyboard.get("scenes", [])
        subtitle_segments = subtitles.get("segments", [])
        narration_text = "".join(str(scene.get("narration", "")) for scene in scenes)
        narration_chars = _character_count(narration_text)
        duration_sec = float(
            video_qa.get("metrics", {}).get("duration_sec")
            or audio_manifest.get("total_duration_sec")
            or sum(float(scene.get("duration_sec", 0)) for scene in scenes)
        )
        speed = narration_chars / duration_sec if duration_sec > 0 else None
        hook_chars = _character_count(str(script.get("hook", "")))
        hook_length = hook_chars / speed if speed and hook_chars else None
        subtitle_chars = [_character_count(str(segment.get("text", ""))) for segment in subtitle_segments]

        title = str(package.get("title") or script.get("title") or state.topic)
        title_style = "unknown"
        for candidate in publish_metadata.get("title_candidates", []):
            if candidate.get("title") == title:
                title_style = str(candidate.get("style") or "unknown")
                break

        visual_distribution = Counter(str(scene.get("visual_type", "unknown")) for scene in scenes)
        cover_template = "existing_publish_cover" if package.get("cover_path") else "none"
        return ContentFingerprint(
            run_id=state.run_id,
            topic=state.topic,
            title=title,
            title_style=title_style,
            duration_sec=round(duration_sec, 6),
            hook_length_sec=round(hook_length, 6) if hook_length is not None else None,
            scene_count=len(scenes),
            subtitle_density=round(sum(subtitle_chars) / duration_sec, 6) if duration_sec > 0 else None,
            average_subtitle_chars=(round(sum(subtitle_chars) / len(subtitle_chars), 6) if subtitle_chars else None),
            narration_chars=narration_chars,
            narration_speed_chars_per_sec=round(speed, 6) if speed is not None else None,
            visual_type_distribution=dict(sorted(visual_distribution.items())),
            number_of_sources=len(sources.get("sources", [])),
            cover_template=cover_template,
            cover_text_length=_character_count(title),
            tags=[str(tag) for tag in package.get("tags", [])],
            category=str(package.get("category") or "unknown"),
        )

    def _read(self, state: RunState, key: str) -> dict:
        relative = state.artifacts.get(key)
        if not relative or not self.manager.artifact_exists(state, key):
            raise FileNotFoundError(f"生成内容指纹缺少必需产物：{key}")
        return self.manager.read_json(state.run_id, relative)

    def _read_optional(self, state: RunState, key: str) -> dict | None:
        relative = state.artifacts.get(key)
        if not relative or not self.manager.artifact_exists(state, key):
            return None
        return self.manager.read_json(state.run_id, relative)


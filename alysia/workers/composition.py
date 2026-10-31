from __future__ import annotations

import shutil
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from alysia.core.config import SubtitleConfig, VideoConfig
from alysia.core.run import RunManager, RunState
from alysia.schemas import (
    AudioManifest,
    Storyboard,
    SubtitleDocument,
    VideoComposition,
    VideoScene,
    VideoSubtitle,
)


def seconds_to_frame(value: float, fps: int) -> int:
    return int((Decimal(str(value)) * fps).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class CompositionWorker:
    def __init__(
        self,
        manager: RunManager,
        video_config: VideoConfig,
        subtitle_config: SubtitleConfig,
    ) -> None:
        self.manager = manager
        self.video_config = video_config
        self.subtitle_config = subtitle_config

    def run(
        self,
        state: RunState,
        storyboard: Storyboard,
        audio_manifest: AudioManifest,
        subtitles: SubtitleDocument,
    ) -> VideoComposition:
        run_dir = self.manager.run_dir(state.run_id)
        video_dir = run_dir / "video"
        assets_dir = video_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        total_frames = max(1, seconds_to_frame(audio_manifest.total_duration_sec, self.video_config.fps))
        video_subtitles: list[VideoSubtitle] = []
        for segment in subtitles.segments:
            start_frame = min(total_frames - 1, seconds_to_frame(segment.start_sec, self.video_config.fps))
            end_frame = min(total_frames, max(start_frame + 1, seconds_to_frame(segment.end_sec, self.video_config.fps)))
            video_subtitles.append(
                VideoSubtitle(
                    id=segment.id,
                    scene_id=segment.scene_id,
                    start_frame=start_frame,
                    end_frame=end_frame,
                    text=segment.text,
                )
            )

        storyboard_by_id = {scene.id: scene for scene in storyboard.scenes}
        generated_assets = self._generated_assets(run_dir)
        start_frames = [seconds_to_frame(scene.start_sec, self.video_config.fps) for scene in audio_manifest.scenes]
        start_frames[0] = 0
        scenes: list[VideoScene] = []
        asset_records: list[dict[str, str | bool | None]] = []
        for index, audio_scene in enumerate(audio_manifest.scenes):
            source = storyboard_by_id.get(audio_scene.scene_id)
            if source is None:
                raise ValueError(f"audio manifest scene 不存在于 storyboard：{audio_scene.scene_id}")
            start_frame = start_frames[index]
            end_frame = start_frames[index + 1] if index + 1 < len(start_frames) else total_frames
            end_frame = max(start_frame + 1, min(total_frames, end_frame))
            matching = [position for position, item in enumerate(video_subtitles) if item.scene_id == source.id]
            subtitle_range = (matching[0], matching[-1] + 1) if matching else None
            asset_path = self._stage_image(source.visual_prompt, source.id, run_dir, assets_dir)
            generated = generated_assets.get(source.id)
            video_asset_path = None
            generation_mode = None
            discard_source_audio = True
            if generated and generated.get("asset_path"):
                candidate = run_dir / generated["asset_path"]
                if candidate.is_file() and candidate.suffix.lower() in {".mp4", ".webm", ".mov"}:
                    target = assets_dir / f"{source.id}{candidate.suffix.lower()}"
                    if candidate.resolve() != target.resolve():
                        shutil.copy2(candidate, target)
                    video_asset_path = target.relative_to(run_dir).as_posix()
                    generation_mode = generated.get("generation_mode")
                    discard_source_audio = bool(generated.get("discard_source_audio", True))
                elif candidate.is_file():
                    asset_path = self._stage_image(generated["asset_path"], source.id, run_dir, assets_dir)
            placeholder = source.visual_type.value == "image" and asset_path is None
            visual = {
                "title": source.screen_text or storyboard.title,
                "body": source.visual_prompt or source.narration,
                "asset_path": asset_path,
                "placeholder": placeholder,
                "transition": source.transition,
                "video_asset_path": video_asset_path,
                "generation_mode": generation_mode,
                "discard_source_audio": discard_source_audio,
            }
            scenes.append(
                VideoScene(
                    id=source.id,
                    start_frame=start_frame,
                    duration_frames=end_frame - start_frame,
                    type=source.visual_type,
                    narration=source.narration,
                    visual=visual,
                    subtitle_range=subtitle_range,
                )
            )
            asset_records.append(
                {
                    "scene_id": source.id,
                    "source": source.visual_prompt or None,
                    "staged_path": asset_path,
                    "placeholder": placeholder,
                    "video_asset_path": video_asset_path,
                    "generation_mode": generation_mode,
                    "discard_source_audio": discard_source_audio,
                }
            )

        composition = VideoComposition(
            title=storyboard.title,
            width=self.video_config.width,
            height=self.video_config.height,
            fps=self.video_config.fps,
            duration_frames=total_frames,
            audio_file=audio_manifest.narration_file.replace("\\", "/"),
            scenes=scenes,
            subtitles=video_subtitles,
            subtitle_style={
                "font_size": self.subtitle_config.font_size,
                "position": self.subtitle_config.position,
                "max_width": self.subtitle_config.max_width,
            },
        )
        self.manager.write_json(state.run_id, "video/composition.json", composition.model_dump(mode="json"))
        self.manager.write_json(state.run_id, "video/assets_manifest.json", {"assets": asset_records})
        self.manager.write_json(
            state.run_id,
            "video/render_config.json",
            {
                "width": self.video_config.width,
                "height": self.video_config.height,
                "fps": self.video_config.fps,
                "codec": self.video_config.codec,
                "audio_codec": self.video_config.audio_codec,
                "duration_frames": total_frames,
            },
        )
        return composition

    @staticmethod
    def _generated_assets(run_dir: Path) -> dict[str, dict]:
        path = run_dir / "visual" / "assets_manifest.json"
        if not path.is_file():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {item["scene_id"]: item for item in payload.get("assets", [])}

    @staticmethod
    def _stage_image(value: str, scene_id: str, run_dir: Path, assets_dir: Path) -> str | None:
        if not value:
            return None
        source = Path(value).expanduser()
        if not source.is_absolute():
            source = run_dir / source
        if not source.is_file() or source.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            return None
        target = assets_dir / f"{scene_id}{source.suffix.lower()}"
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        return target.relative_to(run_dir).as_posix()

"""User-authored, local-only video/voice/edit jobs for CLI and Control Center."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
from typing import Any, Iterator, Literal
from uuid import uuid4
import wave

from pydantic import BaseModel, Field, model_validator

from alysia.core.config import AlysiaConfig
from alysia.core.io import atomic_write_json
from alysia.core.resources import ResourceManager
from alysia.core.run import RunManager
from alysia.providers.tts.sapi import SapiTTSProvider
from alysia.providers.visual.comfyui import ComfyUIProvider
from alysia.providers.video.remotion import RemotionRenderer
from alysia.schemas.audio import TTSRequest
from alysia.schemas.storyboard import VisualType
from alysia.schemas.video import VideoComposition, VideoScene, VideoSubtitle
from alysia.schemas.visual import H3VisualPrompt, SceneVisualPlan
from alysia.visual.dynamic_wallpaper import DynamicWallpaperWorkflow
from alysia.visual.jobs import build_visual_job
from alysia.workers.media import require_media_executable
from alysia.workers.video import VideoRenderWorker
from alysia.workers.video_qa import VideoQAWorker
from alysia.workers.wav import concatenate_wavs, inspect_wav


RUN_ID = re.compile(r"^local_[0-9]{8}_[0-9]{6}_[0-9a-f]{8}$")
SCENE_ID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


class LocalCreationBusy(RuntimeError):
    """Another local creation is active; leave its state untouched."""


class LocalScene(BaseModel):
    scene_id: str
    backend: Literal["h3_staged_i2v", "comfyui_api"]
    prompt: str = Field(min_length=1, max_length=12000)
    narration: str = Field(min_length=1, max_length=180)
    reference_image: Path | None = None
    workflow: dict[str, Any] | None = None
    requested_duration_sec: float = Field(default=3.0, gt=0, le=8)

    @model_validator(mode="after")
    def validate_backend(self) -> "LocalScene":
        if not SCENE_ID.fullmatch(self.scene_id):
            raise ValueError("scene_id 只能使用字母、数字、下划线和连字符")
        if self.backend == "h3_staged_i2v":
            if self.reference_image is None or not self.reference_image.is_file():
                raise ValueError("h3_staged_i2v 需要存在的 reference_image")
            if self.workflow is not None:
                raise ValueError("staged H3 使用固定的已验证工作流，不接受替换节点图")
        else:
            if self.reference_image is not None:
                raise ValueError("comfyui_api 的图片输入须由 API 工作流自身声明")
            metadata = (self.workflow or {}).get("_alysia", {})
            graph = (self.workflow or {}).get("prompt")
            if metadata.get("api_format") is not True or not isinstance(graph, dict) or not graph:
                raise ValueError("comfyui_api 需要带 _alysia.api_format=true 的 API 节点图")
            peak = metadata.get("measured_peak_vram_mb")
            if type(peak) is not int or not 0 < peak <= 6144:
                raise ValueError("自定义 ComfyUI 工作流需填写实测显存峰值，且不超过 6144 MiB")
            if not any(node.get("class_type") == "SaveVideo" for node in graph.values() if isinstance(node, dict)):
                raise ValueError("comfyui_api 工作流必须包含 SaveVideo 节点")
            binding = metadata.get("bindings", {}).get("prompt") if isinstance(metadata.get("bindings"), dict) else None
            parts = binding.split(".") if isinstance(binding, str) else []
            if (len(parts) != 3 or parts[1] != "inputs"
                    or not isinstance(graph.get(parts[0]), dict)
                    or not isinstance(graph[parts[0]].get("inputs"), dict)
                    or not isinstance(graph[parts[0]]["inputs"].get(parts[2]), str)):
                raise ValueError("comfyui_api 必须将用户 prompt 绑定到现有的文本输入节点")
        return self


class LocalCreationSpec(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    scenes: list[LocalScene] = Field(min_length=1, max_length=5)
    width: int = Field(default=1280, ge=320, le=1920, multiple_of=2)
    height: int = Field(default=720, ge=240, le=1080, multiple_of=2)
    fps: int = Field(default=24, ge=12, le=30)

    @model_validator(mode="after")
    def unique_scenes(self) -> "LocalCreationSpec":
        ids = [scene.scene_id for scene in self.scenes]
        if len(ids) != len(set(ids)):
            raise ValueError("scene_id 必须唯一")
        return self


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@contextmanager
def _single_job_lock(path: Path) -> Iterator[None]:
    """Cross-process lock for local creator jobs; no other process is killed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt

            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise LocalCreationBusy("另一个本地创作任务正在使用 GPU/剪辑资源") from exc
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise LocalCreationBusy("另一个本地创作任务正在使用 GPU/剪辑资源") from exc
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class LocalCreatorService:
    def __init__(self, config: AlysiaConfig, *, root: Path | None = None) -> None:
        self.config = config
        self.root = (root or config.runtime.runs_dir.parent / "workspace" / "local_creator").resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._threads: dict[str, threading.Thread] = {}

    def submit(self, payload: LocalCreationSpec | dict[str, Any]) -> dict[str, Any]:
        spec = payload if isinstance(payload, LocalCreationSpec) else LocalCreationSpec.model_validate(payload)
        now = datetime.now().astimezone()
        run_id = f"local_{now:%Y%m%d_%H%M%S}_{uuid4().hex[:8]}"
        run_dir = self._dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=False)
        atomic_write_json(run_dir / "spec.json", spec.model_dump(mode="json"))
        state = {"run_id": run_id, "title": spec.title, "status": "PENDING", "phase": "queued",
                 "created_at": now.isoformat(), "updated_at": now.isoformat(), "clips": {},
                 "voice": {}, "final_video": None, "qa": None, "error": None}
        self._save(state)
        return self.status(run_id)

    def list(self) -> list[dict[str, Any]]:
        return [self.status(path.name) for path in sorted(self.root.glob("local_*"), reverse=True)
                if path.is_dir() and RUN_ID.fullmatch(path.name) and (path / "state.json").is_file()]

    def status(self, run_id: str) -> dict[str, Any]:
        return json.loads((self._dir(run_id) / "state.json").read_text(encoding="utf-8"))

    def start_background(self, run_id: str) -> dict[str, Any]:
        state = self.status(run_id)
        if state["status"] == "COMPLETE":
            return state
        thread = self._threads.get(run_id)
        if thread is not None and thread.is_alive():
            return state
        worker = threading.Thread(target=self.run, args=(run_id,), daemon=True, name=f"alysia-{run_id}")
        self._threads[run_id] = worker
        worker.start()
        return self.status(run_id)

    def run(self, run_id: str) -> dict[str, Any]:
        state = self.status(run_id)
        completed = state.get("final_video") or {}
        if (state["status"] == "COMPLETE" and self.final_video(run_id).is_file()
                and completed.get("sha256") == _hash_file(self.final_video(run_id))):
            return state
        spec = LocalCreationSpec.model_validate_json((self._dir(run_id) / "spec.json").read_text(encoding="utf-8"))
        try:
            with _single_job_lock(self.root / ".active_job.lock"):
                self._update(state, status="RUNNING", phase="visual", error=None)
                for scene in spec.scenes:
                    self._clip(run_id, scene, state)
                self._update(state, phase="voice")
                for scene in spec.scenes:
                    self._voice(run_id, scene, state)
                self._update(state, phase="edit")
                expected = self._edit(run_id, spec, state)
                self._update(state, phase="qa")
                qa_config = self.config.model_copy(deep=True)
                qa_config.video.width, qa_config.video.height, qa_config.video.fps = spec.width, spec.height, spec.fps
                report = VideoQAWorker(qa_config).run(self.final_video(run_id), expected)
                state["qa"] = report.model_dump(mode="json")
                if not report.passed:
                    raise RuntimeError(f"成片 QA 未通过：{report.errors}")
                state["final_video"] = {"path": str(self.final_video(run_id)),
                                        "bytes": self.final_video(run_id).stat().st_size,
                                        "sha256": _hash_file(self.final_video(run_id))}
                self._update(state, status="COMPLETE", phase="review_ready")
        except LocalCreationBusy:
            return self.status(run_id)
        except Exception as exc:
            self._update(state, status="FAILED", error=f"{type(exc).__name__}: {exc}")
        return self.status(run_id)

    def final_video(self, run_id: str) -> Path:
        return self._dir(run_id) / "output" / "final.mp4"

    def _clip(self, run_id: str, scene: LocalScene, state: dict[str, Any]) -> None:
        run_dir = self._dir(run_id)
        target = run_dir / "clips" / f"{scene.scene_id}.mp4"
        previous = state["clips"].get(scene.scene_id)
        if previous and target.is_file() and _hash_file(target) == previous["sha256"]:
            return
        self._update(state, phase=f"visual:{scene.scene_id}")
        if scene.backend == "h3_staged_i2v":
            workflow = DynamicWallpaperWorkflow(self.config)
            resume_dir = self._matching_h3_run(run_dir / "h3" / scene.scene_id, scene)
            summary = (workflow.resume(resume_dir) if resume_dir else workflow.run(
                scene.reference_image, scene.prompt, output_dir=run_dir / "h3" / scene.scene_id,
            ))
            source = Path(summary["artifact"])
            provenance = {"backend": scene.backend, "summary": str(Path(summary["run_dir"]) / "summary.json")}
        else:
            workflow_dir = run_dir / "workflows"
            workflow_dir.mkdir(parents=True, exist_ok=True)
            atomic_write_json(workflow_dir / f"{scene.scene_id}.json", scene.workflow)
            h3 = self.config.visual_generation.h3
            provider = ComfyUIProvider(
                base_url=h3.comfyui_base_url, workflow_dir=workflow_dir,
                output_dir=h3.comfyui_dir / "output" if h3.comfyui_dir else Path("workspace/comfyui_output"),
                timeout_sec=h3.api_timeout_sec, job_timeout_sec=h3.job_timeout_sec,
                runtime_vram_stop_mib=7680, runtime_ram_stop_mib=min(self.config.hardware_profile.ram_gb, 24) * 1024,
            )
            visual = SceneVisualPlan(
                scene_id=scene.scene_id, generation_mode="h3_t2v",
                requested_duration_sec=scene.requested_duration_sec,
                prompt=H3VisualPrompt(subject=scene.prompt, camera=""),
                budgeted_h3_seconds=scene.requested_duration_sec,
            )
            job = build_visual_job(run_id, visual, provider.provider_id, scene.scene_id)
            with ResourceManager(sequential_gpu=True).phase(f"local_creator:{scene.scene_id}", provider=provider, gpu_heavy=True):
                result = provider.generate(job)
            videos = [path for path in result.output_files if path.suffix.lower() in {".mp4", ".webm", ".mov"}]
            if not videos:
                raise ValueError("ComfyUI 工作流完成但没有输出视频")
            source = videos[0]
            provenance = {"backend": scene.backend, "workflow_sha256": _hash_file(workflow_dir / f"{scene.scene_id}.json"),
                          "provider_job_id": job.job_id, "source": str(source),
                          "sampled_peak_vram_mib": result.seed_config.get("sampled_peak_vram_mib"),
                          "sampled_peak_system_ram_mib": result.seed_config.get("sampled_peak_system_ram_mib")}
        self._video_duration(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        state["clips"][scene.scene_id] = {"path": str(target), "sha256": _hash_file(target),
                                           "duration_sec": self._video_duration(target), **provenance}
        self._save(state)

    @staticmethod
    def _matching_h3_run(root: Path, scene: LocalScene) -> Path | None:
        if not root.is_dir() or scene.reference_image is None:
            return None
        prompt_hash = hashlib.sha256(scene.prompt.encode("utf-8")).hexdigest()
        image_hash = _hash_file(scene.reference_image)
        for candidate in sorted(root.glob("wallpaper_*"), reverse=True):
            try:
                job = json.loads((candidate / "job.json").read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if (job.get("workflow_id") == "dynamic_wallpaper"
                    and job.get("prompt_sha256") == prompt_hash
                    and job.get("source_image_sha256") == image_hash):
                return candidate
        return None

    def _voice(self, run_id: str, scene: LocalScene, state: dict[str, Any]) -> None:
        target = self._dir(run_id) / "audio" / "scenes" / f"{scene.scene_id}.wav"
        previous = state["voice"].get(scene.scene_id)
        if previous and target.is_file() and _hash_file(target) == previous["sha256"]:
            return
        if self.config.tts.provider != "sapi":
            raise ValueError("本地创作闭环要求真实 SAPI 配音；不使用 mock TTS")
        target.parent.mkdir(parents=True, exist_ok=True)
        result = asyncio.run(SapiTTSProvider().synthesize(TTSRequest(
            text=scene.narration, scene_id=scene.scene_id,
            language=self.config.tts.language, voice=self.config.tts.voice,
            speed=self.config.tts.speed, sample_rate=self.config.tts.sample_rate,
            output_path=target,
        )))
        state["voice"][scene.scene_id] = {"path": str(target), "sha256": _hash_file(target),
                                           "duration_sec": result.duration_sec, "provider": result.provider}
        self._save(state)

    def _edit(self, run_id: str, spec: LocalCreationSpec, state: dict[str, Any]) -> float:
        run_dir = self._dir(run_id)
        ffmpeg = require_media_executable("ffmpeg", self.config.render.ffmpeg_path)
        npm = shutil.which("npm")
        remotion_dir = self.config.render.remotion_dir.resolve()
        if not npm or not (remotion_dir / "node_modules" / "remotion").is_dir():
            raise FileNotFoundError("Remotion 尚未安装，无法完成本地剪辑")
        scenes: list[VideoScene] = []
        subtitles: list[VideoSubtitle] = []
        audio_paths: list[Path] = []
        cursor = 0
        for index, scene in enumerate(spec.scenes, 1):
            clip = run_dir / "clips" / f"{scene.scene_id}.mp4"
            voice = run_dir / "audio" / "scenes" / f"{scene.scene_id}.wav"
            voice_sec = float(inspect_wav(voice)["duration_sec"])
            frames = math.ceil(max(self._video_duration(clip), voice_sec + .2) * spec.fps)
            duration = frames / spec.fps
            staged = run_dir / "video" / "assets" / f"{scene.scene_id}.mp4"
            staged.parent.mkdir(parents=True, exist_ok=True)
            source_sec = self._video_duration(clip)
            filter_graph = (
                f"fps={spec.fps},scale={spec.width}:{spec.height}:force_original_aspect_ratio=decrease,"
                f"pad={spec.width}:{spec.height}:(ow-iw)/2:(oh-ih)/2,"
                f"tpad=stop_mode=clone:stop_duration={max(0., duration-source_sec)+.1:.3f},"
                f"trim=duration={duration:.6f},setpts=PTS-STARTPTS"
            )
            subprocess.run([str(ffmpeg), "-nostdin", "-y", "-v", "error", "-i", str(clip),
                            "-vf", filter_graph, "-frames:v", str(frames), "-an", "-c:v", "libx264",
                            "-crf", "20", "-pix_fmt", "yuv420p", str(staged)], check=True, timeout=600)
            padded = run_dir / "audio" / "padded" / f"{scene.scene_id}.wav"
            self._pad_wav(voice, padded, duration)
            audio_paths.append(padded)
            scenes.append(VideoScene(
                id=scene.scene_id, start_frame=cursor, duration_frames=frames,
                type=VisualType.IMAGE, narration=scene.narration,
                visual={"video_asset_path": staged.relative_to(run_dir).as_posix(),
                        "discard_source_audio": True, "title": spec.title},
                subtitle_range=(index-1, index),
            ))
            subtitles.append(VideoSubtitle(id=index, scene_id=scene.scene_id,
                                           start_frame=cursor, end_frame=cursor+frames,
                                           text=scene.narration))
            cursor += frames
        narration = run_dir / "audio" / "narration.wav"
        concatenate_wavs(audio_paths, narration, pause_between_scenes_ms=0)
        composition = VideoComposition(
            title=spec.title, width=spec.width, height=spec.height, fps=spec.fps,
            duration_frames=cursor, audio_file="audio/narration.wav",
            scenes=scenes, subtitles=subtitles,
            subtitle_style={"font_size": min(54, spec.height // 15), "position": "bottom", "max_width": .82},
        )
        props = run_dir / "video" / "composition.json"
        atomic_write_json(props, composition.model_dump(mode="json"))
        raw = run_dir / "video" / "rendered.mp4"
        subprocess.run([npm, "run", "render", "--", "--props", str(props), "--output", str(raw),
                        "--public-dir", str(run_dir)], cwd=remotion_dir, check=True, timeout=1800)
        target = self.final_video(run_id)
        config = self.config.model_copy(deep=True)
        config.video.width, config.video.height, config.video.fps = spec.width, spec.height, spec.fps
        VideoRenderWorker(
            RunManager(config.runtime.runs_dir), config,
            RemotionRenderer(config.video, config.render),
        )._normalize(raw, target, cursor/spec.fps)
        state["composition"] = str(props)
        state["narration"] = str(narration)
        self._save(state)
        return cursor/spec.fps

    @staticmethod
    def _pad_wav(source: Path, target: Path, duration_sec: float) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(source), "rb") as raw, wave.open(str(target), "wb") as output:
            if raw.getnchannels() != 1 or raw.getsampwidth() != 2:
                raise ValueError("SAPI 音频必须是 mono PCM16")
            output.setparams(raw.getparams())
            current = raw.getnframes()
            required = round(duration_sec * raw.getframerate())
            output.writeframes(raw.readframes(current))
            output.writeframes(b"\0" * max(0, required-current) * 2)

    @staticmethod
    def _video_duration(path: Path) -> float:
        ffprobe = require_media_executable("ffprobe")
        result = subprocess.run([str(ffprobe), "-v", "error", "-show_entries",
                                 "stream=codec_type:format=duration", "-of", "json", str(path)],
                                capture_output=True, text=True, check=True, timeout=60)
        data = json.loads(result.stdout)
        if not any(stream.get("codec_type") == "video" for stream in data.get("streams", [])):
            raise ValueError(f"视频产物没有 video stream：{path}")
        duration = float(data["format"]["duration"])
        if duration <= 0:
            raise ValueError(f"视频产物时长无效：{path}")
        return duration

    def _dir(self, run_id: str) -> Path:
        if not RUN_ID.fullmatch(run_id):
            raise ValueError("本地创作任务 ID 无效")
        return self.root / run_id

    def _update(self, state: dict[str, Any], **changes: Any) -> None:
        state.update(changes)
        self._save(state)

    def _save(self, state: dict[str, Any]) -> None:
        state["updated_at"] = datetime.now().astimezone().isoformat()
        atomic_write_json(self._dir(state["run_id"]) / "state.json", state, backup_count=2)

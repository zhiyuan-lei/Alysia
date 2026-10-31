from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from alysia.core.config import AlysiaConfig
from alysia.core.resources import ResourceManager
from alysia.core.run import RunManager
from alysia.core.state import Stage
from alysia.identity import IdentityService
from alysia.production import ProductionService
from alysia.reliability import ReliabilityService
from alysia.core.io import atomic_write_json
from alysia.providers.visual import (
    MiniMaxH3LocalProvider,
    MockVisualGenerationProvider,
    VisualProviderRegistry,
)
from alysia.schemas import Storyboard
from alysia.schemas.visual import (
    H3VisualPrompt,
    SceneVisualPlan,
    VisualAsset,
    VisualAssetsManifest,
    VisualGenerationResult,
    VisualPlan,
)
from alysia.visual.planner import VisualPlanner
from alysia.visual.dynamic_wallpaper import DynamicWallpaperWorkflow
from alysia.visual.qa import VisualQA
from alysia.visual.queue import VisualJobQueue
from alysia.visual.upscale import FFmpegScaleUpscaler, NoOpUpscaler
from alysia.security import SecurityService


class VisualGenerationService:
    def __init__(
        self,
        config: AlysiaConfig,
        *,
        resources: ResourceManager | None = None,
        registry: VisualProviderRegistry | None = None,
    ) -> None:
        self.config = config
        self.manager = RunManager(config.runtime.runs_dir)
        self.resources = resources or ResourceManager(sequential_gpu=config.runtime.sequential_gpu)
        self.reliability = ReliabilityService(config, manager=self.manager, resources=self.resources)
        self.queue = VisualJobQueue(config.visual_generation.queue_dir, self.resources)
        self.planner = VisualPlanner(config)
        self.qa = VisualQA()
        self.security = SecurityService(config)
        self.registry = registry or self._default_registry()

    def dynamic_wallpaper(
        self, image_path: Path, prompt: str, *, output_dir: Path | None = None,
    ) -> dict[str, Any]:
        """运行独立的单图 H3 动态壁纸工作流，不进入发布队列。"""
        return DynamicWallpaperWorkflow(self.config, resources=self.resources).run(
            image_path, prompt, output_dir=output_dir,
        )

    def resume_dynamic_wallpaper(self, run_dir: Path) -> dict[str, Any]:
        return DynamicWallpaperWorkflow(self.config, resources=self.resources).resume(run_dir)

    def _default_registry(self) -> VisualProviderRegistry:
        h3_output = (
            self.config.visual_generation.h3.comfyui_dir / "output"
            if self.config.visual_generation.h3.comfyui_dir else Path("workspace/comfyui_output")
        )
        return VisualProviderRegistry([
            MockVisualGenerationProvider(self.config.runtime.runs_dir),
            MiniMaxH3LocalProvider(
                self.config.visual_generation.h3, output_dir=h3_output,
                security=self.security,
            ),
        ])

    def doctor(self) -> dict[str, Any]:
        h3 = self.config.visual_generation.h3
        vram = self.resources.probe_vram()
        providers = [item.health_check().model_dump(mode="json") for item in self.registry.list()]
        return {
            "enabled": self.config.visual_generation.enabled,
            "low_vram": h3.low_vram,
            "sequential_gpu_required": h3.sequential_gpu_required,
            "comfyui_dir": str(h3.comfyui_dir) if h3.comfyui_dir else None,
            "model_path": str(h3.model_path) if h3.model_path else None,
            "configured_hardware_profile": self.config.hardware_profile.model_dump(mode="json"),
            "vram": vram,
            "ram": self.resources.probe_ram(),
            "providers": providers,
        }

    def h3_setup_status(self) -> dict[str, Any]:
        h3 = self.config.visual_generation.h3
        provider = self.registry.get("visual.comfyui-h3")
        health = provider.health_check()
        manifest_path = (
            h3.comfyui_dir / "alysia_h3_model_manifest.json"
            if h3.comfyui_dir is not None else None
        )
        manifest = None
        if manifest_path is not None and manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        required_models = getattr(provider, "required_model_paths", lambda: [])()
        return {
            "ready": health.available,
            "provider": health.model_dump(mode="json"),
            "comfyui_dir": str(h3.comfyui_dir) if h3.comfyui_dir else None,
            "workflow_dir": str(h3.workflow_dir.resolve()),
            "required_models": [
                {
                    "path": str(path),
                    "exists": path.is_file(),
                    "size": path.stat().st_size if path.is_file() else None,
                }
                for path in required_models
            ],
            "download_manifest": manifest,
            "configured_hardware_profile": self.config.hardware_profile.model_dump(mode="json"),
            "detected_vram": self.resources.probe_vram(),
            "detected_ram": self.resources.probe_ram(),
        }

    def h3_smoke_test(self) -> dict[str, Any]:
        provider = self.registry.get("visual.comfyui-h3")
        health = provider.health_check()
        if not health.available:
            raise RuntimeError(f"H3 provider 未就绪：{health.details}")
        h3 = self.config.visual_generation.h3
        run_id = f"h3_smoke_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        scene = SceneVisualPlan(
            scene_id="smoke-t2v",
            generation_mode="h3_t2v",
            requested_duration_sec=3.0,
            prompt=H3VisualPrompt(
                subject="A small silver robot walking through a quiet neon-lit workshop",
                environment="cinematic realistic workshop, no text or logos",
                action_motion="slow natural walk with subtle moving lights",
                camera="smooth side tracking shot",
                lighting_style="soft blue and amber practical lighting",
                negative_constraints=["no subtitles", "no watermark", "no embedded captions"],
            ),
            route_reasons=["explicit local H3 smoke test"],
            budgeted_h3_seconds=3.0,
        )
        job = provider.prepare_job(run_id, scene)
        self.queue.enqueue(job)
        result = self.queue.run(job.job_id, provider)
        qa = self.qa.run(run_id, result, expected_duration_sec=scene.requested_duration_sec)
        report = {
            "run_id": run_id,
            "result": result.model_dump(mode="json"),
            "qa": qa.model_dump(mode="json"),
            "configured_hardware_profile": self.config.hardware_profile.model_dump(mode="json"),
        }
        output = self.config.visual_generation.queue_dir.parent / "h3_smoke_result.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        return report

    def plan(self, run_id: str, *, force: bool = False) -> VisualPlan:
        state = self.manager.load(run_id)
        path = self.manager.run_dir(run_id) / "visual" / "visual_plan.json"
        if path.is_file() and not force:
            return VisualPlan.model_validate_json(path.read_text(encoding="utf-8"))
        storyboard_path = state.artifacts.get("storyboard", "storyboard.json")
        storyboard = Storyboard.model_validate(self.manager.read_json(run_id, storyboard_path))
        try:
            production = ProductionService(self.config).load_plan(run_id)
        except FileNotFoundError:
            production = None
        identity = IdentityService(self.config).ensure().visual_identity
        plan = self.planner.plan(run_id, storyboard, production, identity)
        self.manager.write_json(run_id, "visual/visual_plan.json", plan.model_dump(mode="json"))
        for scene in plan.scenes:
            if scene.prompt is not None:
                self.manager.write_json(
                    run_id, f"visual/prompts/{scene.scene_id}.json", scene.prompt.model_dump(mode="json")
                )
        state.artifacts["visual_plan"] = "visual/visual_plan.json"
        self.manager.save(state)
        return plan

    def generate(self, run_id: str, *, provider: str | None = None, force: bool = False) -> VisualAssetsManifest:
        state = self.manager.load(run_id)
        manifest_path = self.manager.run_dir(run_id) / "visual" / "assets_manifest.json"
        if manifest_path.is_file() and not force:
            manifest = VisualAssetsManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
            if all(
                asset.asset_path is None
                or self.reliability.integrity.check(
                    self.manager.run_dir(run_id) / asset.asset_path, producer=asset.provider,
                ).validity == "valid"
                for asset in manifest.assets
            ):
                return manifest
        plan = self.plan(run_id, force=force)
        state.start_stage(Stage.GENERATING_ASSETS)
        self.manager.save(state)
        self.reliability.checkpoint(state, "started")
        provider_id = self._provider_id(provider or self.config.visual_generation.provider)
        visual_provider = self.registry.get(provider_id)
        assets: list[VisualAsset] = []
        warnings: list[str] = []
        for scene in plan.scenes:
            if not scene.generation_mode.startswith("h3_"):
                assets.append(
                    VisualAsset(scene_id=scene.scene_id, generation_mode=scene.generation_mode,
                                provider="remotion" if scene.generation_mode == "remotion" else "static")
                )
                continue
            if self.config.visual_generation.h3.unload_other_gpu_models:
                unloaded = self.resources.unload_gpu_providers(except_name=provider_id)
                if unloaded:
                    warnings.append(f"{scene.scene_id}: H3 前卸载 GPU providers={unloaded}")
            job = visual_provider.prepare_job(run_id, scene)
            try:
                result, recovery_warnings = self._generate_with_recovery(
                    run_id, state, scene, job, visual_provider
                )
            except Exception as exc:
                self.reliability.checkpoint(state, "failed")
                state.fail_stage(Stage.GENERATING_ASSETS, exc)
                self.manager.save(state)
                raise
            warnings.extend(recovery_warnings)
            if result is None:
                assets.append(
                    VisualAsset(
                        scene_id=scene.scene_id,
                        generation_mode="remotion",
                        provider="approved_fallback:remotion",
                        review_eligible=True,
                    )
                )
                continue
            result = self._postprocess(run_id, result)
            result_path = f"visual/results/{scene.scene_id}.json"
            self.manager.write_json(run_id, result_path, result.model_dump(mode="json"))
            qa = self.qa.run(run_id, result, expected_duration_sec=scene.requested_duration_sec)
            qa_path = f"visual/qa/{scene.scene_id}.json"
            self.manager.write_json(run_id, qa_path, qa.model_dump(mode="json"))
            if not qa.passed:
                raise RuntimeError(f"Visual QA FAIL scene={scene.scene_id}: {qa.errors}")
            output = result.output_files[0].resolve()
            relative = output.relative_to(self.manager.run_dir(run_id)).as_posix()
            assets.append(
                VisualAsset(
                    scene_id=scene.scene_id, generation_mode=scene.generation_mode,
                    asset_path=relative, provider=result.provider, provenance_path=result_path,
                    discard_source_audio=not self.config.visual_generation.preserve_h3_audio_as_ambience,
                    optional_ambience=self.config.visual_generation.preserve_h3_audio_as_ambience,
                    mock=result.mock, review_eligible=qa.production_eligible,
                )
            )
        eligible = all(asset.review_eligible for asset in assets)
        if not eligible:
            warnings.append("包含 mock visual artifact；禁止提升到 production review。")
        manifest = VisualAssetsManifest(
            run_id=run_id, assets=assets, production_review_eligible=eligible, warnings=warnings,
        )
        self.manager.write_json(run_id, "visual/assets_manifest.json", manifest.model_dump(mode="json"))
        state.artifacts["visual_assets_manifest"] = "visual/assets_manifest.json"
        state.complete_stage(Stage.GENERATING_ASSETS)
        self.manager.save(state)
        self.reliability.checkpoint(state, "succeeded")
        return manifest

    def _generate_with_recovery(self, run_id, state, scene, job, provider):
        warnings: list[str] = []
        health = provider.health_check()
        guard = self.reliability.guard.check(
            self.manager.run_dir(run_id), gpu_heavy=True, comfyui_health=health, estimated_output_mb=512,
        )
        atomic_write_json(
            self.reliability.root(run_id) / "resource_guards" / f"{job.job_id}.json",
            guard.model_dump(mode="json"), backup_count=2,
        )
        if guard.status == "blocked":
            error = RuntimeError("H3 ResourceGuard BLOCKED: " + "; ".join(guard.reasons))
            fallbacks = ["render.remotion"] if self.config.production.allow_fallback else []
            failure, decision = self.reliability.record_exception(
                error, state=state, stage="h3", provider=provider.provider_id,
                retry_count=job.attempts, fallback_refs=fallbacks,
            )
            if decision.action == "use_approved_fallback":
                failure.status = "recovered"
                failure.quality_impact = decision.quality_impact
                self.reliability.failures(run_id).save(failure)
                warnings.append(f"{scene.scene_id}: H3 blocked → Remotion；{decision.quality_impact}")
                return None, warnings
            raise error
        self.queue.enqueue(job)
        try:
            return self.queue.run(job.job_id, provider), warnings
        except Exception as first_error:
            fallbacks = ["h3.low_resource", "render.remotion"] if self.config.production.allow_fallback else []
            first_failure, decision = self.reliability.record_exception(
                first_error, state=state, stage="h3", provider=provider.provider_id,
                retry_count=job.attempts, fallback_refs=fallbacks,
            )
            if decision.action != "use_approved_fallback":
                raise
            self.resources.unload_gpu_providers()
            low_provider = self._low_resource_provider(provider)
            if low_provider is not None:
                low_scene = scene.model_copy(
                    deep=True,
                    update={"requested_duration_sec": min(scene.requested_duration_sec, 3.0)},
                )
                low_job = low_provider.prepare_job(run_id, low_scene)
                self.queue.enqueue(low_job)
                try:
                    result = self.queue.run(low_job.job_id, low_provider)
                    first_failure.status = "recovered"
                    first_failure.quality_impact = "H3 降为更低分辨率/更短镜头；动态信息量可能下降"
                    self.reliability.failures(run_id).save(first_failure)
                    warnings.append(f"{scene.scene_id}: H3 OOM/error 后使用 approved low-resource profile")
                    return result, warnings
                except Exception as second_error:
                    second_failure, second_decision = self.reliability.record_exception(
                        second_error, state=state, stage="h3_low_resource", provider=provider.provider_id,
                        retry_count=1, fallback_refs=["render.remotion"] if self.config.production.allow_fallback else [],
                    )
                    if second_decision.action == "use_approved_fallback":
                        second_failure.status = "recovered"
                        second_failure.quality_impact = second_decision.quality_impact
                        self.reliability.failures(run_id).save(second_failure)
                        warnings.append(
                            f"{scene.scene_id}: H3 low-resource 仍失败 → Remotion；{second_decision.quality_impact}"
                        )
                        return None, warnings
                    raise
            if self.config.production.allow_fallback:
                first_failure.status = "recovered"
                first_failure.quality_impact = "H3 动态镜头回退为 Remotion 程序化画面"
                self.reliability.failures(run_id).save(first_failure)
                warnings.append(f"{scene.scene_id}: H3 失败 → Remotion 程序化画面")
                return None, warnings
            raise

    def _low_resource_provider(self, provider):
        if not isinstance(provider, MiniMaxH3LocalProvider):
            return None
        profile = provider.config.model_copy(deep=True)
        profile.preview_width = min(profile.preview_width, 480)
        profile.preview_width -= profile.preview_width % 32
        profile.preview_height = min(profile.preview_height, 288)
        profile.preview_height -= profile.preview_height % 32
        profile.preview_steps = min(profile.preview_steps, 4)
        output_dir = provider.output_dir
        return MiniMaxH3LocalProvider(profile, output_dir=output_dir)

    def status(self, run_id: str) -> dict[str, Any]:
        jobs = self.queue.list(run_id)
        manifest_path = self.manager.run_dir(run_id) / "visual" / "assets_manifest.json"
        return {
            "run_id": run_id,
            "plan_exists": (self.manager.run_dir(run_id) / "visual" / "visual_plan.json").is_file(),
            "manifest_exists": manifest_path.is_file(),
            "jobs": [job.model_dump(mode="json") for job in jobs],
            "production_review_eligible": (
                VisualAssetsManifest.model_validate_json(manifest_path.read_text(encoding="utf-8")).production_review_eligible
                if manifest_path.is_file() else None
            ),
        }

    @staticmethod
    def _provider_id(value: str) -> str:
        return {"mock": "visual.mock", "comfyui-h3": "visual.comfyui-h3"}.get(value, value)

    def _postprocess(self, run_id: str, result: VisualGenerationResult) -> VisualGenerationResult:
        source = result.output_files[0]
        if source.suffix.lower() != ".mp4":
            return result
        destination = self.manager.run_dir(run_id) / "visual" / "postprocessed" / f"{result.scene_id}.mp4"
        upscaler = FFmpegScaleUpscaler() if self.config.visual_generation.upscale == "ffmpeg" else NoOpUpscaler()
        if source.resolve() != destination.resolve():
            upscaler.upscale(source, destination, width=self.config.video.width, height=self.config.video.height)
        result.output_files = [destination]
        result.resolution = f"{self.config.video.width}x{self.config.video.height}"
        result.warnings.append("源音轨未交给主旁白链路；Editor 默认丢弃 H3 原生音频。")
        return result

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from alysia.capabilities.store import atomic_json, load_models
from alysia.schemas import Capability


class CapabilityRegistry:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.directory = self.root / "registry"
        self.directory.mkdir(parents=True, exist_ok=True)

    def bootstrap(self) -> list[Capability]:
        existing = {item.capability_id: item for item in self.list()}
        for capability in initial_capabilities():
            current = existing.get(capability.capability_id)
            if current is None:
                self.register(capability)
            elif not current.accepted_inputs and not current.produced_outputs:
                self.upsert(current.model_copy(update={
                    "tags": capability.tags,
                    "accepted_inputs": capability.accepted_inputs,
                    "produced_outputs": capability.produced_outputs,
                    "resource_requirements": capability.resource_requirements,
                    "policy_restrictions": capability.policy_restrictions,
                    "execution_layer": capability.execution_layer,
                }))
        return self.list()

    def register(self, capability: Capability) -> Capability:
        path = self.directory / f"{capability.capability_id}.json"
        if path.exists():
            raise ValueError(f"Capability 已存在：{capability.capability_id}")
        atomic_json(path, capability.model_dump(mode="json"))
        return capability

    def upsert(self, capability: Capability) -> Capability:
        atomic_json(self.directory / f"{capability.capability_id}.json", capability.model_dump(mode="json"))
        return capability

    def get(self, capability_id: str) -> Capability:
        path = self.directory / f"{capability_id}.json"
        if not path.is_file():
            raise KeyError(f"Capability 不存在：{capability_id}")
        return Capability.model_validate_json(path.read_text(encoding="utf-8"))

    def list(self) -> list[Capability]:
        return load_models(self.directory, Capability)


def initial_capabilities() -> list[Capability]:
    definitions = [
        ("research", "可追溯调研", "research", "researcher", ["alysia/agents/researcher.py"], "stable", ["topic"], ["research"], "studio"),
        ("script", "结构化脚本", "writing", "writer", ["alysia/agents/writer.py"], "stable", ["topic", "research"], ["script"], "studio"),
        ("storyboard", "结构化分镜", "direction", "storyboard_director", ["alysia/agents/director.py"], "stable", ["script"], ["storyboard"], "studio"),
        ("scene_selection", "关键镜头选择", "visual", "designer", ["alysia/visual/planner.py"], "stable", ["storyboard"], ["selected_scenes"], "production"),
        ("visual_planning", "结构化视觉计划", "visual", "designer", ["alysia/visual/planner.py"], "stable", ["selected_scenes"], ["scene_visual_plan"], "production"),
        ("visual_remotion", "程序化视觉", "visual", "designer", ["alysia/workers/composition.py", "video/remotion"], "stable", ["storyboard"], ["visual_assets"], "production"),
        ("visual_h3_local", "本地 H3 动态镜头", "visual", "designer", ["alysia/visual", "alysia/providers/visual"], "experimental", ["scene_visual_plan"], ["visual_clip"], "production"),
        ("visual_qa", "视觉素材 QA", "qa", "critic", ["alysia/visual/qa.py"], "stable", ["visual_clip"], ["approved_visual_clip"], "production"),
        ("editor_integration", "视觉素材编辑集成", "editing", "editor", ["alysia/workers/composition.py", "alysia/workers/video.py"], "stable", ["approved_visual_clip"], ["final_video"], "studio"),
        ("video_qa", "成片 QA", "qa", "critic", ["alysia/workers/video_qa.py"], "stable", ["final_video"], ["video_qa_report"], "studio"),
        ("tts", "中文旁白生成", "audio", "voice", ["alysia/workers/voice.py"], "experimental", ["script"], ["audio"], "studio"),
        ("subtitle_alignment", "语义字幕与对齐", "audio", "voice", ["alysia/workers/subtitle.py"], "experimental", ["script", "audio"], ["subtitles"], "studio"),
        ("audio_qa", "语音与字幕 QA", "qa", "voice", ["alysia/workers/audio_qa.py"], "stable", ["audio", "subtitles"], ["audio_qa_report"], "studio"),
        ("video_render", "视频渲染", "editing", "editor", ["alysia/workers/video.py"], "stable", ["storyboard", "audio", "subtitles"], ["final_video"], "studio"),
        ("publish_gate", "人工审批发布", "publishing", "publisher", ["alysia/publishing"], "stable", ["publish_package"], ["publish_job"], "studio"),
        ("analytics", "内容表现分析", "learning", "analyst", ["alysia/analytics"], "stable", ["feedback_metrics"], ["performance_analysis"], "studio"),
        ("long_term_memory", "长期经验记忆", "learning", "analyst", ["alysia/learning"], "stable", ["performance_analysis"], ["lessons"], "studio"),
        ("topic_planning", "自主选题", "planning", "supervisor", ["alysia/planning"], "stable", ["channel_goal"], ["content_plan"], "supervisor"),
        ("multi_agent_studio", "受控创作团队", "orchestration", "studio_director", ["alysia/studio"], "stable", ["approved_content_run"], ["review_ready_content"], "studio"),
        ("long_horizon_supervision", "长期目标监督", "orchestration", "supervisor", ["alysia/supervisor"], "stable", ["long_term_goal"], ["workflow_task"], "supervisor"),
    ]
    now = datetime.now().astimezone()
    return [
        Capability(
            capability_id=capability_id, name=name, description=name, category=category,
            owner_agent=owner, implementation_refs=refs, maturity=maturity,
            known_limits=["以对应阶段开发报告与测试为边界"], prerequisites=[],
            evaluation_suite=[f"tests/test_{'visual_generation' if capability_id == 'visual_h3_local' else category}.py"],
            last_verified_at=now if maturity == "stable" else None,
            tags=[category, capability_id], accepted_inputs=accepted_inputs,
            produced_outputs=produced_outputs, execution_layer=execution_layer,
            resource_requirements=(
                {"gpu_heavy": True, "sequential_gpu_required": True, "peak_vram_mb": "unknown"}
                if capability_id == "visual_h3_local" else {}
            ),
            policy_restrictions=(
                ["human_publish_approval"] if capability_id == "publish_gate" else []
            ),
        )
        for capability_id, name, category, owner, refs, maturity, accepted_inputs, produced_outputs, execution_layer in definitions
    ]

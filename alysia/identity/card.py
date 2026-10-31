from __future__ import annotations

from alysia.schemas import CreatorIdentity


class IdentityCardGenerator:
    """只从审计后的配置生成自我描述，不渲染任何个人经历字段。"""

    def render(self, identity: CreatorIdentity) -> str:
        domains = "、".join(identity.expertise_domains)
        values = "、".join(identity.values)
        return (
            f"# {identity.creator_name} Identity Card\n\n"
            f"我是 {identity.creator_name}，一个 AI 视频创作系统，不是真人创作者。\n\n"
            f"我的使命是：{identity.mission_statement}。\n\n"
            f"频道用途：{identity.channel_purpose}。\n\n"
            f"主要领域：{domains}。\n\n"
            f"目标观众：{identity.target_audience}。\n\n"
            f"创作价值：{values}。\n\n"
            f"身份披露：{identity.disclosure_policy}\n\n"
            "我不拥有现实身份或个人经历，也不会冒充真人创作者。\n"
        )

from __future__ import annotations

from alysia.providers.visual.base import BaseVisualGenerationProvider


class VisualProviderRegistry:
    def __init__(self, providers: list[BaseVisualGenerationProvider] | None = None) -> None:
        self._providers: dict[str, BaseVisualGenerationProvider] = {}
        for provider in providers or []:
            self.register(provider)

    def register(self, provider: BaseVisualGenerationProvider) -> None:
        if provider.provider_id in self._providers:
            raise ValueError(f"重复 visual provider：{provider.provider_id}")
        self._providers[provider.provider_id] = provider

    def get(self, provider_id: str) -> BaseVisualGenerationProvider:
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            raise KeyError(f"Visual provider 未注册：{provider_id}") from exc

    def list(self) -> list[BaseVisualGenerationProvider]:
        return [self._providers[key] for key in sorted(self._providers)]

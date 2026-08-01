from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import BrandInput, ProviderResponse, Question


class ProviderClient(ABC):
    name: str
    model_version: str

    @abstractmethod
    async def query(self, question: Question, brand: BrandInput) -> ProviderResponse:
        """Return one answer for one question."""


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ProviderClient] = {}
        self._aliases = {
            "openai": "gpt",
            "chatgpt": "gpt",
            "deepseek": "deepseek",
            "千问": "qwen",
            "通义千问": "qwen",
            "豆包": "doubao",
            "minimax": "minimax",
            "mini max": "minimax",
            "MiniMax": "minimax",
        }

    def register(self, provider: ProviderClient) -> None:
        self._providers[provider.name] = provider

    def select(self, names: list[str] | None = None) -> list[ProviderClient]:
        if not names:
            return list(self._providers.values())
        normalized = [self._normalize_name(name) for name in names]
        missing = [name for name in normalized if name not in self._providers]
        if missing:
            raise ValueError(f"Unknown providers: {', '.join(missing)}")
        return [self._providers[name] for name in normalized]

    @property
    def names(self) -> list[str]:
        return list(self._providers.keys())

    def _normalize_name(self, name: str) -> str:
        stripped = str(name).strip()
        return self._aliases.get(stripped, self._aliases.get(stripped.lower(), stripped.lower()))

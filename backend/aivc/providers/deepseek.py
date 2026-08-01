from __future__ import annotations

from .openai_compatible import OpenAICompatibleConfig, OpenAICompatibleProvider


class DeepSeekProvider(OpenAICompatibleProvider):
    def __init__(self) -> None:
        super().__init__(
            OpenAICompatibleConfig(
                name="deepseek",
                api_key_env="DEEPSEEK_API_KEY",
                default_base_url="https://api.deepseek.com",
                default_model="deepseek-v4-flash",
                extra_payload={"thinking": {"type": "disabled"}},
            )
        )


def build_provider() -> DeepSeekProvider:
    return DeepSeekProvider()

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..models import BrandInput, Citation, ProviderResponse, Question, QuestionType
from .base import ProviderClient


@dataclass(frozen=True)
class OpenAICompatibleConfig:
    name: str
    api_key_env: str | None = None
    api_key_envs: list[str] = field(default_factory=list)
    default_base_url: str | None = None
    default_model: str | None = None
    base_url_env: str | None = None
    base_url_envs: list[str] = field(default_factory=list)
    model_env: str | None = None
    model_envs: list[str] = field(default_factory=list)
    extra_payload: dict = field(default_factory=dict)


class OpenAICompatibleProvider(ProviderClient):
    def __init__(
        self,
        config: OpenAICompatibleConfig,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: int = 60,
    ) -> None:
        self.name = config.name
        self.api_key = api_key or _first_env([*config.api_key_envs, config.api_key_env or ""])
        self.base_url = (
            base_url
            or _first_env([*config.base_url_envs, config.base_url_env or "", f"{config.name.upper()}_BASE_URL"])
            or config.default_base_url
            or ""
        ).rstrip("/")
        self.model_version = (
            model
            or _first_env([*config.model_envs, config.model_env or "", f"{config.name.upper()}_MODEL"])
            or config.default_model
            or ""
        )
        self.extra_payload = dict(config.extra_payload)
        timeout_env = _first_env([f"{config.name.upper()}_TIMEOUT_SECONDS", "AIVC_PROVIDER_TIMEOUT_SECONDS"])
        self.timeout_seconds = int(timeout_env) if timeout_env.isdigit() else (120 if config.name == "doubao" else timeout_seconds)
        if not self.api_key:
            env_names = ", ".join([*config.api_key_envs, config.api_key_env or "API_KEY"])
            raise ValueError(f"{env_names} is required for provider {self.name}")
        if not self.base_url:
            raise ValueError(f"Base URL is required for provider {self.name}")
        if not self.model_version:
            raise ValueError(f"Model is required for provider {self.name}")

    async def query(self, question: Question, brand: BrandInput) -> ProviderResponse:
        started = time.perf_counter()
        response = await asyncio.to_thread(self._chat_completion, question, brand)
        latency_ms = int((time.perf_counter() - started) * 1000)
        message = response.get("choices", [{}])[0].get("message", {})
        answer = message.get("content") or ""
        usage = response.get("usage") or {}
        total_tokens = usage.get("total_tokens") or max(1, len(answer) // 2)
        return ProviderResponse(
            provider=self.name,
            model_version=response.get("model") or self.model_version,
            question_id=question.id,
            question=question.text,
            answer=answer,
            latency_ms=latency_ms,
            token_count=int(total_tokens),
            citations=_extract_citations(response),
            web_enabled=bool(response.get("citations") or response.get("search_results")),
        )

    def _chat_completion(self, question: Question, brand: BrandInput) -> dict:
        source_instruction = (
            "如果用户问题是在询问信息来源，请尽量用清单回答，每条包含：来源名称、完整网址、引文类别、页面类型、适合核实的信息。"
            "不要只写平台名，能给域名或具体页面就给域名或具体页面。"
            if question.type == QuestionType.CITATION_SOURCE
            else ""
        )
        payload = {
            "model": self.model_version,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是中国市场 AI 搜索可见度测评中的受测 AI。"
                        "请像真实用户搜索助手一样回答，客观、简洁，必要时列出推荐顺序。"
                        f"{source_instruction}"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"品牌：{brand.brand_name}\n"
                        f"行业：{brand.industry or '待调研'}\n"
                        f"主要产品：{brand.product_text}\n"
                        f"竞品：{'、'.join(brand.competitors) or '待调研'}\n"
                        f"用户问题：{question.text}"
                    ),
                },
            ],
            "stream": False,
        }
        payload.update(self.extra_payload)
        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=True).encode("utf-8"),
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as raw_response:
                return json.loads(raw_response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{self.name} API HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"{self.name} API request failed: {exc.reason}") from exc


KNOWN_OPENAI_COMPATIBLE_CONFIGS = [
    OpenAICompatibleConfig(
        name="gpt",
        api_key_envs=["GPT_API_KEY", "OPENAI_API_KEY"],
        default_base_url="https://api.openai.com/v1",
        default_model="gpt-4.1-mini",
        base_url_env="GPT_BASE_URL",
        base_url_envs=["OPENAI_BASE_URL"],
        model_env="GPT_MODEL",
        model_envs=["OPENAI_MODEL"],
    ),
    OpenAICompatibleConfig(
        name="deepseek",
        api_key_env="DEEPSEEK_API_KEY",
        default_base_url="https://api.deepseek.com",
        default_model="deepseek-v4-flash",
        extra_payload={"thinking": {"type": "disabled"}},
    ),
    OpenAICompatibleConfig(
        name="qwen",
        api_key_envs=["QWEN_API_KEY", "DASHSCOPE_API_KEY"],
        default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        default_model="qwen-plus",
        base_url_env="QWEN_BASE_URL",
        base_url_envs=["DASHSCOPE_BASE_URL"],
        model_env="QWEN_MODEL",
        model_envs=["DASHSCOPE_MODEL"],
    ),
    OpenAICompatibleConfig(
        name="doubao",
        api_key_envs=["DOUBAO_API_KEY", "ARK_API_KEY", "VOLCENGINE_API_KEY"],
        default_base_url="https://ark.cn-beijing.volces.com/api/v3",
        default_model="doubao-seed-1-6-250615",
        base_url_env="DOUBAO_BASE_URL",
        base_url_envs=["ARK_BASE_URL", "VOLCENGINE_BASE_URL"],
        model_env="DOUBAO_MODEL",
        model_envs=["ARK_MODEL", "VOLCENGINE_MODEL"],
    ),
    OpenAICompatibleConfig(
        name="minimax",
        api_key_env="MINIMAX_API_KEY",
        default_base_url="https://api.minimax.chat/v1",
        default_model="MiniMax-M1",
        base_url_env="MINIMAX_BASE_URL",
        model_env="MINIMAX_MODEL",
    ),
]


def build_configured_openai_compatible_providers() -> list[OpenAICompatibleProvider]:
    providers: list[OpenAICompatibleProvider] = []
    for config in [*KNOWN_OPENAI_COMPATIBLE_CONFIGS, *_custom_configs()]:
        try:
            providers.append(OpenAICompatibleProvider(config))
        except ValueError:
            continue
    return providers


def _custom_configs() -> list[OpenAICompatibleConfig]:
    raw = os.environ.get("AIVC_OPENAI_COMPATIBLE_PROVIDERS")
    if not raw:
        return []
    payload = json.loads(raw)
    configs: list[OpenAICompatibleConfig] = []
    for item in payload:
        configs.append(
            OpenAICompatibleConfig(
                name=item["name"],
                api_key_env=item["api_key_env"],
                default_base_url=item.get("base_url"),
                default_model=item.get("model"),
                base_url_env=item.get("base_url_env"),
                base_url_envs=item.get("base_url_envs") or [],
                model_env=item.get("model_env"),
                model_envs=item.get("model_envs") or [],
                extra_payload=item.get("extra_payload") or {},
            )
        )
    return configs


def _first_env(names: list[str]) -> str:
    for name in names:
        if name and os.environ.get(name):
            return os.environ[name]
    return ""


def _extract_citations(response: dict) -> list[Citation]:
    citations: list[Citation] = []
    for index, item in enumerate(response.get("citations") or []):
        if isinstance(item, str):
            citations.append(Citation(title=f"引用来源 {index + 1}", url=item, source_type="新闻媒体", authority=0.72))
        elif isinstance(item, dict):
            citations.append(
                Citation(
                    title=item.get("title") or f"引用来源 {index + 1}",
                    url=item.get("url") or item.get("link") or "",
                    source_type=item.get("source_type") or "新闻媒体",
                    authority=float(item.get("authority") or 0.72),
                )
            )
    return citations

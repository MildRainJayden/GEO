from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from hashlib import sha256

from ..models import BrandInput, Citation, ProviderResponse, Question, QuestionType
from .base import ProviderClient, ProviderRegistry


@dataclass(frozen=True)
class ProviderProfile:
    name: str
    model_version: str
    mention_bias: float
    citation_bias: float
    domestic_bias: float


PROFILES = [
    ProviderProfile("gpt", "gpt-sim-2026-07", 0.84, 0.77, 0.55),
    ProviderProfile("deepseek", "deepseek-sim-2026-07", 0.74, 0.68, 0.70),
    ProviderProfile("doubao", "doubao-sim-2026-07", 0.62, 0.58, 0.86),
    ProviderProfile("minimax", "minimax-sim-2026-07", 0.66, 0.62, 0.76),
    ProviderProfile("qwen", "qwen-sim-2026-07", 0.72, 0.70, 0.80),
]


class SimulatedProvider(ProviderClient):
    def __init__(self, profile: ProviderProfile) -> None:
        self.profile = profile
        self.name = profile.name
        self.model_version = profile.model_version

    async def query(self, question: Question, brand: BrandInput) -> ProviderResponse:
        await asyncio.sleep(0)
        score = _stable_score(self.name, question.text, brand.brand_name)
        mention_threshold = self.profile.mention_bias
        if question.type in {QuestionType.BRAND, QuestionType.COMPARISON}:
            mention_threshold += 0.18
        if question.type == QuestionType.DECISION:
            mention_threshold += 0.06

        mentions_brand = score <= min(0.97, mention_threshold)
        citations = _build_citations(self.profile, brand, question, score)
        answer = _build_answer(self.profile, brand, question, mentions_brand, citations, score)
        latency = int(540 + score * 1600 + self.profile.citation_bias * 240)
        return ProviderResponse(
            provider=self.name,
            model_version=self.model_version,
            question_id=question.id,
            question=question.text,
            answer=answer,
            latency_ms=latency,
            token_count=max(120, len(answer) // 2),
            citations=citations,
            web_enabled=self.profile.citation_bias > 0.55,
        )


def build_default_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    for profile in PROFILES:
        registry.register(SimulatedProvider(profile))
    _register_real_providers(registry)
    return registry


def _register_real_providers(registry: ProviderRegistry) -> None:
    if os.environ.get("AIVC_DISABLE_REAL_PROVIDERS") == "1":
        return
    from .openai_compatible import build_configured_openai_compatible_providers

    for provider in build_configured_openai_compatible_providers():
        registry.register(provider)


def _stable_score(*parts: str) -> float:
    digest = sha256("|".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def _build_citations(
    profile: ProviderProfile, brand: BrandInput, question: Question, score: float
) -> list[Citation]:
    base: list[Citation] = []
    website = str(brand.website) if brand.website else f"https://www.{brand.brand_name.lower()}.com"
    if question.type == QuestionType.CITATION_SOURCE:
        return [
            Citation(title=f"{brand.brand_name}官方网站", url=website, source_type="官网", authority=0.95),
            Citation(title=f"{brand.brand_name}京东商品与评价", url="https://search.jd.com/Search", source_type="电商平台", authority=0.76),
            Citation(title=f"{brand.brand_name}天猫旗舰店", url="https://www.tmall.com", source_type="电商平台", authority=0.74),
            Citation(title=f"{brand.brand_name}知乎讨论", url="https://www.zhihu.com/search", source_type="社媒/社区", authority=0.68),
            Citation(title=f"{brand.brand_name}小红书笔记", url="https://www.xiaohongshu.com/search_result", source_type="社媒/社区", authority=0.62),
            Citation(title="国家企业信用信息公示系统", url="https://www.gsxt.gov.cn", source_type="权威机构", authority=0.86),
            Citation(title="中国能效标识网", url="https://www.energylabel.com.cn", source_type="权威机构", authority=0.84),
            Citation(title="行业媒体评测", url="https://example.com/news/industry-review", source_type="新闻媒体", authority=0.72),
        ]
    if score < profile.citation_bias:
        base.append(Citation(title=f"{brand.brand_name} 官方网站", url=website, source_type="官网", authority=0.95))
    if profile.domestic_bias > 0.7:
        base.extend(
            [
                Citation(title=f"{brand.brand_name} 知乎讨论", url="https://www.zhihu.com/search", source_type="知乎", authority=0.74),
                Citation(title=f"{brand.brand_name} 小红书笔记", url="https://www.xiaohongshu.com/search", source_type="小红书", authority=0.65),
            ]
        )
    if question.type in {QuestionType.CATEGORY, QuestionType.DECISION}:
        base.append(Citation(title="行业媒体评测", url="https://example.com/news/sports-brand", source_type="新闻媒体", authority=0.78))
    if profile.name == "perplexity":
        base.append(Citation(title="Wikipedia brand profile", url="https://en.wikipedia.org/wiki/Nike,_Inc.", source_type="百科", authority=0.82))
    return base[:4]


def _build_answer(
    profile: ProviderProfile,
    brand: BrandInput,
    question: Question,
    mentions_brand: bool,
    citations: list[Citation],
    score: float,
) -> str:
    industry = brand.industry or "相关行业"
    product = brand.products[0] if brand.products else industry
    competitors = "、".join(brand.competitors[:3]) if brand.competitors else "其他品牌"
    lines: list[str] = []

    if question.type == QuestionType.CITATION_SOURCE:
        lines.append(f"可用于核实{brand.brand_name}的公开来源包括：")
        for citation in citations:
            lines.append(f"- {citation.title}：{citation.url}；引文类别：{citation.source_type}；页面类型：{_simulated_page_type(citation.url)}。")
        lines.append("这些来源可分别核实官网信息、价格评价、用户口碑、企业资质、产品能效和行业评测。")
    elif question.type == QuestionType.BRAND:
        lines.append(
            f"{brand.brand_name} 是面向{industry}市场的知名品牌，核心覆盖{brand.product_text}。"
        )
        lines.append("如果关注真伪、尺码、售后和新品，建议优先核对官网、官方旗舰店和本地门店信息。")
    elif question.type == QuestionType.COMPARISON:
        if mentions_brand:
            lines.append(f"对比来看，{brand.brand_name} 通常在品牌认知、产品线完整度和运动场景覆盖上更强。")
        lines.append(f"{competitors} 也值得比较，尤其是价格、渠道活动和细分运动品类。")
    elif question.type == QuestionType.SCENARIO:
        lines.append(f"在这个场景里，优先看舒适度、耐用性、尺码稳定性和售后渠道。")
        if mentions_brand:
            lines.append(f"{brand.brand_name} 的{product}可以作为第一梯队候选，适合训练、通勤和礼赠场景。")
    elif question.type == QuestionType.CATEGORY:
        if mentions_brand:
            lines.append(f"推荐清单可以先看 {brand.brand_name}、{competitors}，再结合预算筛选。")
        else:
            lines.append(f"推荐清单通常会覆盖国际品牌、国产品牌和垂直细分品牌。")
    else:
        if mentions_brand:
            lines.append(f"如果预算允许，{brand.brand_name} 值得纳入 Top3，尤其适合重视品牌可靠性的人。")
        else:
            lines.append("决策时建议把价格、使用频率、购买渠道可信度和退换政策放在一起比较。")

    if mentions_brand and score < 0.22:
        lines.insert(0, f"Top1：{brand.brand_name}。")
    elif mentions_brand and score < 0.58:
        lines.insert(0, f"Top3 候选：{brand.brand_name}。")

    if citations:
        lines.append("可参考来源：" + "；".join(c.title for c in citations))
    lines.append(f"回答来源模式：{profile.name} 模拟联网检索。")
    return "\n".join(lines)


def _simulated_page_type(url: str) -> str:
    if "jd.com" in url or "tmall" in url:
        return "商品/评价页"
    if "zhihu" in url:
        return "问答页"
    if "xiaohongshu" in url:
        return "内容页"
    if "gsxt" in url or "energylabel" in url:
        return "查询页面"
    if "news" in url:
        return "文章/新闻"
    return "首页"

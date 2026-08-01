from __future__ import annotations

import json
import re
from dataclasses import dataclass

from ..models import AuditRequest, BrandInput, Question, QuestionType
from ..providers.base import ProviderClient, ProviderRegistry


@dataclass(frozen=True)
class BrandResearch:
    website: str | None
    industry: str
    products: list[str]
    competitors: list[str]
    regions: list[str]


KNOWN_BRANDS: dict[str, BrandResearch] = {
    "美的": BrandResearch(
        website="https://www.midea.com.cn",
        industry="智能家电与全球科技集团",
        products=["家用空调", "中央空调", "冰箱", "洗衣机", "厨房电器", "生活小家电", "热水器", "净水器"],
        competitors=["海尔", "格力", "小米", "海信", "TCL", "松下", "西门子家电"],
        regions=["中国", "北京", "上海", "广州", "深圳", "成都", "杭州"],
    ),
    "midea": BrandResearch(
        website="https://www.midea.com.cn",
        industry="智能家电与全球科技集团",
        products=["家用空调", "中央空调", "冰箱", "洗衣机", "厨房电器", "生活小家电", "热水器", "净水器"],
        competitors=["海尔", "格力", "小米", "海信", "TCL", "松下", "西门子家电"],
        regions=["中国", "北京", "上海", "广州", "深圳", "成都", "杭州"],
    ),
    "nike": BrandResearch(
        website="https://www.nike.com",
        industry="运动服饰",
        products=["运动鞋", "运动服饰", "跑步装备"],
        competitors=["Adidas", "Puma", "Under Armour", "安踏", "李宁"],
        regions=["中国", "北京", "上海", "广州", "深圳", "成都"],
    ),
}


async def enrich_request(request: AuditRequest, registry: ProviderRegistry) -> tuple[BrandInput, int, list[str]]:
    research = await _research_with_ai(request, registry) if _needs_research(request) else None
    research = research or _known_brand(request.brand_name) or _generic_research(request.brand_name)

    website = request.website or research.website
    industry = request.industry or research.industry
    products = request.products or research.products
    competitors = request.competitors or research.competitors
    regions = request.regions or research.regions
    question_count = request.question_count or _adaptive_question_count(products, competitors, bool(request.industry), bool(request.website))

    brand = BrandInput(
        brand_name=request.brand_name,
        website=website,
        industry=industry,
        products=products,
        competitors=competitors,
        regions=regions,
    )
    providers = request.providers or _adaptive_providers(registry)
    return brand, question_count, providers


def _needs_research(request: AuditRequest) -> bool:
    return not request.website or not request.industry or not request.products or not request.competitors


async def _research_with_ai(request: AuditRequest, registry: ProviderRegistry) -> BrandResearch | None:
    real_candidates = [
        provider
        for provider in registry.select(request.providers)
        if provider.__class__.__name__ != "SimulatedProvider"
    ]
    if not real_candidates:
        return None
    provider = real_candidates[0]
    prompt = (
        "请调研并补全品牌测评信息，只输出 JSON，不要输出解释。字段："
        "website、industry、products、competitors、regions。"
        "products 和 competitors 各给 5-8 个，regions 给中国主要城市。"
        f"\n品牌：{request.brand_name}"
        f"\n官网：{request.website or ''}"
        f"\n行业：{request.industry or ''}"
    )
    question = Question(text=prompt, type=QuestionType.BRAND)
    try:
        response = await provider.query(question, BrandInput(brand_name=request.brand_name))
        payload = _parse_json_object(response.answer)
        if not payload:
            return None
        return BrandResearch(
            website=payload.get("website") or None,
            industry=str(payload.get("industry") or "").strip(),
            products=_as_list(payload.get("products")),
            competitors=_as_list(payload.get("competitors")),
            regions=_as_list(payload.get("regions")) or ["中国", "北京", "上海", "深圳"],
        )
    except Exception:
        return None


def _parse_json_object(text: str) -> dict | None:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[,，、\n]", value) if item.strip()]
    return []


def _known_brand(brand_name: str) -> BrandResearch | None:
    return KNOWN_BRANDS.get(brand_name.lower()) or KNOWN_BRANDS.get(brand_name)


def _generic_research(brand_name: str) -> BrandResearch:
    return BrandResearch(
        website=None,
        industry="综合消费品牌",
        products=["核心产品", "主力服务", "旗舰产品"],
        competitors=["主要竞品", "替代品牌", "同类品牌"],
        regions=["中国", "北京", "上海", "深圳"],
    )


def _adaptive_question_count(products: list[str], competitors: list[str], has_industry: bool, has_website: bool) -> int:
    base = 35
    base += min(len(products), 8) * 3
    base += min(len(competitors), 8) * 2
    if not has_industry:
        base += 8
    if not has_website:
        base += 6
    return max(30, min(90, base))


def _adaptive_providers(registry: ProviderRegistry) -> list[str]:
    preferred = ["gpt", "deepseek", "doubao", "minimax", "qwen"]
    available_providers = {provider.name: provider for provider in registry.select()}
    real = [
        name
        for name in preferred
        if name in available_providers and available_providers[name].__class__.__name__ != "SimulatedProvider"
    ]
    if real:
        return real
    return [name for name in preferred if name in available_providers] or list(available_providers)

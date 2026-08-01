from __future__ import annotations

import re

from ..models import BrandInput, BrandMentionAnalysis, ProviderResponse


POSITIVE_WORDS = ["推荐", "可靠", "知名", "适合", "值得", "第一梯队", "更强", "Top1", "Top3"]
NEGATIVE_WORDS = ["不推荐", "风险", "投诉", "负面", "不靠谱"]


def analyze_brand_response(response: ProviderResponse, brand: BrandInput) -> BrandMentionAnalysis:
    answer = response.answer
    brand_pattern = re.compile(re.escape(brand.brand_name), re.IGNORECASE)
    mention_count = len(brand_pattern.findall(answer))
    brand_mentioned = mention_count > 0
    recommendation_position = _recommendation_position(answer, brand.brand_name)
    sentiment = _sentiment(answer)
    covered_terms = [term for term in [brand.industry, *brand.products] if term and term in answer]
    description_correct = brand_mentioned and bool(covered_terms)
    error_types = [] if description_correct or not brand_mentioned else ["行业错误"]
    return BrandMentionAnalysis(
        provider=response.provider,
        question_id=response.question_id,
        brand_mentioned=brand_mentioned,
        mention_count=mention_count,
        recommendation_position=recommendation_position,
        sentiment=sentiment,
        description_correct=description_correct,
        error_types=error_types,
        industry_terms_covered=covered_terms,
    )


def _recommendation_position(answer: str, brand_name: str) -> str:
    if not re.search(re.escape(brand_name), answer, re.IGNORECASE):
        return "未推荐"
    before_brand = answer[: answer.lower().find(brand_name.lower()) if brand_name.lower() in answer.lower() else 0]
    if "Top1" in before_brand or answer.startswith(f"Top1：{brand_name}"):
        return "Top1"
    if "Top3" in before_brand or "Top3 候选" in answer:
        return "Top3"
    return "Top5"


def _sentiment(answer: str) -> str:
    if any(word in answer for word in NEGATIVE_WORDS):
        return "消极"
    if any(word in answer for word in POSITIVE_WORDS):
        return "积极"
    return "中性"

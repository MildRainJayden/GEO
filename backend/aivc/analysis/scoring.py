from __future__ import annotations

from collections import defaultdict

from ..models import BrandMentionAnalysis, CompetitorMetric, PlatformScore, ProviderResponse, ScoreBreakdown


def compute_visibility_score(
    analyses: list[BrandMentionAnalysis],
    responses: list[ProviderResponse],
    provider_count: int,
) -> ScoreBreakdown:
    total = len(analyses) or 1
    mention_rate = sum(a.brand_mentioned for a in analyses) / total
    top3_rate = sum(a.recommendation_position in {"Top1", "Top3"} for a in analyses) / total
    accuracy_rate = sum(a.description_correct for a in analyses) / total
    covered_providers = len({a.provider for a in analyses if a.brand_mentioned})
    platform_coverage = covered_providers / max(provider_count, 1)
    citation_quality = _citation_quality(responses)
    industry_coverage = sum(bool(a.industry_terms_covered) for a in analyses) / total
    quality_signal_rate = _quality_signal_rate(analyses, responses)
    confidence = _sample_confidence(total, provider_count)

    raw_score = (
        mention_rate * 40
        + accuracy_rate * 30
        + platform_coverage * 10
        + industry_coverage * 20
    )
    total_score = raw_score * confidence
    if quality_signal_rate < 0.2:
        total_score = min(total_score, 85.0 if provider_count < 2 else 92.0)

    return ScoreBreakdown(
        total_score=round(total_score, 2),
        mention_rate_score=round(mention_rate * 40, 2),
        top3_rate_score=round(top3_rate * 100, 2),
        accuracy_score=round(accuracy_rate * 30, 2),
        platform_coverage_score=round(platform_coverage * 10, 2),
        citation_quality_score=round(citation_quality * 100, 2),
        industry_coverage_score=round(industry_coverage * 20, 2),
        competitive_voice_score=0.0,
        base_visibility_score=round(total_score, 2),
        platform_scores=_platform_scores(analyses, responses),
        trend_score=round(min(100, total_score + 7.5), 2),
    )


def apply_competitive_voice_score(
    score: ScoreBreakdown,
    brand_name: str,
    competitors: list[CompetitorMetric],
) -> ScoreBreakdown:
    if not competitors:
        score.base_visibility_score = score.base_visibility_score or score.total_score
        return score
    own = next((item for item in competitors if item.brand.strip().lower() == brand_name.strip().lower()), None)
    if own is None:
        score.base_visibility_score = score.base_visibility_score or score.total_score
        score.competitive_voice_score = 0.0
        score.total_score = round(score.total_score * 0.7, 2)
        score.trend_score = round(min(100, score.total_score + 7.5), 2)
        return score

    leader_share = max((item.voice_share or item.mention_rate for item in competitors), default=0.0)
    own_share = own.voice_share or own.mention_rate
    relative_share = own_share / leader_share if leader_share > 0 else 0.0
    rank_score = _average_rank_score(own.average_rank)
    competitive_score = (
        own_share * 45
        + min(relative_share, 1.0) * 25
        + own.top3_rate * 15
        + rank_score * 10
        + own.occurrence_rate * 5
    )

    base_score = score.base_visibility_score or score.total_score
    score.base_visibility_score = round(base_score, 2)
    score.competitive_voice_score = round(competitive_score, 2)
    score.total_score = round(base_score * 0.7 + competitive_score * 0.3, 2)
    score.trend_score = round(min(100, score.total_score + 7.5), 2)
    return score


def _citation_quality(responses: list[ProviderResponse]) -> float:
    citations = [citation for response in responses for citation in response.citations]
    if not citations:
        return 0
    return sum(c.authority for c in citations) / len(citations)


def _platform_scores(
    analyses: list[BrandMentionAnalysis],
    responses: list[ProviderResponse],
) -> list[PlatformScore]:
    grouped: dict[str, list[BrandMentionAnalysis]] = defaultdict(list)
    response_grouped: dict[str, list[ProviderResponse]] = defaultdict(list)
    for analysis in analyses:
        grouped[analysis.provider].append(analysis)
    for response in responses:
        response_grouped[response.provider].append(response)

    platform_scores: list[PlatformScore] = []
    for provider, items in grouped.items():
        total = len(items) or 1
        mention_rate = sum(a.brand_mentioned for a in items) / total
        top3_rate = sum(a.recommendation_position in {"Top1", "Top3"} for a in items) / total
        accuracy_rate = sum(a.description_correct for a in items) / total
        citation_quality = _citation_quality(response_grouped[provider])
        industry_coverage = sum(bool(a.industry_terms_covered) for a in items) / total
        confidence = _sample_confidence(total, 1)
        quality_signal_rate = _quality_signal_rate(items, response_grouped[provider])
        score = (mention_rate * 45 + accuracy_rate * 35 + industry_coverage * 20) * confidence
        if quality_signal_rate < 0.2:
            score = min(score, 85.0)
        platform_scores.append(
            PlatformScore(
                provider=provider,
                score=round(score, 2),
                mention_rate=round(mention_rate, 4),
                top3_rate=round(top3_rate, 4),
                accuracy_rate=round(accuracy_rate, 4),
                citation_quality=round(citation_quality, 4),
                explanation=_platform_explanation(provider, score, mention_rate, top3_rate, accuracy_rate, citation_quality),
            )
        )
    return sorted(platform_scores, key=lambda item: item.score, reverse=True)


def _platform_explanation(
    provider: str,
    score: float,
    mention_rate: float,
    top3_rate: float,
    accuracy_rate: float,
    citation_quality: float,
) -> str:
    strengths: list[str] = []
    risks: list[str] = []
    if mention_rate >= 0.8:
        strengths.append("品牌提及稳定")
    else:
        risks.append("品牌提及不足")
    if accuracy_rate >= 0.7:
        strengths.append("品牌描述较准确")
    else:
        risks.append("行业或产品事实覆盖不够")
    if top3_rate < 0.15:
        risks.append("同类推荐中的靠前度偏弱")
    if citation_quality == 0:
        risks.append("可被公开资料支撑的表达仍可加强")

    verdict = "表现较强" if score >= 75 else "表现中等" if score >= 55 else "需要重点优化"
    return f"{provider} {verdict}：" + "；".join([*(strengths[:2] or ["有基础曝光"]), *(risks[:2])]) + "。"


def _sample_confidence(total_answers: int, provider_count: int) -> float:
    if total_answers < 20:
        return 0.82
    if total_answers < 50:
        return 0.9
    if provider_count < 2:
        return 0.95
    return 1.0


def _average_rank_score(average_rank: float | None) -> float:
    if average_rank is None:
        return 0.0
    return max(0.0, min(1.0, 1 - (average_rank - 1) / 4))


def _quality_signal_rate(
    analyses: list[BrandMentionAnalysis],
    responses: list[ProviderResponse],
) -> float:
    total = len(analyses) or 1
    top3_hits = sum(a.recommendation_position in {"Top1", "Top3"} for a in analyses)
    cited_question_ids = {response.question_id for response in responses if response.citations}
    citation_hits = sum(a.question_id in cited_question_ids for a in analyses)
    return (top3_hits + citation_hits) / (total * 2)

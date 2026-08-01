from __future__ import annotations

import asyncio

from ..models import BrandInput, BrandMentionAnalysis, CompetitorMetric, ProviderResponse, Question, QuestionType
from ..providers.base import ProviderClient


def build_competitor_matrix(
    brand: BrandInput,
    questions: list[Question],
    responses: list[ProviderResponse],
    analyses: list[BrandMentionAnalysis],
) -> list[CompetitorMetric]:
    """Legacy fallback based on target-brand audit answers.

    The main report now prefers build_industry_benchmark_matrix because it uses
    neutral industry prompts. This fallback keeps older callers working.
    """
    question_by_id = {question.id: question for question in questions}
    response_by_id = {(response.provider, response.question_id): response for response in responses}
    matrix: list[CompetitorMetric] = []
    brands = _dedupe([brand.brand_name, *brand.competitors])
    total = len(responses) or 1
    scenario_total = sum(
        1 for response in responses if question_by_id[response.question_id].type == QuestionType.SCENARIO
    ) or 1

    for candidate in brands:
        mention_hits = 0
        top3_hits = 0
        scenario_hits = 0
        citation_count = 0
        rank_sum = 0.0

        if candidate == brand.brand_name:
            for analysis in analyses:
                if not analysis.brand_mentioned:
                    continue
                mention_hits += 1
                rank = _analysis_rank(analysis)
                rank_sum += rank
                top3_hits += int(rank <= 3)
                response = response_by_id.get((analysis.provider, analysis.question_id))
                if response:
                    citation_count += len(response.citations)
                    question = question_by_id[analysis.question_id]
                    scenario_hits += int(question.type == QuestionType.SCENARIO)
        else:
            aliases = _brand_aliases(candidate)
            for response in responses:
                answer_lower = response.answer.lower()
                rank = _match_rank(answer_lower, aliases)
                if rank is None:
                    continue
                mention_hits += 1
                rank_sum += rank
                top3_hits += int(rank <= 3)
                citation_count += sum(any(alias in c.title.lower() for alias in aliases) for c in response.citations)
                question = question_by_id[response.question_id]
                scenario_hits += int(question.type == QuestionType.SCENARIO)

        occurrence_rate = mention_hits / total
        average_rank = rank_sum / mention_hits if mention_hits else None
        top3_rate = top3_hits / total
        scenario_rate = scenario_hits / scenario_total
        matrix.append(
            CompetitorMetric(
                brand=candidate,
                mention_rate=round(occurrence_rate, 4),
                top3_rate=round(top3_rate, 4),
                industry_coverage=round(_rank_to_score(average_rank), 4),
                scenario_coverage=round(scenario_rate, 4),
                citation_count=citation_count,
                accuracy_rate=round(occurrence_rate, 4),
                voice_share=round(occurrence_rate, 4),
                occurrence_rate=round(occurrence_rate, 4),
                average_rank=round(average_rank, 2) if average_rank is not None else None,
                effective_sample_count=total,
                scenario_sample_count=scenario_total,
            )
        )
    return matrix


async def build_industry_benchmark_matrix(
    brand: BrandInput,
    providers: list[ProviderClient],
) -> list[CompetitorMetric]:
    """Compare candidate brands with neutral industry-ranking prompts."""
    candidate_brands = sorted(_dedupe([brand.brand_name, *brand.competitors]), key=lambda item: item.lower())
    candidate_text = "、".join(candidate_brands)
    questions = _benchmark_questions(brand, candidate_brands)
    neutral_context = BrandInput(
        brand_name=f"候选品牌池：{candidate_text}",
        industry=brand.industry,
        products=brand.products,
        competitors=candidate_brands,
        regions=brand.regions,
    )
    jobs = [(provider, question) for question in questions for provider in providers]
    results = await asyncio.gather(
        *(provider.query(question, neutral_context) for provider, question in jobs),
        return_exceptions=True,
    )
    responses = [result for result in results if isinstance(result, ProviderResponse)]
    if not responses:
        raise RuntimeError("industry benchmark failed for all providers")

    question_by_id = {question.id: question for question in questions}
    total = len(responses)
    scenario_total = sum(
        1 for response in responses if question_by_id[response.question_id].type == QuestionType.SCENARIO
    )
    context_terms = _context_terms(brand)
    candidate_aliases = {candidate: _brand_aliases(candidate) for candidate in candidate_brands}
    voice_scores = {candidate: 0.0 for candidate in candidate_brands}
    mention_counts = {candidate: 0 for candidate in candidate_brands}
    scenario_mentions = {candidate: 0 for candidate in candidate_brands}
    top3_counts = {candidate: 0 for candidate in candidate_brands}
    rank_sums = {candidate: 0.0 for candidate in candidate_brands}
    position_scores = {candidate: 0.0 for candidate in candidate_brands}

    for response in responses:
        answer_lower = response.answer.lower()
        ranked_matches = _ranked_matches(answer_lower, candidate_aliases)
        has_context = any(term.lower() in answer_lower for term in context_terms)
        question = question_by_id[response.question_id]
        for rank, candidate, salience in ranked_matches:
            voice_scores[candidate] += salience
            mention_counts[candidate] += 1
            rank_sums[candidate] += rank
            top3_counts[candidate] += int(rank <= 3)
            position_scores[candidate] += salience if has_context else salience * 0.75
            if question.type == QuestionType.SCENARIO:
                scenario_mentions[candidate] += 1

    voice_total = sum(voice_scores.values()) or 1.0
    matrix: list[CompetitorMetric] = []
    for candidate in candidate_brands:
        occurrence_rate = mention_counts[candidate] / total if total else 0
        average_rank = rank_sums[candidate] / mention_counts[candidate] if mention_counts[candidate] else None
        voice_share = voice_scores[candidate] / voice_total
        top3_rate = top3_counts[candidate] / total if total else 0
        position_score = position_scores[candidate] / total if total else 0
        scenario_rate = scenario_mentions[candidate] / scenario_total if scenario_total else 0
        matrix.append(
            CompetitorMetric(
                brand=candidate,
                mention_rate=round(voice_share, 4),
                top3_rate=round(top3_rate, 4),
                industry_coverage=round(position_score, 4),
                scenario_coverage=round(scenario_rate, 4),
                citation_count=0,
                accuracy_rate=round(occurrence_rate, 4),
                voice_share=round(voice_share, 4),
                occurrence_rate=round(occurrence_rate, 4),
                average_rank=round(average_rank, 2) if average_rank is not None else None,
                effective_sample_count=total,
                scenario_sample_count=scenario_total,
            )
        )
    return sorted(matrix, key=lambda item: (item.voice_share, item.industry_coverage), reverse=True)


def _benchmark_questions(brand: BrandInput, candidate_brands: list[str]) -> list[Question]:
    industry = brand.industry or "相关行业"
    products = "、".join(brand.products[:4]) if brand.products else "核心产品"
    candidate_text = "、".join(candidate_brands)
    neutral_note = f"候选品牌池为：{candidate_text}。候选顺序不代表排名，请只根据行业认知排序，不要围绕任何单一品牌展开。"
    return [
        Question(text=f"如果只推荐 5 个中国{industry}代表品牌，你会列出哪些？请按推荐顺序给出。{neutral_note}", type=QuestionType.CATEGORY),
        Question(text=f"购买{products}时，优先考虑的 5 个品牌是什么？请不要列出超过 5 个。{neutral_note}", type=QuestionType.DECISION),
        Question(text=f"从质量、售后、智能化、性价比综合看，{industry}行业 Top5 品牌怎么排？{neutral_note}", type=QuestionType.COMPARISON),
        Question(text=f"家庭用户换新{products}，最值得进入短名单的 3-5 个品牌有哪些？{neutral_note}", type=QuestionType.SCENARIO),
        Question(text=f"只从智能生态和产品线完整度看，{industry}企业 Top5 推荐清单是什么？{neutral_note}", type=QuestionType.COMPARISON),
    ]


def _context_terms(brand: BrandInput) -> list[str]:
    terms = [brand.industry, *brand.products]
    generic_terms = ["家电", "空调", "冰箱", "洗衣机", "厨电", "电视", "智能家居", "售后", "质量"]
    return [term for term in [*terms, *generic_terms] if term]


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = item.strip()
        if normalized and normalized.lower() not in seen:
            result.append(normalized)
            seen.add(normalized.lower())
    return result


def _brand_aliases(brand: str) -> list[str]:
    base = brand.strip().lower()
    aliases = {base}
    suffixes = ["电器", "集团", "智家", "家电", "股份", "控股", "有限", "公司", "品牌"]
    simplified = base
    for suffix in suffixes:
        simplified = simplified.replace(suffix.lower(), "")
    simplified = simplified.strip()
    if simplified:
        aliases.add(simplified)
    if "（" in base:
        aliases.add(base.split("（", 1)[0].strip())
    if "(" in base:
        aliases.add(base.split("(", 1)[0].strip())
    return sorted((alias for alias in aliases if alias), key=len, reverse=True)


def _match_rank(answer_lower: str, aliases: list[str]) -> int | None:
    positions = [answer_lower.find(alias) for alias in aliases if alias in answer_lower]
    positions = [position for position in positions if position >= 0]
    if not positions:
        return None
    position = min(positions)
    if position < 120:
        return 1
    if position < 280:
        return 2
    if position < 520:
        return 3
    return 4


def _analysis_rank(analysis: BrandMentionAnalysis) -> int:
    if analysis.recommendation_position == "Top1":
        return 1
    if analysis.recommendation_position == "Top3":
        return 3
    if analysis.recommendation_position == "Top5":
        return 5
    return 6


def _ranked_matches(answer_lower: str, aliases_by_brand: dict[str, list[str]]) -> list[tuple[int, str, float]]:
    positions: list[tuple[int, str]] = []
    for brand, aliases in aliases_by_brand.items():
        brand_positions = [answer_lower.find(alias) for alias in aliases if alias in answer_lower]
        brand_positions = [position for position in brand_positions if position >= 0]
        if brand_positions:
            positions.append((min(brand_positions), brand))
    positions.sort(key=lambda item: item[0])
    return [(rank, brand, _rank_weight(rank)) for rank, (_position, brand) in enumerate(positions, start=1)]


def _rank_weight(rank: int) -> float:
    if rank == 1:
        return 1.0
    if rank == 2:
        return 0.82
    if rank == 3:
        return 0.66
    if rank == 4:
        return 0.5
    if rank == 5:
        return 0.36
    return 0.22


def _rank_to_score(rank: float | None) -> float:
    if rank is None:
        return 0.0
    return _rank_weight(max(1, round(rank)))

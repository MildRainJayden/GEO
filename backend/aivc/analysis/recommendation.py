from __future__ import annotations

from ..models import BrandInput, BrandMentionAnalysis, CompetitorMetric, ProviderResponse, Question, QuestionType
from ..providers.base import ProviderClient


def build_competitor_matrix(
    brand: BrandInput,
    questions: list[Question],
    responses: list[ProviderResponse],
    analyses: list[BrandMentionAnalysis],
) -> list[CompetitorMetric]:
    industry = brand.industry or ""
    question_by_id = {question.id: question for question in questions}
    response_by_id = {(response.provider, response.question_id): response for response in responses}
    matrix: list[CompetitorMetric] = []
    brands = [brand.brand_name, *brand.competitors]

    for candidate in brands:
        mention_hits = 0
        top3_hits = 0
        accuracy_hits = 0
        industry_hits = 0
        scenario_hits = 0
        citation_count = 0
        total = len(responses) or 1

        if candidate == brand.brand_name:
            for analysis in analyses:
                mention_hits += int(analysis.brand_mentioned)
                top3_hits += int(analysis.recommendation_position in {"Top1", "Top3"})
                accuracy_hits += int(analysis.description_correct)
                industry_hits += int(bool(analysis.industry_terms_covered))
                response = response_by_id.get((analysis.provider, analysis.question_id))
                if response:
                    citation_count += len(response.citations)
                    question = question_by_id[analysis.question_id]
                    scenario_hits += int(question.type == QuestionType.SCENARIO and analysis.brand_mentioned)
        else:
            candidate_lower = candidate.lower()
            for response in responses:
                contains = candidate_lower in response.answer.lower()
                mention_hits += int(contains)
                top3_hits += int(contains and ("Top1" in response.answer or "Top3" in response.answer))
                accuracy_hits += int(contains and (not industry or industry in response.answer))
                industry_hits += int(contains and (not industry or industry in response.answer))
                citation_count += sum(candidate_lower in c.title.lower() for c in response.citations)
                question = question_by_id[response.question_id]
                scenario_hits += int(question.type == QuestionType.SCENARIO and contains)

        scenario_total = sum(1 for response in responses if question_by_id[response.question_id].type == QuestionType.SCENARIO) or 1
        matrix.append(
            CompetitorMetric(
                brand=candidate,
                mention_rate=round(mention_hits / total, 4),
                top3_rate=round(top3_hits / total, 4),
                industry_coverage=round(industry_hits / total, 4),
                scenario_coverage=round(scenario_hits / scenario_total, 4),
                citation_count=citation_count,
                accuracy_rate=round(accuracy_hits / total, 4),
            )
        )
    return matrix


async def build_industry_benchmark_matrix(
    brand: BrandInput,
    providers: list[ProviderClient],
) -> list[CompetitorMetric]:
    """Compare brands on neutral industry questions, not target-brand questions."""
    candidate_brands = _dedupe([brand.brand_name, *brand.competitors])
    questions = _benchmark_questions(brand)
    responses = [
        await provider.query(question, brand)
        for question in questions
        for provider in providers
    ]
    total = len(responses) or 1
    scenario_total = sum(question.type == QuestionType.SCENARIO for question in questions) * max(len(providers), 1) or 1
    context_terms = _context_terms(brand)
    matrix: list[CompetitorMetric] = []

    for candidate in candidate_brands:
        candidate_aliases = _brand_aliases(candidate)
        mention_score = 0.0
        context_score = 0.0
        scenario_score = 0.0
        factual_score = 0.0
        for response in responses:
            answer_lower = response.answer.lower()
            salience = _salience(answer_lower, candidate_aliases)
            contains = salience > 0
            mention_score += salience
            has_context = any(term.lower() in answer_lower for term in context_terms)
            context_score += salience if contains and has_context else 0
            question = next(q for q in questions if q.id == response.question_id)
            scenario_score += salience if question.type == QuestionType.SCENARIO and contains else 0
            factual_score += salience if contains and has_context else 0

        matrix.append(
            CompetitorMetric(
                brand=candidate,
                mention_rate=round(mention_score / total, 4),
                top3_rate=0,
                industry_coverage=round(context_score / total, 4),
                scenario_coverage=round(scenario_score / scenario_total, 4),
                citation_count=0,
                accuracy_rate=round(factual_score / total, 4),
            )
        )
    return sorted(matrix, key=lambda item: (item.mention_rate, item.industry_coverage), reverse=True)


def _benchmark_questions(brand: BrandInput) -> list[Question]:
    industry = brand.industry or "相关行业"
    products = "、".join(brand.products[:4]) if brand.products else "核心产品"
    return [
        Question(text=f"如果只推荐 5 个中国{industry}代表品牌，你会列出哪些？请按推荐顺序给出。", type=QuestionType.CATEGORY),
        Question(text=f"购买{products}时，优先考虑的 5 个品牌是什么？请不要列出超过 5 个。", type=QuestionType.DECISION),
        Question(text=f"从质量、售后、智能化、性价比综合看，{industry}行业 Top5 品牌怎么排？", type=QuestionType.COMPARISON),
        Question(text=f"家庭用户换新{products}，最值得进入短名单的 3-5 个品牌有哪些？", type=QuestionType.SCENARIO),
        Question(text=f"只从智能生态和产品线完整度看，{industry}企业 Top5 推荐清单是什么？", type=QuestionType.COMPARISON),
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


def _salience(answer_lower: str, aliases: list[str]) -> float:
    positions = [answer_lower.find(alias) for alias in aliases if alias in answer_lower]
    positions = [position for position in positions if position >= 0]
    if not positions:
        return 0.0
    position = min(positions)
    if position < 120:
        return 1.0
    if position < 280:
        return 0.8
    if position < 520:
        return 0.6
    return 0.4

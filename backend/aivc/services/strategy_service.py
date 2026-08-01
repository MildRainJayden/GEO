from __future__ import annotations

import json
import re

from ..analysis.geo_optimizer import build_30_day_plan, find_content_gaps, generate_geo_suggestions
from ..models import (
    BrandInput,
    BrandMentionAnalysis,
    ContentGap,
    GeoSuggestion,
    ProviderResponse,
    Question,
    QuestionType,
    ScoreBreakdown,
    TaskItem,
)
from ..providers.base import ProviderClient


async def generate_personalized_strategy(
    brand: BrandInput,
    responses: list[ProviderResponse],
    analyses: list[BrandMentionAnalysis],
    score: ScoreBreakdown,
    providers: list[ProviderClient],
    web_evidence: list[str] | None = None,
) -> tuple[list[ContentGap], list[GeoSuggestion], list[TaskItem]]:
    strategist = _select_real_provider(providers)
    if not strategist:
        return _fallback_strategy(brand, analyses, score)

    prompt = _strategy_prompt(brand, responses, analyses, score, web_evidence or [])
    try:
        response = await strategist.query(Question(text=prompt, type=QuestionType.DECISION), brand)
        payload = _parse_json_object(response.answer)
        if not payload:
            payload = await _repair_strategy_json(strategist, response.answer, brand)
        if not payload:
            return _fallback_strategy(brand, analyses, score)
        return _strategy_from_payload(brand, payload)
    except Exception:
        return _fallback_strategy(brand, analyses, score)


def _select_real_provider(providers: list[ProviderClient]) -> ProviderClient | None:
    for provider in providers:
        if provider.__class__.__name__ != "SimulatedProvider":
            return provider
    return None


def _strategy_prompt(
    brand: BrandInput,
    responses: list[ProviderResponse],
    analyses: list[BrandMentionAnalysis],
    score: ScoreBreakdown,
    web_evidence: list[str],
) -> str:
    weak_answers = []
    analysis_by_key = {(a.provider, a.question_id): a for a in analyses}
    for response in responses[:20]:
        analysis = analysis_by_key.get((response.provider, response.question_id))
        if analysis and (not analysis.brand_mentioned or not analysis.description_correct):
            weak_answers.append(
                {
                    "provider": response.provider,
                    "question": response.question,
                    "answer_excerpt": response.answer[:280],
                    "mentioned": analysis.brand_mentioned,
                    "correct": analysis.description_correct,
                }
            )
        if len(weak_answers) >= 8:
            break

    return (
        "你是 GEO（生成式引擎优化）策略顾问。请基于品牌资料和本次 AI 回答表现，输出高度个性化的 JSON，"
        "不要输出 Markdown 代码块，不要解释 JSON 之外的内容。\n"
        "JSON schema:\n"
        "{\n"
        '  "content_gaps": [{"question":"", "reason":"", "recommendation_type":"FAQ|博客|案例|产品页面|对比文章", "priority":"高|中|低"}],\n'
        '  "geo_suggestions": [{"category":"", "title":"", "action":"", "copyable_content":"", "expected_impact": 0.0}],\n'
        '  "tasks": [{"day":1, "title":"", "channel":"", "expected_score_lift":0.5, "prompt_template":""}]\n'
        "}\n"
        "要求：content_gaps 给 5 条；geo_suggestions 给 5 条，必须包含可复制内容；tasks 给 30 天，"
        "每一天都要贴合该品牌、产品、竞品和渠道，不要使用泛化模板。prompt_template 要能直接复制给 AI 生成内容。\n\n"
        f"品牌：{brand.brand_name}\n"
        f"官网：{brand.website or '未提供'}\n"
        f"行业：{brand.industry}\n"
        f"产品：{brand.product_text}\n"
        f"竞品：{'、'.join(brand.competitors)}\n"
        f"总分：{score.total_score}\n"
        f"网页证据：{json.dumps(web_evidence[:6], ensure_ascii=False)}\n"
        f"平台表现：{[p.model_dump() for p in score.platform_scores]}\n"
        f"弱回答样本：{json.dumps(weak_answers, ensure_ascii=False)}"
    )


def _strategy_from_payload(
    brand: BrandInput,
    payload: dict,
) -> tuple[list[ContentGap], list[GeoSuggestion], list[TaskItem]]:
    gap_items = _as_list(_first_value(payload, ["content_gaps", "contentGaps", "gaps", "内容缺口"]))
    suggestion_items = _as_list(_first_value(payload, ["geo_suggestions", "geoSuggestions", "suggestions", "GEO优化建议", "geo优化建议"]))
    task_items = _as_list(_first_value(payload, ["tasks", "task_plan", "thirty_day_plan", "30_day_plan", "30天任务", "任务计划"]))

    gaps = [
        ContentGap(
            question=str(_first_value(item, ["question", "问题", "query"]) or ""),
            reason=str(_first_value(item, ["reason", "原因", "gap_reason"]) or ""),
            recommendation_type=_pick(_first_value(item, ["recommendation_type", "建议类型", "type"]), ["FAQ", "博客", "案例", "产品页面", "对比文章"], "FAQ"),
            priority=_pick(_first_value(item, ["priority", "优先级"]), ["高", "中", "低"], "中"),
        )
        for item in gap_items
        if _first_value(item, ["question", "问题", "query"])
    ][:8]

    suggestions = [
        GeoSuggestion(
            category=str(_first_value(item, ["category", "类别"]) or "GEO 优化"),
            title=str(_first_value(item, ["title", "标题"]) or f"{brand.brand_name} GEO 优化"),
            action=str(_first_value(item, ["action", "动作", "行动", "建议"]) or ""),
            copyable_content=str(_first_value(item, ["copyable_content", "可复制内容", "content", "内容"]) or ""),
            expected_impact=float(_first_value(item, ["expected_impact", "预计影响", "impact"]) or 3.0),
        )
        for item in suggestion_items
        if _first_value(item, ["title", "标题"])
    ][:8]

    tasks = [
        TaskItem(
            day=int(_first_value(item, ["day", "Day", "日期", "天数"]) or index + 1),
            title=str(_first_value(item, ["title", "标题", "任务"]) or f"{brand.brand_name} GEO 任务"),
            channel=str(_first_value(item, ["channel", "渠道", "平台"]) or "官网"),
            expected_score_lift=float(_first_value(item, ["expected_score_lift", "预计提分", "score_lift"]) or 0.5),
            prompt_template=str(_first_value(item, ["prompt_template", "提示词模板", "prompt"]) or ""),
        )
        for index, item in enumerate(task_items[:30])
    ]

    if len(gaps) < 3 or len(suggestions) < 3:
        return _fallback_strategy(brand, [], None)
    if not tasks:
        tasks = build_30_day_plan(brand)
    while len(tasks) < 30:
        base = tasks[len(tasks) % len(tasks)]
        tasks.append(
            base.model_copy(
                update={
                    "day": len(tasks) + 1,
                    "title": f"{brand.brand_name} 延展任务：{base.title}",
                }
            )
        )
    return gaps, suggestions, tasks[:30]


async def _repair_strategy_json(strategist: ProviderClient, raw_answer: str, brand: BrandInput) -> dict | None:
    repair_prompt = (
        "请把下面内容转换成严格 JSON，只输出 JSON，不要 Markdown。"
        "必须包含 content_gaps、geo_suggestions、tasks 三个数组；字段使用英文 snake_case。"
        "tasks 至少给 10 条。\n\n"
        f"品牌：{brand.brand_name}\n"
        f"原始内容：{raw_answer[:6000]}"
    )
    try:
        response = await strategist.query(Question(text=repair_prompt, type=QuestionType.DECISION), brand)
    except Exception:
        return None
    return _parse_json_object(response.answer)


def _fallback_strategy(
    brand: BrandInput,
    analyses: list[BrandMentionAnalysis],
    score: ScoreBreakdown | None,
) -> tuple[list[ContentGap], list[GeoSuggestion], list[TaskItem]]:
    return find_content_gaps(brand, analyses), generate_geo_suggestions(brand, score), build_30_day_plan(brand)


def _parse_json_object(text: str) -> dict | None:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _as_list(value: object) -> list[dict]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _pick(value: object, allowed: list[str], default: str) -> str:
    text = str(value or "")
    return text if text in allowed else default


def _first_value(payload: dict, keys: list[str]) -> object:
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    return None

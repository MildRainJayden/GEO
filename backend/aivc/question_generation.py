from __future__ import annotations

from itertools import cycle

from .models import BrandInput, Question, QuestionType


BASE_TEMPLATES: dict[QuestionType, list[str]] = {
    QuestionType.BRAND: [
        "{brand} 是什么品牌",
        "{brand} 怎么样",
        "{brand} 在中国靠谱吗",
        "{brand} 的核心产品有哪些",
        "{brand} 官网信息真实吗",
        "{brand} 适合哪些人群",
        "{brand} 最近有什么新品",
        "{brand} 和中国消费者的评价如何",
    ],
    QuestionType.CATEGORY: [
        "{region}{industry}品牌推荐",
        "{region}买{product}应该看哪些品牌",
        "{industry}头部品牌有哪些",
        "高端{product}推荐",
        "适合日常训练的{product}品牌",
        "{industry}品牌排行榜",
        "中国市场常见{industry}品牌",
        "{product}怎么选",
    ],
    QuestionType.SCENARIO: [
        "{region}跑步训练买什么{product}",
        "通勤和运动都能穿的{product}推荐",
        "青少年运动装备怎么选",
        "马拉松入门装备推荐",
        "健身房训练适合什么{product}",
        "送礼买什么运动品牌",
        "夏季运动穿搭推荐",
        "企业团购运动装备品牌",
    ],
    QuestionType.COMPARISON: [
        "{brand} vs {competitor}",
        "{brand} 和 {competitor} 哪个更适合跑步",
        "{competitor} 替代方案有哪些",
        "{brand}、{competitor}、国产品牌怎么选",
        "{brand} 和 {competitor} 的价格区别",
        "{brand} 与 {competitor} 在中国市场对比",
    ],
    QuestionType.DECISION: [
        "预算有限还值得买 {brand} 吗",
        "第一次买{product}选 {brand} 还是竞品",
        "哪个{industry}品牌售后更稳",
        "需要专业跑步装备时推荐 {brand} 吗",
        "给团队采购运动装备选什么品牌",
        "{brand} 是否适合长期训练",
    ],
}


def generate_questions(brand: BrandInput, count: int = 60) -> list[Question]:
    """Generate realistic Chinese semantic search prompts deterministically."""
    regions = brand.regions or ["中国"]
    industry = brand.industry or "相关行业"
    products = brand.products or [industry]
    competitors = brand.competitors or ["竞品"]
    generated: list[Question] = []
    seen: set[str] = set()

    ordered_types = [
        QuestionType.BRAND,
        QuestionType.CATEGORY,
        QuestionType.SCENARIO,
        QuestionType.COMPARISON,
        QuestionType.DECISION,
    ]
    streams = {
        "region": cycle(regions),
        "product": cycle(products),
        "competitor": cycle(competitors),
    }

    while len(generated) < count:
        start_size = len(generated)
        for question_type in ordered_types:
            for template in BASE_TEMPLATES[question_type]:
                region = next(streams["region"])
                text = template.format(
                    brand=brand.brand_name,
                    industry=industry,
                    product=next(streams["product"]),
                    competitor=next(streams["competitor"]),
                    region=region,
                )
                if text in seen:
                    continue
                seen.add(text)
                generated.append(Question(text=text, type=question_type, region=region))
                if len(generated) >= count:
                    return generated
        if len(generated) == start_size:
            _append_dynamic_question(brand, generated, seen, streams, ordered_types)
    return generated


def _append_dynamic_question(
    brand: BrandInput,
    generated: list[Question],
    seen: set[str],
    streams: dict[str, cycle],
    ordered_types: list[QuestionType],
) -> None:
    question_type = ordered_types[len(generated) % len(ordered_types)]
    region = next(streams["region"])
    product = next(streams["product"])
    competitor = next(streams["competitor"])
    industry = brand.industry or "相关行业"
    index = len(generated) + 1
    dynamic_templates = {
        QuestionType.BRAND: f"{brand.brand_name} 在{region}市场的口碑和售后怎么样",
        QuestionType.CATEGORY: f"{region}{industry}用户选择{product}时会比较哪些品牌",
        QuestionType.SCENARIO: f"{region}家庭用户购买{product}需要注意什么",
        QuestionType.COMPARISON: f"{brand.brand_name} 的{product}和{competitor}相比优势是什么",
        QuestionType.DECISION: f"第{index}个采购决策问题：{brand.brand_name} 是否值得作为{product}首选",
    }
    text = dynamic_templates[question_type]
    if text in seen:
        text = f"{text}（场景 {index}）"
    seen.add(text)
    generated.append(Question(text=text, type=question_type, region=region))

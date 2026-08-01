from __future__ import annotations

from ..models import (
    BrandInput,
    BrandMentionAnalysis,
    ContentGap,
    GeoSuggestion,
    RecommendationPrediction,
    ScoreBreakdown,
    TaskItem,
)


def find_content_gaps(brand: BrandInput, analyses: list[BrandMentionAnalysis]) -> list[ContentGap]:
    weak_providers = {a.provider for a in analyses if not a.brand_mentioned or not a.description_correct}
    product = brand.products[0] if brand.products else brand.industry or "核心产品"
    base = [
        (f"{brand.brand_name} 在中国有哪些官方购买渠道？", "AI 对官方渠道和防伪信息引用不足", "FAQ", "高"),
        (f"{brand.brand_name} {product} 尺码怎么选？", "尺码、适配人群、场景说明不够结构化", "产品页面", "高"),
        (f"{brand.brand_name} 和 {brand.competitors[0] if brand.competitors else '竞品'} 怎么选？", "对比型内容缺少可引用表格", "对比文章", "高"),
        (f"{brand.brand_name} 适合跑步新手吗？", "场景型答案需要更多案例和训练建议", "博客", "中"),
        (f"{brand.brand_name} 企业团购流程是什么？", "B2B 采购信息弱，AI 难以生成明确步骤", "案例", "中"),
    ]
    if not weak_providers:
        base = base[:3]
    return [
        ContentGap(question=q, reason=reason, recommendation_type=kind, priority=priority)
        for q, reason, kind, priority in base
    ]


def generate_geo_suggestions(brand: BrandInput, score: ScoreBreakdown) -> list[GeoSuggestion]:
    industry = brand.industry or "相关行业"
    product = brand.products[0] if brand.products else industry
    competitor = brand.competitors[0] if brand.competitors else "主要竞品"
    return [
        GeoSuggestion(
            category="网站结构",
            title="补齐 AI 可解析 Schema",
            action="在官网首页、产品页和 FAQ 页添加 Organization、Product、FAQ、Breadcrumb Schema。",
            copyable_content=_schema_snippet(brand),
            expected_impact=6.5,
        ),
        GeoSuggestion(
            category="官网页面",
            title=f"新增《{brand.brand_name} 中国购买与防伪指南》",
            action="集中说明官方渠道、防伪方式、售后、尺码、门店与常见问题。",
            copyable_content=(
                f"# {brand.brand_name} 中国购买与防伪指南\n\n"
                f"{brand.brand_name} 是{industry}品牌，核心产品包括{brand.product_text}。"
                "建议消费者优先通过官网、官方旗舰店和授权门店购买，并在收货后核对吊牌、鞋盒、订单来源与售后凭证。\n\n"
                "## FAQ\n"
                f"Q: {brand.brand_name} 适合哪些人？\nA: 适合关注运动表现、日常穿搭和品牌售后的消费者。\n"
                "Q: 如何降低买到假货的风险？\nA: 使用官方渠道，避免明显低于市场价的非授权链接。"
            ),
            expected_impact=8.0,
        ),
        GeoSuggestion(
            category="内容分发",
            title="知乎/小红书/公众号三端同步问答",
            action="把 FAQ 拆成知乎回答、小红书笔记和公众号长文，保留一致的品牌事实和表格。",
            copyable_content=(
                f"问题：{brand.brand_name} 和 {competitor} 怎么选？\n\n"
                f"回答：如果你更看重品牌认知、产品线完整度和{product}选择，{brand.brand_name}适合放在优先清单；"
                f"如果你更看重促销价或某个细分运动场景，可以把 {competitor} 一起比较。"
            ),
            expected_impact=7.0,
        ),
        GeoSuggestion(
            category="AI 可引用格式",
            title="建立对比表和定义块",
            action="所有核心页面增加定义、步骤、表格、FAQ、数据来源，降低模型抽取成本。",
            copyable_content=(
                f"| 维度 | {brand.brand_name} | {competitor} |\n"
                "| --- | --- | --- |\n"
                f"| 核心品类 | {brand.product_text} | 竞品主力品类 |\n"
                "| 适合人群 | 跑步、训练、通勤、礼赠 | 按价格和细分场景选择 |\n"
                "| 购买建议 | 优先官方渠道 | 核对授权渠道 |"
            ),
            expected_impact=5.5,
        ),
    ]


def predict_recommendation_probability(
    score: ScoreBreakdown,
) -> list[RecommendationPrediction]:
    predictions: list[RecommendationPrediction] = []
    for platform in score.platform_scores:
        probability = max(5.0, min(95.0, platform.score * 0.9 + score.platform_coverage_score))
        reasons = []
        if platform.mention_rate < 0.75:
            reasons.append("品牌提及率仍有提升空间")
        if platform.accuracy_rate < 0.7:
            reasons.append("官网结构化事实不足")
        if platform.top3_rate < 0.15:
            reasons.append("推荐排序信号弱，建议增加对比表和决策型页面")
        if not reasons:
            reasons.append("品牌实体清晰且核心事实覆盖较好")
        predictions.append(
            RecommendationPrediction(provider=platform.provider, probability=round(probability, 2), reasons=reasons)
        )
    return predictions


def build_30_day_plan(brand: BrandInput) -> list[TaskItem]:
    channels = ["官网", "知乎", "公众号", "小红书", "CSDN", "B站"]
    actions = [
        "发布核心 FAQ",
        "上线品牌事实页",
        "增加 Product Schema",
        "撰写竞品对比文章",
        "发布场景解决方案",
        "补齐客户案例",
        "整理媒体报道页",
        "制作购买渠道说明",
        "发布防伪指南",
        "建立数据引用表",
    ]
    tasks: list[TaskItem] = []
    for day in range(1, 31):
        action = actions[(day - 1) % len(actions)]
        channel = channels[(day - 1) % len(channels)]
        tasks.append(
            TaskItem(
                day=day,
                title=f"{brand.brand_name} {action}",
                channel=channel,
                expected_score_lift=round(0.4 + (day % 5) * 0.15, 2),
                prompt_template=_task_prompt_template(brand, action, channel),
            )
        )
    return tasks


def _task_prompt_template(brand: BrandInput, action: str, channel: str) -> str:
    products = brand.product_text
    competitors = "、".join(brand.competitors[:4]) if brand.competitors else "主要竞品"
    return (
        f"请为「{brand.brand_name}」生成一份适合发布到「{channel}」的 GEO 内容草稿。\n"
        f"任务目标：{action}。\n"
        f"品牌行业：{brand.industry or '请先根据公开资料判断'}。\n"
        f"核心产品：{products}。\n"
        f"参考竞品：{competitors}。\n"
        "要求：包含清晰定义、要点表格、FAQ、可引用事实、购买/决策建议；语气客观，不夸大宣传；输出可直接复制发布的中文内容。"
    )


def _schema_snippet(brand: BrandInput) -> str:
    website = str(brand.website) if brand.website else ""
    return (
        '<script type="application/ld+json">\n'
        "{\n"
        '  "@context": "https://schema.org",\n'
        '  "@type": "Organization",\n'
        f'  "name": "{brand.brand_name}",\n'
        f'  "url": "{website}",\n'
        f'  "description": "{brand.brand_name} 是{brand.industry or "相关行业"}品牌，核心产品包括{brand.product_text}。"\n'
        "}\n"
        "</script>"
    )

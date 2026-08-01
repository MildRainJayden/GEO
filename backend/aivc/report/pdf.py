from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..models import AuditResult, BrandMentionAnalysis, CompetitorMetric
from .citation_insights import build_citation_insights


PALETTE = ["#0f766e", "#2563eb", "#ca8a04", "#7c3aed", "#dc2626", "#0891b2", "#9333ea", "#64748b"]


def write_pdf_report(result: AuditResult, output_path: str | Path) -> Path:
    font_name = "STSong-Light"
    try:
        pdfmetrics.registerFont(UnicodeCIDFont(font_name))
    except Exception:
        font_name = "Helvetica"

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"{result.input.brand_name} AI Visibility Report",
    )
    styles = _styles(font_name)
    story: list = []

    story.append(Paragraph(f"{result.input.brand_name} AI 搜索可见度报告", styles["TitleCN"]))
    story.append(Paragraph(f"行业：{result.input.industry or '自动调研'}", styles["BodyCN"]))
    story.append(Paragraph(f"官网：{result.input.website or '未提供'}", styles["BodyCN"]))
    story.append(Paragraph(f"总体得分：{result.score.total_score}", styles["Score"]))
    story.append(Spacer(1, 8))

    story.append(Paragraph("报告总结", styles["HeadingCN"]))
    story.append(Paragraph(_summary_text(result), styles["NoteCN"]))

    story.append(Paragraph("数据图览", styles["HeadingCN"]))
    story.append(
        Table(
            [[_score_pie(result), _bar_drawing([(p.provider, p.score) for p in result.score.platform_scores], "平台得分", 84 * mm, 48 * mm)]],
            colWidths=[76 * mm, 88 * mm],
        )
    )
    story.append(Spacer(1, 6))

    story.append(Paragraph("核心评分", styles["HeadingCN"]))
    story.append(_table([
        ["指标", "得分", "说明"],
        ["品牌提及", f"{result.score.mention_rate_score}/40", "回答中是否稳定出现品牌实体。"],
        ["准确率", f"{result.score.accuracy_score}/30", "回答是否覆盖正确行业与产品事实。"],
        ["行业/产品覆盖", f"{result.score.industry_coverage_score}/20", "品牌相关产品词是否被覆盖。"],
        ["平台覆盖", f"{result.score.platform_coverage_score}/10", "成功测评的平台中是否均有品牌曝光。"],
        ["竞争声量", f"{result.score.competitive_voice_score}/100", "品牌在行业基准对比中的相对声量、出现率和靠前度。"],
    ], [42 * mm, 28 * mm, 94 * mm], styles))
    story.append(Paragraph("说明：总分由品牌自身可见度和行业竞争声量共同组成。自身问题回答得好但行业对比中出现少，总分会被竞争声量拉低。", styles["NoteCN"]))

    story.append(Paragraph("平台表现", styles["HeadingCN"]))
    story.append(Paragraph("说明：平台得分用于观察不同 AI 引擎对品牌的熟悉度和回答稳定性；多模型总分会综合所有成功返回的平台结果。", styles["NoteCN"]))
    platform_data = [["平台", "评分", "提及率", "准确率", "中文解释"]]
    for p in result.score.platform_scores:
        platform_data.append([p.provider, p.score, f"{p.mention_rate:.0%}", f"{p.accuracy_rate:.0%}", p.explanation])
    story.append(_table(platform_data, [24 * mm, 20 * mm, 22 * mm, 22 * mm, 76 * mm], styles))

    story.append(Paragraph("AI 声量份额", styles["HeadingCN"]))
    story.append(Paragraph("说明：AI 声量份额表示在同一行业的中立推荐与对比问题中，AI 更常把哪些品牌放到靠前位置。它不是销量或市场份额，而是 AI 回答里的被看见程度。", styles["NoteCN"]))
    story.append(
        Table(
            [[_voice_pie(result.competitors[:8]), Paragraph(_voice_explanation(result), styles["NoteCN"])]],
            colWidths=[78 * mm, 86 * mm],
        )
    )
    story.append(Spacer(1, 6))
    competitor_data = [["品牌", "AI声量", "出现率", "平均排名", "Top3率", "场景率", "样本"]]
    for c in result.competitors:
        competitor_data.append(_competitor_row(c))
    story.append(_table(competitor_data, [34 * mm, 22 * mm, 22 * mm, 22 * mm, 20 * mm, 20 * mm, 24 * mm], styles))

    story.append(Paragraph("引用来源", styles["HeadingCN"]))
    story.append(Paragraph("查看大语言模型在回答本次问题时引用、写出或明确提到的来源。这里统计引文类别、引文页面类型、被引最多的域名和网址，帮助判断 AI 更信任哪些内容入口。", styles["NoteCN"]))
    story.extend(_citation_story(result, styles))

    story.append(PageBreak())
    story.append(Paragraph("内容缺口", styles["HeadingCN"]))
    story.append(Paragraph("说明：内容缺口由本次 AI 回答中暴露的弱项、竞品上下文和个性化分析生成，用于指导官网、FAQ、对比页、案例页等内容建设。", styles["NoteCN"]))
    gap_data = [["优先级", "问题", "建议类型", "原因"]]
    for gap in result.content_gaps:
        gap_data.append([gap.priority, gap.question, gap.recommendation_type, gap.reason])
    story.append(_table(gap_data, [18 * mm, 62 * mm, 24 * mm, 60 * mm], styles))

    story.append(Paragraph("GEO 优化建议", styles["HeadingCN"]))
    story.append(Paragraph("说明：建议优先补充 AI 容易摘取和引用的内容，例如清晰结论、参数表、FAQ、真实案例、竞品对比和权威来源。", styles["NoteCN"]))
    story.append(Paragraph("不同 AI 平台的优化重点", styles["HeadingCN"]))
    story.append(_table(_model_geo_rows(result), [26 * mm, 56 * mm, 82 * mm], styles, font_size=7))
    suggestion_data = [["类别", "标题", "动作"]]
    for suggestion in result.geo_suggestions:
        suggestion_data.append([suggestion.category, suggestion.title, suggestion.action])
    story.append(_table(suggestion_data, [28 * mm, 50 * mm, 86 * mm], styles))

    story.append(PageBreak())
    story.append(Paragraph("30 天任务与提示词模板", styles["HeadingCN"]))
    task_data = [["日期", "任务", "渠道", "提分", "提示词模板"]]
    for task in result.tasks:
        task_data.append([f"Day {task.day}", task.title, task.channel, task.expected_score_lift, task.prompt_template])
    story.append(_table(task_data, [16 * mm, 36 * mm, 18 * mm, 16 * mm, 78 * mm], styles, font_size=7))

    doc.build(story, onFirstPage=_footer(font_name), onLaterPages=_footer(font_name))
    return path


def _styles(font_name: str) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "TitleCN": ParagraphStyle("TitleCN", parent=base["Title"], fontName=font_name, fontSize=22, leading=28, spaceAfter=8),
        "HeadingCN": ParagraphStyle("HeadingCN", parent=base["Heading2"], fontName=font_name, fontSize=14, leading=18, spaceBefore=12, spaceAfter=8),
        "BodyCN": ParagraphStyle("BodyCN", parent=base["BodyText"], fontName=font_name, fontSize=9, leading=13),
        "NoteCN": ParagraphStyle("NoteCN", parent=base["BodyText"], fontName=font_name, fontSize=8, leading=12, textColor=colors.HexColor("#425466"), spaceAfter=6),
        "CellCN": ParagraphStyle("CellCN", parent=base["BodyText"], fontName=font_name, fontSize=8, leading=11),
        "Score": ParagraphStyle("Score", parent=base["Title"], fontName=font_name, fontSize=32, leading=38, textColor=colors.HexColor("#0f766e")),
    }


def _table(data: list[list[object]], widths: list[float], styles: dict[str, ParagraphStyle], font_size: int = 8) -> Table:
    wrapped = [
        [
            cell if row_index == 0 and isinstance(cell, (int, float)) else Paragraph(escape(str(cell)), styles["CellCN"])
            for cell in row
        ]
        for row_index, row in enumerate(data)
    ]
    table = Table(wrapped, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#edf3f8")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d7dee8")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTNAME", (0, 0), (-1, -1), styles["CellCN"].fontName),
                ("FONTSIZE", (0, 0), (-1, -1), font_size),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _footer(font_name: str):
    def draw(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont(font_name, 8)
        canvas.setFillColor(colors.HexColor("#667085"))
        canvas.drawRightString(A4[0] - 16 * mm, 9 * mm, f"AI Visibility China - Page {doc.page}")
        canvas.restoreState()

    return draw


def _citation_story(result: AuditResult, styles: dict[str, ParagraphStyle]) -> list:
    insights = build_citation_insights(result)
    story: list = []
    story.append(
        _table(
            [
                ["指标", "数值", "说明"],
                ["品牌官网引用占比", f"{insights.brand_citation_share:.0%}", "模型引用中指向品牌官网域名的比例。"],
                ["唯一域名", insights.unique_domains, "被引用来源覆盖的不同域名数量。"],
                ["来源出现次数", insights.total, "模型返回、写出或明确提到的可识别来源出现次数。"],
            ],
            [42 * mm, 28 * mm, 94 * mm],
            styles,
        )
    )
    if insights.total == 0:
        story.append(Paragraph("本轮模型未返回可解析的引用链接。若要看到更完整的引用来源，可接入支持联网引用的模型，或补充公开搜索数据源。", styles["NoteCN"]))
        return story
    story.append(
        Table(
            [
                [
                    _count_pie(insights.categories, "引文类别", 78 * mm, 48 * mm),
                    _count_pie(insights.page_types, "引文页面类型", 86 * mm, 48 * mm),
                ]
            ],
            colWidths=[78 * mm, 86 * mm],
        )
    )
    story.append(Spacer(1, 6))
    story.append(_table(_count_rows("域名", insights.domains[:8]), [112 * mm, 52 * mm], styles))
    story.append(_table(_count_rows("网址", _short_count_urls(insights.urls[:8])), [132 * mm, 32 * mm], styles, font_size=7))
    provider_rows: list[list[object]] = [["模型", "来源出现次数", "唯一域名", "官网占比", "主要被引域名"]]
    for item in insights.providers:
        provider_rows.append([
            item.provider,
            item.total,
            item.unique_domains,
            f"{item.brand_citation_share:.0%}",
            "、".join(name for name, _count in item.domains[:3]) or "暂无",
        ])
    story.append(Paragraph("各模型引用来源表现", styles["HeadingCN"]))
    story.append(_table(provider_rows, [24 * mm, 28 * mm, 24 * mm, 24 * mm, 64 * mm], styles, font_size=7))
    return story


def _count_rows(label: str, items: list[tuple[str, int]]) -> list[list[object]]:
    rows: list[list[object]] = [[label, "引用次数"]]
    rows.extend([[name, count] for name, count in items])
    return rows


def _short_count_urls(items: list[tuple[str, int]]) -> list[tuple[str, int]]:
    return [(url if len(url) <= 90 else f"{url[:87]}...", count) for url, count in items]


def _count_pie(items: list[tuple[str, int]], title: str, width: float, height: float) -> Drawing:
    labels = [
        (label, count, PALETTE[index % len(PALETTE)])
        for index, (label, count) in enumerate(items[:6])
    ]
    return _pie_drawing(labels, title, width, height)


def _competitor_row(metric: CompetitorMetric) -> list[object]:
    avg_rank = f"{metric.average_rank:.2f}" if metric.average_rank is not None else "-"
    return [
        metric.brand,
        f"{(metric.voice_share or metric.mention_rate):.0%}",
        f"{(metric.occurrence_rate or metric.accuracy_rate):.0%}",
        avg_rank,
        f"{metric.top3_rate:.0%}",
        f"{metric.scenario_coverage:.0%}",
        metric.effective_sample_count or "-",
    ]


def _model_geo_rows(result: AuditResult) -> list[list[object]]:
    analysis_by_provider: dict[str, list[BrandMentionAnalysis]] = defaultdict(list)
    for analysis in result.analyses:
        analysis_by_provider[analysis.provider].append(analysis)
    rows: list[list[object]] = [["平台", "本轮观察", "优化重点"]]
    for platform in result.score.platform_scores:
        analyses = analysis_by_provider.get(platform.provider, [])
        weak_count = sum(
            1
            for analysis in analyses
            if not analysis.brand_mentioned or not analysis.description_correct or not analysis.industry_terms_covered
        )
        issue = _model_issue(platform.mention_rate, platform.accuracy_rate, weak_count, len(analyses))
        rows.append([platform.provider, issue, _model_action(platform.provider, issue)])
    return rows


def _model_issue(mention_rate: float, accuracy_rate: float, weak_count: int, total: int) -> str:
    if mention_rate < 0.6:
        return "品牌在回答中出现不够稳定"
    if accuracy_rate < 0.7:
        return "产品和品牌事实需要更清晰"
    if total and weak_count / total > 0.3:
        return "部分场景问题下表达不够完整"
    return "表现相对稳定，可继续扩大覆盖"


def _model_action(provider: str, issue: str) -> str:
    if issue == "品牌在回答中出现不够稳定":
        return f"优先建设适合 {provider} 抽取的品牌介绍、核心品类页、购买场景页和竞品对比页。"
    if issue == "产品和品牌事实需要更清晰":
        return f"补充参数表、型号清单、售后政策、适用人群和高频 FAQ，让 {provider} 更容易形成准确回答。"
    if issue == "部分场景问题下表达不够完整":
        return f"围绕 {provider} 容易触发的场景问题补案例、问答和对比结论，提升长尾问题中的推荐稳定性。"
    return f"维持 {provider} 已有表现，继续扩展行业场景、竞品比较和权威背书内容。"


def _summary_text(result: AuditResult) -> str:
    brand = result.input.brand_name
    leader = result.competitors[0].brand if result.competitors else "暂无竞品数据"
    brand_metric = next((item for item in result.competitors if item.brand == brand), None)
    share = f"{(brand_metric.voice_share or brand_metric.mention_rate):.0%}" if brand_metric else "暂无"
    return f"{brand} 本轮 AI 可见度总分为 {result.score.total_score}。行业对比中，当前 AI 声量领先品牌为 {leader}；{brand} 的 AI 声量份额为 {share}。建议优先提升行业推荐问题中的出现率和靠前度，并补充可被 AI 摘取的产品事实、场景问答与竞品对比内容。"


def _voice_explanation(result: AuditResult) -> str:
    brand = result.input.brand_name
    leader = result.competitors[0] if result.competitors else None
    own = next((item for item in result.competitors if item.brand == brand), None)
    if not leader or not own:
        return "本轮有效行业对比样本不足，建议扩大问题数量或接入更多 AI 平台后再观察声量变化。"
    if own.brand == leader.brand:
        return f"{brand} 在本轮行业对比中处于领先位置，说明 AI 更容易把它作为同类品牌的优先候选。但仍需关注出现率和平均排名，避免只在少数问题里集中出现。"
    gap = max(leader.voice_share - own.voice_share, 0)
    return f"{brand} 当前声量低于 {leader.brand}，差距约 {gap:.0%}。这通常意味着 AI 在回答同类推荐时更先想到竞品，后续应补强行业场景内容、对比页和权威来源。"


def _score_pie(result: AuditResult) -> Drawing:
    values = [
        result.score.mention_rate_score,
        result.score.accuracy_score,
        result.score.industry_coverage_score,
        result.score.platform_coverage_score,
    ]
    labels = [
        ("品牌提及", values[0], PALETTE[0]),
        ("准确率", values[1], PALETTE[1]),
        ("行业覆盖", values[2], PALETTE[2]),
        ("平台覆盖", values[3], PALETTE[3]),
    ]
    return _pie_drawing(labels, "评分构成", 70 * mm, 48 * mm)


def _voice_pie(metrics: list[CompetitorMetric]) -> Drawing:
    labels = [
        (metric.brand, (metric.voice_share or metric.mention_rate) * 100, PALETTE[index % len(PALETTE)])
        for index, metric in enumerate(metrics[:6])
    ]
    return _pie_drawing(labels, "AI 声量份额", 76 * mm, 54 * mm)


def _pie_drawing(items: list[tuple[str, float, str]], title: str, width: float, height: float) -> Drawing:
    drawing = Drawing(width, height)
    drawing.add(String(0, height - 8, title, fontName="STSong-Light", fontSize=8, fillColor=colors.HexColor("#1d2733")))
    if not items:
        drawing.add(String(0, height - 20, "暂无数据", fontName="STSong-Light", fontSize=7, fillColor=colors.HexColor("#667085")))
        return drawing
    pie = Pie()
    pie.x = 0
    pie.y = 6
    pie.width = 34 * mm
    pie.height = 34 * mm
    pie.data = [max(value, 0.01) for _, value, _ in items]
    for index, (_, _, color) in enumerate(items):
        pie.slices[index].fillColor = colors.HexColor(color)
        pie.slices[index].strokeColor = colors.white
    drawing.add(pie)
    for index, (label, value, color) in enumerate(items[:6]):
        y = height - 20 - index * 7 * mm
        drawing.add(Rect(40 * mm, y - 2, 4 * mm, 4 * mm, fillColor=colors.HexColor(color), strokeColor=None))
        drawing.add(String(46 * mm, y - 1, f"{label[:8]} {value:.0f}", fontName="STSong-Light", fontSize=6.5, fillColor=colors.HexColor("#1d2733")))
    return drawing


def _count_bar_drawing(items: list[tuple[str, int]], title: str, width: float, height: float) -> Drawing:
    drawing = Drawing(width, height)
    drawing.add(String(0, height - 8, title, fontName="STSong-Light", fontSize=8, fillColor=colors.HexColor("#1d2733")))
    if not items:
        drawing.add(String(0, height - 20, "暂无数据", fontName="STSong-Light", fontSize=7, fillColor=colors.HexColor("#667085")))
        return drawing
    max_value = max(max(count for _, count in items), 1)
    label_w = min(32 * mm, width * 0.34)
    value_w = 14 * mm
    bar_w = width - label_w - value_w - 4 * mm
    row_h = min(7 * mm, (height - 12) / max(len(items), 1))
    for index, (label, count) in enumerate(items[:6]):
        y = height - 20 - index * row_h
        if y < 2:
            break
        color = colors.HexColor(PALETTE[index % len(PALETTE)])
        drawing.add(String(0, y + 1, label[:10], fontName="STSong-Light", fontSize=6.5, fillColor=colors.HexColor("#425466")))
        drawing.add(Rect(label_w, y, bar_w, 4 * mm, fillColor=colors.HexColor("#edf3f8"), strokeColor=None))
        drawing.add(Rect(label_w, y, bar_w * (count / max_value), 4 * mm, fillColor=color, strokeColor=None))
        drawing.add(String(label_w + bar_w + 2 * mm, y + 1, str(count), fontName="STSong-Light", fontSize=6.5, fillColor=colors.HexColor("#1d2733")))
    return drawing


def _bar_drawing(items: list[tuple[str, float]], title: str, width: float, height: float) -> Drawing:
    drawing = Drawing(width, height)
    drawing.add(String(0, height - 8, title, fontName="STSong-Light", fontSize=8, fillColor=colors.HexColor("#1d2733")))
    if not items:
        drawing.add(String(0, height - 20, "暂无数据", fontName="STSong-Light", fontSize=7, fillColor=colors.HexColor("#667085")))
        return drawing
    max_value = max(max(value for _, value in items), 1)
    label_w = min(36 * mm, width * 0.34)
    value_w = 14 * mm
    bar_w = width - label_w - value_w - 4 * mm
    row_h = min(8 * mm, (height - 12) / max(len(items), 1))
    for index, (label, value) in enumerate(items):
        y = height - 20 - index * row_h
        if y < 2:
            break
        color = colors.HexColor(PALETTE[index % len(PALETTE)])
        drawing.add(String(0, y + 1, label[:12], fontName="STSong-Light", fontSize=6.5, fillColor=colors.HexColor("#425466")))
        drawing.add(Rect(label_w, y, bar_w, 4.2 * mm, fillColor=colors.HexColor("#edf3f8"), strokeColor=None))
        drawing.add(Rect(label_w, y, bar_w * (value / max_value), 4.2 * mm, fillColor=color, strokeColor=None))
        drawing.add(String(label_w + bar_w + 2 * mm, y + 1, f"{value:.0f}", fontName="STSong-Light", fontSize=6.5, fillColor=colors.HexColor("#1d2733")))
    return drawing

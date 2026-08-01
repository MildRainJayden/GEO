from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..models import AuditResult


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

    story.append(Paragraph("数据图览", styles["HeadingCN"]))
    story.append(
        Table(
            [
                [
                    _score_pie(result),
                    _bar_drawing(
                        [(p.provider, p.score) for p in result.score.platform_scores],
                        "平台得分",
                        84 * mm,
                        48 * mm,
                    ),
                ]
            ],
            colWidths=[76 * mm, 88 * mm],
        )
    )
    story.append(Spacer(1, 6))

    story.append(Paragraph("核心评分", styles["HeadingCN"]))
    story.append(_table([
        ["指标", "得分", "说明"],
        ["品牌提及", f"{result.score.mention_rate_score}/40", "回答中是否稳定出现品牌实体"],
        ["准确率", f"{result.score.accuracy_score}/30", "回答是否覆盖正确行业与产品事实"],
        ["行业/产品覆盖", f"{result.score.industry_coverage_score}/20", "品牌相关产品词是否被覆盖"],
        ["平台覆盖", f"{result.score.platform_coverage_score}/10", "已测平台中是否都有品牌曝光"],
    ], [42 * mm, 28 * mm, 94 * mm], styles))

    story.append(Paragraph("平台表现", styles["HeadingCN"]))
    platform_data = [["平台", "评分", "提及率", "准确率", "中文解释"]]
    for p in result.score.platform_scores:
        platform_data.append([p.provider, p.score, f"{p.mention_rate:.0%}", f"{p.accuracy_rate:.0%}", p.explanation])
    story.append(_table(platform_data, [24 * mm, 20 * mm, 22 * mm, 22 * mm, 76 * mm], styles))

    story.append(Paragraph("行业基准竞品矩阵", styles["HeadingCN"]))
    story.append(
        _bar_drawing(
            [(c.brand, c.mention_rate * 100) for c in result.competitors[:10]],
            "竞品短名单显著度",
            160 * mm,
            62 * mm,
        )
    )
    story.append(Spacer(1, 6))
    competitor_data = [["品牌", "短名单显著度", "行业上下文显著度", "场景题显著度"]]
    for c in result.competitors:
        competitor_data.append([c.brand, f"{c.mention_rate:.0%}", f"{c.industry_coverage:.0%}", f"{c.scenario_coverage:.0%}"])
    story.append(_table(competitor_data, [52 * mm, 36 * mm, 36 * mm, 36 * mm], styles))

    story.append(PageBreak())
    story.append(Paragraph("内容缺口", styles["HeadingCN"]))
    gap_data = [["优先级", "问题", "建议类型", "原因"]]
    for gap in result.content_gaps:
        gap_data.append([gap.priority, gap.question, gap.recommendation_type, gap.reason])
    story.append(_table(gap_data, [18 * mm, 62 * mm, 24 * mm, 60 * mm], styles))

    story.append(Paragraph("GEO 优化建议", styles["HeadingCN"]))
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


def _score_pie(result: AuditResult) -> Drawing:
    drawing = Drawing(70 * mm, 48 * mm)
    pie = Pie()
    pie.x = 0
    pie.y = 6
    pie.width = 35 * mm
    pie.height = 35 * mm
    values = [
        result.score.mention_rate_score,
        result.score.accuracy_score,
        result.score.industry_coverage_score,
        result.score.platform_coverage_score,
    ]
    pie.data = [max(value, 0.01) for value in values]
    palette = [
        colors.HexColor("#0f766e"),
        colors.HexColor("#2563eb"),
        colors.HexColor("#ca8a04"),
        colors.HexColor("#7c3aed"),
    ]
    for index, color in enumerate(palette):
        pie.slices[index].fillColor = color
        pie.slices[index].strokeColor = colors.white
    drawing.add(pie)
    labels = [
        ("品牌提及", values[0], "#0f766e"),
        ("准确率", values[1], "#2563eb"),
        ("行业覆盖", values[2], "#ca8a04"),
        ("平台覆盖", values[3], "#7c3aed"),
    ]
    for index, (label, value, color) in enumerate(labels):
        y = 34 * mm - index * 8 * mm
        drawing.add(Rect(42 * mm, y - 2, 4 * mm, 4 * mm, fillColor=colors.HexColor(color), strokeColor=None))
        drawing.add(String(48 * mm, y - 1, f"{label} {value:.1f}", fontName="STSong-Light", fontSize=7, fillColor=colors.HexColor("#1d2733")))
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
        drawing.add(String(0, y + 1, label[:12], fontName="STSong-Light", fontSize=6.5, fillColor=colors.HexColor("#425466")))
        drawing.add(Rect(label_w, y, bar_w, 4.2 * mm, fillColor=colors.HexColor("#edf3f8"), strokeColor=None))
        drawing.add(Rect(label_w, y, bar_w * (value / max_value), 4.2 * mm, fillColor=colors.HexColor("#0f766e"), strokeColor=None))
        drawing.add(String(label_w + bar_w + 2 * mm, y + 1, f"{value:.0f}", fontName="STSong-Light", fontSize=6.5, fillColor=colors.HexColor("#1d2733")))
    return drawing

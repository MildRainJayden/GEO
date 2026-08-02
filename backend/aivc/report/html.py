from __future__ import annotations

from collections import defaultdict
from html import escape

from ..models import AuditResult, BrandMentionAnalysis, CompetitorMetric
from .citation_insights import build_citation_insights


PALETTE = ["#0f766e", "#2563eb", "#ca8a04", "#7c3aed", "#dc2626", "#0891b2", "#9333ea", "#64748b"]


def render_report_html(result: AuditResult) -> str:
    score = result.score
    platform_rows = "".join(
        f"<tr><td>{escape(p.provider)}</td><td>{p.score}</td><td>{score.platform_weights.get(p.provider, 0):.0%}</td><td>{p.mention_rate:.0%}</td><td>{p.accuracy_rate:.0%}</td><td>{escape(p.explanation)}</td></tr>"
        for p in score.platform_scores
    )
    competitor_rows = "".join(_competitor_row(c) for c in result.competitors)
    gap_items = "".join(
        f"<li><strong>{escape(g.priority)}</strong>：{escape(g.question)} - {escape(g.recommendation_type)}，{escape(g.reason)}</li>"
        for g in result.content_gaps
    )
    suggestion_items = "".join(
        f"<section><h3>{escape(s.title)}</h3><p>{escape(s.action)}</p><pre>{escape(s.copyable_content)}</pre></section>"
        for s in result.geo_suggestions
    )
    task_rows = "".join(
        f"<tr><td>Day {t.day}</td><td>{escape(t.title)}</td><td>{escape(t.channel)}</td><td>{t.expected_score_lift}</td><td><pre>{escape(t.prompt_template)}</pre></td></tr>"
        for t in result.tasks
    )
    score_chart = _score_pie_svg(result)
    platform_chart = _bar_chart_svg([(p.provider, p.score, 100) for p in score.platform_scores], "平台得分", suffix="")
    voice_chart = _voice_share_donut_svg(result.competitors[:8])
    citation_section = _citation_section(result)
    model_geo_section = _model_geo_section(result)

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(result.input.brand_name)} AI Visibility Report</title>
  <style>
    body {{ margin: 0; font-family: Arial, "Microsoft YaHei", sans-serif; color: #1d2733; background: #f6f8fb; }}
    header {{ background: #101820; color: white; padding: 32px 7vw; }}
    main {{ padding: 28px 7vw 56px; }}
    h1, h2, h3 {{ margin: 0 0 14px; }}
    .score {{ font-size: 56px; font-weight: 800; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; }}
    .metric, section {{ background: white; border: 1px solid #dfe5ee; border-radius: 8px; padding: 18px; margin-bottom: 18px; }}
    .chart-grid {{ display: grid; grid-template-columns: minmax(260px, 0.9fr) minmax(320px, 1.2fr); gap: 18px; align-items: start; margin: 18px 0; }}
    .voice-grid {{ display: grid; grid-template-columns: minmax(260px, 0.78fr) minmax(360px, 1.22fr); gap: 18px; align-items: start; margin: 18px 0; }}
    .citation-grid {{ display: grid; grid-template-columns: repeat(3, minmax(180px, 1fr)); gap: 16px; margin: 16px 0 22px; }}
    .citation-card {{ background: white; border: 1px solid #dfe5ee; border-radius: 8px; padding: 18px; box-shadow: 0 1px 3px rgba(16, 24, 40, 0.06); }}
    .citation-card span {{ color: #667085; font-size: 13px; }}
    .citation-card strong {{ display: block; margin-top: 22px; font-size: 36px; line-height: 1; }}
    .citation-panels {{ display: grid; grid-template-columns: repeat(2, minmax(280px, 1fr)); gap: 16px; }}
    .chart-card {{ background: white; border: 1px solid #dfe5ee; border-radius: 8px; padding: 18px; }}
    .chart-card h3 {{ font-size: 16px; margin-bottom: 10px; }}
    .legend {{ display: grid; gap: 8px; margin-top: 12px; font-size: 13px; }}
    .legend span {{ display: inline-flex; align-items: center; gap: 8px; }}
    .swatch {{ width: 11px; height: 11px; border-radius: 3px; display: inline-block; flex: 0 0 auto; }}
    .note {{ color: #667085; font-size: 13px; line-height: 1.7; margin: -4px 0 14px; }}
    .summary {{ background: #eef7f5; border-color: #b7d8d2; }}
    .source-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }}
    .source-card {{ border: 1px solid #dfe5ee; border-radius: 8px; padding: 14px; background: #fbfdff; }}
    .source-card strong {{ display: block; margin-bottom: 6px; }}
    .source-card a {{ color: #0f766e; word-break: break-all; }}
    .insight {{ background: #fff8ed; border-color: #f0d5a8; }}
    svg.chart {{ width: 100%; height: auto; overflow: visible; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dfe5ee; margin-bottom: 18px; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid #edf1f6; text-align: left; vertical-align: top; }}
    th {{ background: #edf3f8; }}
    pre {{ white-space: pre-wrap; background: #0f1720; color: #e6edf3; padding: 12px; border-radius: 6px; overflow: auto; font-size: 13px; line-height: 1.55; }}
    .copy-note {{ color: #667085; font-size: 13px; margin: -8px 0 14px; }}
    @media (max-width: 760px) {{ .chart-grid, .voice-grid, .citation-grid, .citation-panels {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <header>
    <h1>{escape(result.input.brand_name)} AI 搜索可见度报告</h1>
    <p>{escape(result.input.industry or "自动调研行业")} · {escape(str(result.input.website or ""))}</p>
    <div class="score">{score.total_score}</div>
  </header>
  <main>
    <section class="summary">
      <h2>报告总结</h2>
      <p>{escape(_summary_text(result))}</p>
    </section>
    <div class="grid">
      <div class="metric">品牌提及<strong>{score.mention_rate_score}/40</strong></div>
      <div class="metric">准确率<strong>{score.accuracy_score}/30</strong></div>
      <div class="metric">行业/产品覆盖<strong>{score.industry_coverage_score}/20</strong></div>
      <div class="metric">平台覆盖<strong>{score.platform_coverage_score}/10</strong></div>
      <div class="metric">竞争声量<strong>{score.competitive_voice_score}/100</strong></div>
    </div>
    <p class="note">评分说明：总分由“品牌自身可见度”和“行业竞争声量”共同组成。多模型结果会先按模型分别计算，再按国内月活规模权重与模型均衡权重综合，避免单一模型左右结论。自身问题回答得好但行业对比中出现少，总分会被竞争声量拉低；这更接近客户真正关心的“AI 会不会在同类推荐里想起你”。</p>
    <div class="chart-grid">
      <section class="chart-card"><h3>评分构成</h3>{score_chart}</section>
      <section class="chart-card"><h3>平台得分</h3>{platform_chart}</section>
    </div>
    <h2>平台表现</h2>
    <p class="note">说明：平台得分用于观察不同 AI 引擎对品牌的熟悉度和回答稳定性；总分按模型权重加权综合。权重默认参考国内公开月活规模，并保留一部分模型均衡权重，后续可在配置中覆盖。</p>
    <table><tr><th>平台</th><th>评分</th><th>总分权重</th><th>提及率</th><th>准确率</th><th>中文解释</th></tr>{platform_rows}</table>
    <h2>AI 声量份额</h2>
    <p class="note">说明：AI 声量份额表示在同一行业的中立推荐与对比问题中，AI 更常把哪些品牌放到靠前位置。它不是销量或市场份额，而是“AI 回答里的被看见程度”。</p>
    <div class="voice-grid">
      <section class="chart-card"><h3>声量占比</h3>{voice_chart}</section>
      <section class="chart-card insight"><h3>如何理解这张图</h3><p>{escape(_voice_explanation(result))}</p></section>
    </div>
    <table><tr><th>品牌</th><th>AI 声量份额</th><th>出现率</th><th>平均排名</th><th>Top3率</th><th>场景题出现率</th><th>有效样本</th></tr>{competitor_rows}</table>
    {citation_section}
    <h2>内容缺口</h2>
    <p class="note">说明：内容缺口由本次 AI 回答中暴露的弱项、竞品上下文和个性化分析生成，用于指导官网、FAQ、对比页、案例页等内容建设。</p>
    <section><ul>{gap_items}</ul></section>
    <h2>GEO 优化建议</h2>
    <p class="note">说明：建议优先补充 AI 容易摘取和引用的内容，例如清晰结论、参数表、FAQ、真实案例、竞品对比和权威来源。</p>
    {model_geo_section}
    {suggestion_items}
    <h2>30 天任务</h2>
    <p class="copy-note">每个任务都附带可复制的提示词模板，可直接交给内容团队或模型生成首稿。</p>
    <table><tr><th>日期</th><th>任务</th><th>渠道</th><th>预计提分</th><th>一键复制提示词模板</th></tr>{task_rows}</table>
  </main>
</body>
</html>"""


def _competitor_row(metric: CompetitorMetric) -> str:
    avg_rank = f"{metric.average_rank:.2f}" if metric.average_rank is not None else "-"
    sample = str(metric.effective_sample_count or "-")
    return (
        f"<tr><td>{escape(metric.brand)}</td>"
        f"<td>{(metric.voice_share or metric.mention_rate):.0%}</td>"
        f"<td>{(metric.occurrence_rate or metric.accuracy_rate):.0%}</td>"
        f"<td>{avg_rank}</td>"
        f"<td>{metric.top3_rate:.0%}</td>"
        f"<td>{metric.scenario_coverage:.0%}</td>"
        f"<td>{sample}</td></tr>"
    )


def _citation_section(result: AuditResult) -> str:
    insights = build_citation_insights(result)
    provider_rows = "".join(
        "<tr>"
        f"<td>{escape(item.provider)}</td>"
        f"<td>{item.total}</td>"
        f"<td>{item.unique_domains}</td>"
        f"<td>{item.brand_citation_share:.0%}</td>"
        f"<td>{escape('、'.join(name for name, _count in item.domains[:3]) or '暂无')}</td>"
        "</tr>"
        for item in insights.providers
    )
    empty_note = (
        '<p class="note">本轮模型未返回可解析的引用链接。若要看到更完整的引用来源，可接入支持联网引用的模型，或补充公开搜索数据源。</p>'
        if insights.total == 0
        else ""
    )
    return f"""
    <h2>引用来源</h2>
    <p class="note">查看大语言模型在回答本次问题时引用、写出或明确提到的来源。本轮会额外加入来源探测问题，让模型列出它判断品牌、产品、口碑、参数、售后和竞品时会参考的公开网站；这些样本只用于引用来源，不参与总分计算。若品牌官网引用占比为 0，表示本轮可见来源更多指向第三方平台、媒体、社区或权威机构，模型没有明显把官网作为可引用入口。</p>
    <div class="citation-grid">
      <div class="citation-card"><span>品牌官网引用占比</span><strong>{insights.brand_citation_share:.0%}</strong></div>
      <div class="citation-card"><span>唯一域名数</span><strong>{insights.unique_domains}</strong></div>
      <div class="citation-card"><span>来源出现次数</span><strong>{insights.total}</strong></div>
    </div>
    {empty_note}
    <div class="citation-panels">
      <section class="chart-card"><h3>引文类别</h3>{_distribution_svg(insights.categories, "引文类别")}</section>
      <section class="chart-card"><h3>引文页面类型</h3>{_distribution_svg(insights.page_types, "引文页面类型")}</section>
      <section class="chart-card"><h3>被引最多的域名</h3>{_count_table(insights.domains, "域名")}</section>
      <section class="chart-card"><h3>被引用次数最多的网址</h3>{_url_table(insights.urls)}</section>
    </div>
    <section class="chart-card">
      <h3>各模型引用来源表现</h3>
      <p class="note">用于观察不同模型更倾向参考官网、平台、媒体、社区还是权威机构；后续同时接入多个模型时，这里会按模型分别展示。</p>
      <table><tr><th>模型</th><th>来源出现次数</th><th>唯一域名数</th><th>官网占比</th><th>主要被引域名</th></tr>{provider_rows}</table>
    </section>
    """


def _distribution_svg(items: list[tuple[str, int]], title: str) -> str:
    if not items:
        return '<p class="copy-note">暂无可解析引用</p>'
    total = sum(count for _, count in items) or 1
    radius = 58
    circumference = 2 * 3.14159 * radius
    segments: list[str] = []
    legend: list[str] = []
    cumulative = 0.0
    for index, (label, count) in enumerate(items):
        share = count / total
        color = PALETTE[index % len(PALETTE)]
        length = share * circumference
        segments.append(
            f'<circle cx="84" cy="84" r="{radius}" fill="none" stroke="{color}" stroke-width="28" '
            f'stroke-dasharray="{length:.2f} {circumference - length:.2f}" stroke-dashoffset="{-cumulative:.2f}" '
            'transform="rotate(-90 84 84)" />'
        )
        cumulative += length
        legend.append(
            f'<span><i class="swatch" style="background:{color}"></i>{escape(label)}：{share:.0%}，{count}次</span>'
        )
    return (
        '<div style="display:grid;grid-template-columns:180px 1fr;gap:16px;align-items:center">'
        f'<svg class="chart" viewBox="0 0 168 168" role="img" aria-label="{escape(title)}">'
        '<circle cx="84" cy="84" r="58" fill="none" stroke="#e5eaf0" stroke-width="28" />'
        + "".join(segments)
        + f'<text x="84" y="78" text-anchor="middle" font-size="22" font-weight="700" fill="#1d2733">{total}</text>'
        + '<text x="84" y="100" text-anchor="middle" font-size="12" fill="#667085">次</text></svg>'
        + '<div class="legend">'
        + "".join(legend)
        + "</div></div>"
    )


def _count_table(items: list[tuple[str, int]], label: str) -> str:
    if not items:
        return '<p class="copy-note">暂无可解析引用</p>'
    rows = "".join(f"<tr><td>{escape(name)}</td><td>{count}</td></tr>" for name, count in items)
    return f"<table><tr><th>{escape(label)}</th><th>引用次数</th></tr>{rows}</table>"


def _url_table(items: list[tuple[str, int]]) -> str:
    if not items:
        return '<p class="copy-note">暂无可解析引用</p>'
    rows = "".join(
        f'<tr><td><a href="{escape(url)}" target="_blank" rel="noreferrer">{escape(_short_url(url))}</a></td><td>{count}</td></tr>'
        for url, count in items
    )
    return f"<table><tr><th>网址</th><th>引用次数</th></tr>{rows}</table>"


def _short_url(url: str) -> str:
    return url if len(url) <= 80 else f"{url[:77]}..."


def _model_geo_section(result: AuditResult) -> str:
    if not result.score.platform_scores:
        return ""
    analysis_by_provider: dict[str, list[BrandMentionAnalysis]] = defaultdict(list)
    for analysis in result.analyses:
        analysis_by_provider[analysis.provider].append(analysis)
    rows: list[str] = []
    for platform in result.score.platform_scores:
        analyses = analysis_by_provider.get(platform.provider, [])
        weak_count = sum(
            1
            for analysis in analyses
            if not analysis.brand_mentioned or not analysis.description_correct or not analysis.industry_terms_covered
        )
        issue = _model_issue(platform.mention_rate, platform.accuracy_rate, weak_count, len(analyses))
        rows.append(
            f"<tr><td>{escape(platform.provider)}</td><td>{escape(issue)}</td><td>{escape(_model_action(platform.provider, issue))}</td></tr>"
        )
    return (
        "<h3>不同 AI 平台的优化重点</h3>"
        '<p class="note">说明：不同 AI 平台对官网、媒体稿、问答内容和对比内容的吸收偏好不同。这里给出的是客户可执行的内容建设方向。</p>'
        "<table><tr><th>平台</th><th>本轮观察</th><th>优化重点</th></tr>"
        + "".join(rows)
        + "</table>"
    )


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
    score = result.score.total_score
    leader = result.competitors[0].brand if result.competitors else "暂无竞品数据"
    brand_metric = next((item for item in result.competitors if item.brand == brand), None)
    share = f"{(brand_metric.voice_share or brand_metric.mention_rate):.0%}" if brand_metric else "暂无"
    return f"{brand} 本轮 AI 可见度总分为 {score}。行业对比中，当前 AI 声量领先品牌为 {leader}；{brand} 的 AI 声量份额为 {share}。建议优先提升行业推荐问题中的出现率和靠前度，并补充可被 AI 摘取的产品事实、场景问答与竞品对比内容。"


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


def _score_pie_svg(result: AuditResult) -> str:
    parts = [
        ("品牌提及", result.score.mention_rate_score, 40, PALETTE[0]),
        ("准确率", result.score.accuracy_score, 30, PALETTE[1]),
        ("行业/产品覆盖", result.score.industry_coverage_score, 20, PALETTE[2]),
        ("平台覆盖", result.score.platform_coverage_score, 10, PALETTE[3]),
    ]
    return _donut_svg(parts, center=f"{result.score.total_score:.1f}", subtitle="总分", aria="评分构成饼图")


def _voice_share_donut_svg(metrics: list[CompetitorMetric]) -> str:
    items = [(m.brand, (m.voice_share or m.mention_rate) * 100, 100, PALETTE[i % len(PALETTE)]) for i, m in enumerate(metrics)]
    if not items:
        return '<p class="copy-note">暂无数据</p>'
    visible = items[:6]
    other_value = sum(value for _, value, _, _ in items[6:])
    if other_value > 0:
        visible.append(("其他", other_value, 100, PALETTE[-1]))
    leader_value = visible[0][1] if visible else 0
    return _donut_svg(visible, center=f"{leader_value:.0f}%", subtitle="最高声量", aria="AI 声量份额饼图")


def _donut_svg(parts: list[tuple[str, float, float, str]], center: str, subtitle: str, aria: str) -> str:
    total = sum(max(value, 0) for _, value, _, _ in parts) or 1
    segments: list[str] = []
    legend: list[str] = []
    cumulative = 0.0
    radius = 58
    circumference = 2 * 3.14159 * radius
    for label, value, max_value, color in parts:
        safe_value = max(value, 0)
        length = safe_value / total * circumference
        segments.append(
            f'<circle cx="84" cy="84" r="{radius}" fill="none" stroke="{color}" stroke-width="28" '
            f'stroke-dasharray="{length:.2f} {circumference - length:.2f}" stroke-dashoffset="{-cumulative:.2f}" '
            'transform="rotate(-90 84 84)" />'
        )
        cumulative += length
        value_text = f"{safe_value:.0f}%" if max_value == 100 else f"{safe_value:.1f}/{max_value}"
        legend.append(f'<span><i class="swatch" style="background:{color}"></i>{escape(label)}：{value_text}</span>')
    return (
        '<div style="display:grid;grid-template-columns:180px 1fr;gap:16px;align-items:center">'
        f'<svg class="chart" viewBox="0 0 168 168" role="img" aria-label="{escape(aria)}">'
        '<circle cx="84" cy="84" r="58" fill="none" stroke="#e5eaf0" stroke-width="28" />'
        + "".join(segments)
        + f'<text x="84" y="78" text-anchor="middle" font-size="22" font-weight="700" fill="#1d2733">{escape(center)}</text>'
        + f'<text x="84" y="100" text-anchor="middle" font-size="12" fill="#667085">{escape(subtitle)}</text></svg>'
        + '<div class="legend">'
        + "".join(legend)
        + "</div></div>"
    )


def _bar_chart_svg(items: list[tuple[str, float, float]], title: str, suffix: str) -> str:
    if not items:
        return f'<p class="copy-note">{escape(title)}暂无数据</p>'
    width = 620
    left = 126
    row_h = 34
    height = 24 + len(items) * row_h
    bars: list[str] = []
    for index, (label, value, max_value) in enumerate(items):
        y = 18 + index * row_h
        pct = 0 if max_value <= 0 else max(0, min(1, value / max_value))
        bar_w = pct * (width - left - 72)
        color = PALETTE[index % len(PALETTE)]
        bars.append(
            f'<text x="0" y="{y + 15}" font-size="12" fill="#425466">{escape(label[:18])}</text>'
            f'<rect x="{left}" y="{y}" width="{width-left-72}" height="18" rx="5" fill="#edf3f8" />'
            f'<rect x="{left}" y="{y}" width="{bar_w:.1f}" height="18" rx="5" fill="{color}" />'
            f'<text x="{width - 58}" y="{y + 14}" font-size="12" fill="#1d2733">{value:.0f}{suffix}</text>'
        )
    return f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">{"".join(bars)}</svg>'

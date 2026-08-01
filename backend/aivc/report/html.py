from __future__ import annotations

from html import escape

from ..models import AuditResult


def render_report_html(result: AuditResult) -> str:
    score = result.score
    platform_rows = "".join(
        f"<tr><td>{escape(p.provider)}</td><td>{p.score}</td><td>{p.mention_rate:.0%}</td><td>{p.accuracy_rate:.0%}</td><td>{escape(p.explanation)}</td></tr>"
        for p in score.platform_scores
    )
    citation_rows = "".join(
        f"<tr><td>{escape(c.source_type)}</td><td>{c.count}</td><td>{c.share:.0%}</td><td>{c.authority:.2f}</td></tr>"
        for c in result.citations
    )
    citation_section = (
        f"""
    <h2>引用来源</h2>
    <table><tr><th>来源</th><th>次数</th><th>占比</th><th>权威度</th></tr>{citation_rows}</table>"""
        if citation_rows
        else ""
    )
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
    competitor_rows = "".join(
        f"<tr><td>{escape(c.brand)}</td><td>{c.mention_rate:.0%}</td><td>{c.industry_coverage:.0%}</td><td>{c.scenario_coverage:.0%}</td></tr>"
        for c in result.competitors
    )
    score_chart = _score_pie_svg(result)
    platform_chart = _bar_chart_svg(
        [(p.provider, p.score, 100) for p in score.platform_scores],
        "平台得分条形图",
        suffix="",
    )
    competitor_chart = _bar_chart_svg(
        [(c.brand, c.mention_rate * 100, 100) for c in result.competitors[:10]],
        "竞品短名单显著度条形图",
        suffix="%",
    )

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
    .chart-card {{ background: white; border: 1px solid #dfe5ee; border-radius: 8px; padding: 18px; }}
    .chart-card h3 {{ font-size: 16px; margin-bottom: 10px; }}
    .legend {{ display: grid; gap: 8px; margin-top: 12px; font-size: 13px; }}
    .legend span {{ display: inline-flex; align-items: center; gap: 8px; }}
    .swatch {{ width: 11px; height: 11px; border-radius: 3px; display: inline-block; }}
    svg.chart {{ width: 100%; height: auto; overflow: visible; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dfe5ee; margin-bottom: 18px; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid #edf1f6; text-align: left; }}
    th {{ background: #edf3f8; }}
    pre {{ white-space: pre-wrap; background: #0f1720; color: #e6edf3; padding: 12px; border-radius: 6px; overflow: auto; font-size: 13px; line-height: 1.55; }}
    .copy-note {{ color: #667085; font-size: 13px; margin: -8px 0 14px; }}
    @media (max-width: 760px) {{ .chart-grid {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <header>
    <h1>{escape(result.input.brand_name)} AI 搜索可见度报告</h1>
    <p>{escape(result.input.industry)} · {escape(str(result.input.website or ""))}</p>
    <div class="score">{score.total_score}</div>
  </header>
  <main>
    <div class="grid">
      <div class="metric">品牌提及：{score.mention_rate_score}/40</div>
      <div class="metric">准确率：{score.accuracy_score}/30</div>
      <div class="metric">行业/产品覆盖：{score.industry_coverage_score}/20</div>
      <div class="metric">平台覆盖：{score.platform_coverage_score}/10</div>
    </div>
    <div class="chart-grid">
      <section class="chart-card"><h3>评分构成</h3>{score_chart}</section>
      <section class="chart-card"><h3>平台得分</h3>{platform_chart}</section>
    </div>
    <h2>平台表现</h2>
    <table><tr><th>平台</th><th>评分</th><th>提及率</th><th>准确率</th><th>中文解释</th></tr>{platform_rows}</table>
    <h2>行业基准竞品矩阵</h2>
    <section class="chart-card"><h3>竞品短名单显著度</h3>{competitor_chart}</section>
    <table><tr><th>品牌</th><th>短名单显著度</th><th>行业上下文显著度</th><th>场景题显著度</th></tr>{competitor_rows}</table>
    {citation_section}
    <h2>内容缺口</h2>
    <section><ul>{gap_items}</ul></section>
    <h2>GEO 优化建议</h2>
    {suggestion_items}
    <h2>30 天任务</h2>
    <p class="copy-note">每个任务都附带可复制的提示词模板，可直接交给内容团队或模型生成首稿。</p>
    <table><tr><th>日期</th><th>任务</th><th>渠道</th><th>预计提分</th><th>一键复制提示词模板</th></tr>{task_rows}</table>
  </main>
</body>
</html>"""


def _score_pie_svg(result: AuditResult) -> str:
    parts = [
        ("品牌提及", result.score.mention_rate_score, 40, "#0f766e"),
        ("准确率", result.score.accuracy_score, 30, "#2563eb"),
        ("行业/产品覆盖", result.score.industry_coverage_score, 20, "#ca8a04"),
        ("平台覆盖", result.score.platform_coverage_score, 10, "#7c3aed"),
    ]
    total = sum(value for _, value, _, _ in parts) or 1
    segments: list[str] = []
    legend: list[str] = []
    cumulative = 0.0
    radius = 58
    circumference = 2 * 3.14159 * radius
    for label, value, max_value, color in parts:
        length = value / total * circumference
        segments.append(
            f'<circle cx="84" cy="84" r="{radius}" fill="none" stroke="{color}" stroke-width="28" '
            f'stroke-dasharray="{length:.2f} {circumference - length:.2f}" stroke-dashoffset="{-cumulative:.2f}" '
            'transform="rotate(-90 84 84)" />'
        )
        cumulative += length
        legend.append(
            f'<span><i class="swatch" style="background:{color}"></i>{escape(label)}：{value:.1f}/{max_value}</span>'
        )
    return (
        '<div style="display:grid;grid-template-columns:180px 1fr;gap:16px;align-items:center">'
        '<svg class="chart" viewBox="0 0 168 168" role="img" aria-label="评分构成饼图">'
        '<circle cx="84" cy="84" r="58" fill="none" stroke="#e5eaf0" stroke-width="28" />'
        + "".join(segments)
        + f'<text x="84" y="78" text-anchor="middle" font-size="22" font-weight="700" fill="#1d2733">{result.score.total_score:.1f}</text>'
        + '<text x="84" y="100" text-anchor="middle" font-size="12" fill="#667085">总分</text></svg>'
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
        bars.append(
            f'<text x="0" y="{y + 15}" font-size="12" fill="#425466">{escape(label[:18])}</text>'
            f'<rect x="{left}" y="{y}" width="{width-left-72}" height="18" rx="5" fill="#edf3f8" />'
            f'<rect x="{left}" y="{y}" width="{bar_w:.1f}" height="18" rx="5" fill="#0f766e" />'
            f'<text x="{width - 58}" y="{y + 14}" font-size="12" fill="#1d2733">{value:.0f}{suffix}</text>'
        )
    return f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">{"".join(bars)}</svg>'

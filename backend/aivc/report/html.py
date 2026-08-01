from __future__ import annotations

from html import escape

from ..models import AuditResult


def render_report_html(result: AuditResult) -> str:
    score = result.score
    platform_rows = "".join(
        f"<tr><td>{escape(p.provider)}</td><td>{p.score}</td><td>{p.mention_rate:.0%}</td><td>{p.top3_rate:.0%}</td><td>{p.accuracy_rate:.0%}</td><td>{escape(p.explanation)}</td></tr>"
        for p in score.platform_scores
    )
    citation_rows = "".join(
        f"<tr><td>{escape(c.source_type)}</td><td>{c.count}</td><td>{c.share:.0%}</td><td>{c.authority:.2f}</td></tr>"
        for c in result.citations
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
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dfe5ee; margin-bottom: 18px; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid #edf1f6; text-align: left; }}
    th {{ background: #edf3f8; }}
    pre {{ white-space: pre-wrap; background: #0f1720; color: #e6edf3; padding: 12px; border-radius: 6px; overflow: auto; font-size: 13px; line-height: 1.55; }}
    .copy-note {{ color: #667085; font-size: 13px; margin: -8px 0 14px; }}
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
    <h2>平台表现</h2>
    <table><tr><th>平台</th><th>评分</th><th>提及率</th><th>Top3</th><th>准确率</th><th>中文解释</th></tr>{platform_rows}</table>
    <h2>行业基准竞品矩阵</h2>
    <table><tr><th>品牌</th><th>短名单显著度</th><th>行业上下文显著度</th><th>场景题显著度</th></tr>{competitor_rows}</table>
    <h2>引用来源</h2>
    <table><tr><th>来源</th><th>次数</th><th>占比</th><th>权威度</th></tr>{citation_rows}</table>
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

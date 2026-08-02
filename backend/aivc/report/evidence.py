from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from html import escape

from ..models import AuditResult, BrandMentionAnalysis
from .citation_insights import build_citation_insights, build_citation_records


METHODOLOGY_NOTES = [
    "本证据包用于审计和复核，不是面向销售展示的精简报告。",
    "本项目衡量的是品牌在大模型回答中的可见度，不等同于销量、市场份额或全网搜索量。",
    "评分只使用品牌认知、行业推荐、场景、竞品对比、购买决策等可见度问题；引用来源探测题只用于来源分析，不参与总分。",
    "模型回答可能存在幻觉，因此证据包保留原始问题、原始回答、识别出的来源和计算口径，便于客户抽样复核。",
    "多模型测评会按模型分别展示，同时用相同问题集和相同规则综合计算，降低单一模型偏差。",
]


def build_evidence_payload(result: AuditResult) -> dict:
    question_by_id = {question.id: question for question in result.questions}
    analysis_by_key = {(analysis.provider, analysis.question_id): analysis for analysis in result.analyses}
    citation_records = build_citation_records(result)
    citations_by_key: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for record in citation_records:
        citations_by_key[(record.provider, record.question_id)].append(asdict(record))

    response_rows = []
    for response in result.responses:
        question = question_by_id.get(response.question_id)
        analysis = analysis_by_key.get((response.provider, response.question_id))
        response_rows.append(
            {
                "provider": response.provider,
                "model_version": response.model_version,
                "question_id": response.question_id,
                "question_type": question.type.value if question else "",
                "question": response.question,
                "answer": response.answer,
                "latency_ms": response.latency_ms,
                "token_count": response.token_count,
                "created_at": response.created_at.isoformat(),
                "structured_citations": [citation.model_dump(mode="json") for citation in response.citations],
                "parsed_sources": citations_by_key.get((response.provider, response.question_id), []),
                "visibility_analysis": _analysis_dict(analysis),
            }
        )

    question_type_counts = Counter(question.type.value for question in result.questions)
    response_provider_counts = Counter(response.provider for response in result.responses)
    citation_insights = build_citation_insights(result)
    payload = {
        "audit_id": result.audit_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "brand": result.input.model_dump(mode="json"),
        "methodology_notes": METHODOLOGY_NOTES,
        "sample_summary": {
            "question_count": len(result.questions),
            "response_count": len(result.responses),
            "analysis_count": len(result.analyses),
            "question_type_counts": dict(sorted(question_type_counts.items())),
            "response_provider_counts": dict(sorted(response_provider_counts.items())),
            "successful_providers": sorted(response_provider_counts),
        },
        "score": result.score.model_dump(mode="json"),
        "score_rules": _score_rules(),
        "provider_weighting": {
            "normalized_weights": result.score.platform_weights,
            "raw_mau_basis": result.score.platform_weight_basis,
            "rule": "最终模型权重 = 70% 国内月活规模份额 + 30% 模型均衡份额；未知或未披露月活的模型使用可配置基线，避免新增模型权重为 0。",
            "config": "可通过 AIVC_PROVIDER_MAU_WEIGHTS、AIVC_UNKNOWN_PROVIDER_MAU、AIVC_PROVIDER_MAU_BLEND 调整。",
        },
        "citation_summary": {
            "total_source_mentions": citation_insights.total,
            "unique_domains": citation_insights.unique_domains,
            "brand_official_site_share": citation_insights.brand_citation_share,
            "categories": citation_insights.categories,
            "page_types": citation_insights.page_types,
            "top_domains": citation_insights.domains,
            "top_urls": citation_insights.urls,
            "providers": [asdict(provider) for provider in citation_insights.providers],
        },
        "competitors": [metric.model_dump(mode="json") for metric in result.competitors],
        "questions": [question.model_dump(mode="json") for question in result.questions],
        "responses": response_rows,
        "content_gaps": [gap.model_dump(mode="json") for gap in result.content_gaps],
        "geo_suggestions": [suggestion.model_dump(mode="json") for suggestion in result.geo_suggestions],
        "tasks": [task.model_dump(mode="json") for task in result.tasks],
        "web_evidence_notes": result.evidence_notes,
    }
    payload["sha256"] = _payload_hash(payload)
    return payload


def render_evidence_html(result: AuditResult) -> str:
    payload = build_evidence_payload(result)
    responses = payload["responses"]
    response_rows = "".join(_response_row(row) for row in responses)
    source_rows = "".join(
        _parsed_source_row(response, source)
        for response in responses
        for source in response["parsed_sources"]
    )
    method_items = "".join(f"<li>{escape(note)}</li>" for note in payload["methodology_notes"])
    score_rows = "".join(
        f"<tr><td>{escape(label)}</td><td>{escape(str(value))}</td></tr>"
        for label, value in _score_table_items(payload).items()
    )
    source_stat_rows = "".join(
        f"<tr><td>{escape(name)}</td><td>{count}</td></tr>"
        for name, count in payload["citation_summary"]["top_domains"][:12]
    )
    provider_rows = "".join(
        f"<tr><td>{escape(item['provider'])}</td><td>{item['total']}</td><td>{item['unique_domains']}</td><td>{item['brand_citation_share']:.0%}</td></tr>"
        for item in payload["citation_summary"]["providers"]
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(str(payload["brand"]["brand_name"]))} 测评证据包</title>
  <style>
    body {{ margin: 0; font-family: Arial, "Microsoft YaHei", sans-serif; color: #172033; background: #f6f8fb; }}
    header {{ background: #111827; color: white; padding: 28px 7vw; }}
    main {{ padding: 26px 7vw 60px; }}
    section {{ background: white; border: 1px solid #dfe5ee; border-radius: 8px; padding: 18px; margin-bottom: 18px; }}
    h1, h2, h3 {{ margin: 0 0 12px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }}
    .metric {{ background: #fbfdff; border: 1px solid #dfe5ee; border-radius: 8px; padding: 14px; }}
    .metric strong {{ display: block; font-size: 28px; margin-top: 8px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
    th, td {{ border-bottom: 1px solid #e8edf3; padding: 9px 8px; text-align: left; vertical-align: top; font-size: 13px; }}
    th {{ background: #edf3f8; }}
    details {{ border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 12px; margin: 8px 0; background: #fbfdff; }}
    summary {{ cursor: pointer; font-weight: 700; }}
    pre {{ white-space: pre-wrap; background: #111827; color: #e5e7eb; border-radius: 6px; padding: 12px; overflow: auto; }}
    .note {{ color: #667085; line-height: 1.7; }}
    a {{ color: #0f766e; word-break: break-all; }}
  </style>
</head>
<body>
  <header>
    <h1>{escape(str(payload["brand"]["brand_name"]))} 测评证据包</h1>
    <p>审计编号：{escape(payload["audit_id"])} · 生成时间：{escape(payload["generated_at"])} · 校验哈希：{escape(payload["sha256"][:16])}...</p>
  </header>
  <main>
    <section>
      <h2>用途说明</h2>
      <p class="note">这份证据包用于回应客户关于数据来源、AI 幻觉、测评流程和指标口径的质疑。它保留原始问题和模型回答，因此内容会比正式报告更长。</p>
      <ul>{method_items}</ul>
    </section>
    <section>
      <h2>样本概览</h2>
      <div class="grid">
        <div class="metric">问题数<strong>{payload["sample_summary"]["question_count"]}</strong></div>
        <div class="metric">模型回答数<strong>{payload["sample_summary"]["response_count"]}</strong></div>
        <div class="metric">来源出现次数<strong>{payload["citation_summary"]["total_source_mentions"]}</strong></div>
        <div class="metric">唯一域名数<strong>{payload["citation_summary"]["unique_domains"]}</strong></div>
      </div>
    </section>
    <section>
      <h2>评分口径</h2>
      <table><tr><th>项目</th><th>说明</th></tr>{score_rows}</table>
    </section>
    <section>
      <h2>引用来源复核</h2>
      <p class="note">以下来源均可追溯到具体模型、问题和原始回答。来源出现次数是本轮样本中的可见来源信号，不代表全网真实引用量。</p>
      <h3>各模型来源概览</h3>
      <table><tr><th>模型</th><th>来源出现次数</th><th>唯一域名数</th><th>官网占比</th></tr>{provider_rows}</table>
      <h3>被引最多域名</h3>
      <table><tr><th>域名</th><th>次数</th></tr>{source_stat_rows}</table>
      <h3>来源逐条追溯</h3>
      <table><tr><th>模型</th><th>问题类型</th><th>来源</th><th>类别</th><th>页面类型</th><th>原问题</th></tr>{source_rows}</table>
    </section>
    <section>
      <h2>原始问题与回答</h2>
      {response_rows}
    </section>
    <section>
      <h2>机器可读 JSON</h2>
      <p><a href="/audit/{escape(payload["audit_id"])}/evidence.json" target="_blank" rel="noreferrer">打开 evidence.json</a></p>
    </section>
  </main>
</body>
</html>"""


def _analysis_dict(analysis: BrandMentionAnalysis | None) -> dict | None:
    return analysis.model_dump(mode="json") if analysis else None


def _score_rules() -> dict[str, str]:
    return {
        "品牌提及": "统计可见度问题中品牌是否被模型主动提及。",
        "描述准确": "统计模型回答是否覆盖正确行业或主要产品事实。",
        "行业/产品覆盖": "统计回答是否包含品牌所属行业和产品相关词。",
        "平台覆盖": "统计成功返回的模型中是否均有品牌曝光。",
        "竞争声量": "基于中立行业推荐和竞品对比问题，衡量品牌与竞品在 AI 回答中的相对出现和靠前程度。",
        "模型权重": "多模型结果先按模型分别计算，再按国内月活规模权重和模型均衡权重综合。默认采用 70% 月活份额 + 30% 均衡份额。",
        "引用来源": "引用来源探测题只用于分析模型会参考哪些外部网站，不参与总分计算。",
    }


def _score_table_items(payload: dict) -> dict[str, object]:
    score = payload["score"]
    return {
        "总分": score["total_score"],
        "基础可见度": score.get("base_visibility_score"),
        "品牌提及得分": score["mention_rate_score"],
        "准确率得分": score["accuracy_score"],
        "行业/产品覆盖得分": score["industry_coverage_score"],
        "平台覆盖得分": score["platform_coverage_score"],
        "竞争声量得分": score.get("competitive_voice_score"),
        "模型权重": payload.get("provider_weighting", {}).get("normalized_weights", {}),
        "权重依据": payload.get("provider_weighting", {}).get("raw_mau_basis", {}),
        "说明": "总分由品牌自身可见度和行业竞争声量综合计算；引用来源不直接扣分。",
    }


def _response_row(row: dict) -> str:
    analysis = row.get("visibility_analysis") or {}
    source_count = len(row["parsed_sources"])
    answer = row["answer"]
    return (
        "<details>"
        f"<summary>{escape(row['provider'])} · {escape(row['question_type'])} · 来源 {source_count} 个 · {escape(_short(row['question'], 90))}</summary>"
        "<table>"
        f"<tr><th>模型</th><td>{escape(row['model_version'])}</td></tr>"
        f"<tr><th>问题</th><td>{escape(row['question'])}</td></tr>"
        f"<tr><th>品牌提及</th><td>{escape(str(analysis.get('brand_mentioned', '不参与评分')))}</td></tr>"
        f"<tr><th>推荐位置</th><td>{escape(str(analysis.get('recommendation_position', '不参与评分')))}</td></tr>"
        f"<tr><th>延迟/Token</th><td>{row['latency_ms']} ms / {row['token_count']}</td></tr>"
        "</table>"
        f"<pre>{escape(answer)}</pre>"
        "</details>"
    )


def _parsed_source_row(response: dict, source: dict) -> str:
    url = source.get("url") or ""
    link = f'<a href="{escape(url)}" target="_blank" rel="noreferrer">{escape(_short(url, 72))}</a>' if url else ""
    return (
        "<tr>"
        f"<td>{escape(response['provider'])}</td>"
        f"<td>{escape(response['question_type'])}</td>"
        f"<td>{link}</td>"
        f"<td>{escape(source.get('category') or '')}</td>"
        f"<td>{escape(source.get('page_type') or '')}</td>"
        f"<td>{escape(_short(response['question'], 90))}</td>"
        "</tr>"
    )


def _payload_hash(payload: dict) -> str:
    stable_payload = {key: value for key, value in payload.items() if key not in {"generated_at", "sha256"}}
    raw = json.dumps(stable_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _short(text: str, length: int) -> str:
    text = str(text or "")
    return text if len(text) <= length else f"{text[: length - 3]}..."

from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path

from .models import AuditRequest
from .report.pdf import write_pdf_report
from .services.audit_service import AuditService


NIKE_REQUEST = AuditRequest(
    brand_name="Nike",
    website="https://www.nike.com",
    industry="运动服饰",
    products=["运动鞋", "运动服饰", "跑步装备"],
    competitors=["Adidas", "Puma", "Under Armour", "安踏", "李宁"],
    regions=["中国", "北京", "上海", "广州", "深圳", "成都"],
    question_count=60,
)


async def run_audit_sample(
    request: AuditRequest,
    output_dir: Path,
    providers: list[str] | None = None,
    question_count: int | None = None,
) -> None:
    service = AuditService()
    final_request = request.model_copy(
        update={
            "providers": providers or request.providers,
            "question_count": question_count if question_count is not None else request.question_count,
        }
    )
    record = await service.create_audit(final_request)
    if not record.result:
        raise RuntimeError(record.error or "audit failed")
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = _slug(record.result.input.brand_name)
    result_path = output_dir / f"{slug}-result.json"
    html_path = output_dir / f"{slug}-report.html"
    pdf_path = output_dir / f"{slug}-report.pdf"
    result_path.write_text(record.result.model_dump_json(indent=2), encoding="utf-8")
    html_path.write_text(record.result.report_html or "", encoding="utf-8")
    write_pdf_report(record.result, pdf_path)
    print(json.dumps({"audit_id": record.id, "score": record.result.score.total_score, "outputs": [str(result_path), str(html_path), str(pdf_path)]}, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Visibility China CLI")
    parser.add_argument("--nike", action="store_true", help="Run a complete Nike audit")
    parser.add_argument("--brand", help="Brand name to audit, for example: 美的")
    parser.add_argument("--website", help="Optional official website")
    parser.add_argument("--industry", default="", help="Optional industry")
    parser.add_argument("--products", help="Comma-separated products, optional")
    parser.add_argument("--competitors", help="Comma-separated competitors, optional")
    parser.add_argument("--deepseek", action="store_true", help="Shortcut for --providers deepseek --question-count 10")
    parser.add_argument("--providers", help="Comma-separated providers, for example: deepseek,kimi,qwen")
    parser.add_argument("--question-count", type=int, help="Override question count")
    parser.add_argument("--output-dir", default="outputs", help="Where to write reports")
    args = parser.parse_args()
    if args.nike:
        providers = _parse_providers(args.providers)
        if args.deepseek:
            providers = ["deepseek"]
        question_count = args.question_count or (10 if args.deepseek else None)
        asyncio.run(run_audit_sample(NIKE_REQUEST, Path(args.output_dir), providers=providers, question_count=question_count))
        return
    if args.brand:
        providers = _parse_providers(args.providers)
        if args.deepseek:
            providers = ["deepseek"]
        question_count = args.question_count or (10 if args.deepseek else None)
        request = AuditRequest(
            brand_name=args.brand,
            website=args.website or None,
            industry=args.industry,
            products=_parse_providers(args.products) or [],
            competitors=_parse_providers(args.competitors) or [],
        )
        asyncio.run(run_audit_sample(request, Path(args.output_dir), providers=providers, question_count=question_count))
        return
    parser.error("Use --brand 美的 or --nike")


def _parse_providers(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    return [item.strip() for item in raw.split(",") if item.strip()]


def _slug(value: str) -> str:
    normalized = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", value, flags=re.UNICODE).strip("-").lower()
    return normalized or "audit"


if __name__ == "__main__":
    main()

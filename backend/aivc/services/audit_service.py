from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from ..analysis.citation import summarize_citations
from ..analysis.geo_optimizer import (
    predict_recommendation_probability,
)
from ..analysis.recommendation import build_competitor_matrix, build_industry_benchmark_matrix
from ..analysis.scoring import compute_visibility_score
from ..analysis.visibility import analyze_brand_response
from ..config import load_dotenv
from ..models import AuditRecord, AuditRequest, AuditResult, BrandInput
from ..providers.base import ProviderRegistry
from ..providers.simulated import build_default_registry
from ..question_generation import generate_questions
from ..report.html import render_report_html
from .research_service import enrich_request
from .strategy_service import generate_personalized_strategy
from .web_research_service import collect_web_evidence


class AuditService:
    def __init__(self, registry: ProviderRegistry | None = None) -> None:
        load_dotenv()
        self.registry = registry or build_default_registry()
        self.records: dict[str, AuditRecord] = {}

    async def create_audit(self, request: AuditRequest) -> AuditRecord:
        audit_id = uuid4().hex
        record = AuditRecord(id=audit_id, status="running", request=request)
        self.records[audit_id] = record
        try:
            result = await self.run_audit(audit_id, request)
            record.status = "completed"
            record.result = result
        except Exception as exc:  # pragma: no cover - defensive API state
            record.status = "failed"
            record.error = str(exc)
        record.updated_at = datetime.now(timezone.utc)
        return record

    async def run_audit(self, audit_id: str, request: AuditRequest) -> AuditResult:
        brand, question_count, provider_names = await enrich_request(request, self.registry)
        web_evidence = await collect_web_evidence(brand)
        questions = generate_questions(brand, question_count)
        providers = self.registry.select(provider_names)
        query_tasks = [provider.query(question, brand) for question in questions for provider in providers]
        responses = await asyncio.gather(*query_tasks)
        analyses = [analyze_brand_response(response, brand) for response in responses]
        score = compute_visibility_score(analyses, responses, len(providers))
        citations = summarize_citations(responses)
        try:
            competitors = await build_industry_benchmark_matrix(brand, providers)
        except Exception:
            competitors = build_competitor_matrix(brand, questions, responses, analyses)
        content_gaps, geo_suggestions, tasks = await generate_personalized_strategy(
            brand, responses, analyses, score, providers, web_evidence
        )
        predictions = predict_recommendation_probability(score)
        result = AuditResult(
            audit_id=audit_id,
            input=brand,
            questions=questions,
            responses=responses,
            analyses=analyses,
            score=score,
            citations=citations,
            competitors=competitors,
            content_gaps=content_gaps,
            geo_suggestions=geo_suggestions,
            recommendation_predictions=predictions,
            tasks=tasks,
        )
        result.report_html = render_report_html(result)
        return result

    def get_audit(self, audit_id: str) -> AuditRecord | None:
        return self.records.get(audit_id)


default_service = AuditService()

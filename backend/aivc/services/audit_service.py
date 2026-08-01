from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from ..analysis.citation import summarize_citations
from ..analysis.geo_optimizer import (
    predict_recommendation_probability,
)
from ..analysis.recommendation import build_industry_benchmark_matrix
from ..analysis.scoring import apply_competitive_voice_score, compute_visibility_score
from ..analysis.visibility import analyze_brand_response
from ..config import load_dotenv
from ..models import AuditRecord, AuditRequest, AuditResult, BrandInput
from ..models import ProviderResponse, Question
from ..providers.base import ProviderClient, ProviderRegistry
from ..providers.simulated import build_default_registry
from ..question_generation import generate_citation_source_questions, generate_questions
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
        visibility_questions = generate_questions(brand, question_count)
        citation_questions = generate_citation_source_questions(brand, question_count)
        questions = [*visibility_questions, *citation_questions]
        providers = self.registry.select(provider_names)
        responses, provider_errors = await _query_providers(providers, questions, brand)
        if not responses:
            error_detail = "; ".join(f"{name}: {message}" for name, message in provider_errors.items())
            raise RuntimeError(f"All provider queries failed: {error_detail}")
        successful_provider_names = {response.provider for response in responses}
        successful_providers = [provider for provider in providers if provider.name in successful_provider_names]
        visibility_question_ids = {question.id for question in visibility_questions}
        visibility_responses = [response for response in responses if response.question_id in visibility_question_ids]
        analyses = [analyze_brand_response(response, brand) for response in visibility_responses]
        score = compute_visibility_score(analyses, visibility_responses, len(successful_providers))
        citations = summarize_citations(responses)
        try:
            competitors = await build_industry_benchmark_matrix(brand, successful_providers)
        except Exception:
            competitors = []
        score = apply_competitive_voice_score(score, brand.brand_name, competitors)
        content_gaps, geo_suggestions, tasks = await generate_personalized_strategy(
            brand, visibility_responses, analyses, score, successful_providers, web_evidence
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
            evidence_notes=web_evidence,
        )
        result.report_html = render_report_html(result)
        return result

    def get_audit(self, audit_id: str) -> AuditRecord | None:
        return self.records.get(audit_id)


default_service = AuditService()


async def _query_providers(
    providers: list[ProviderClient],
    questions: list[Question],
    brand: BrandInput,
) -> tuple[list[ProviderResponse], dict[str, str]]:
    jobs = [(provider, question) for question in questions for provider in providers]
    results = await asyncio.gather(
        *(provider.query(question, brand) for provider, question in jobs),
        return_exceptions=True,
    )
    responses: list[ProviderResponse] = []
    provider_errors: dict[str, str] = {}
    for (provider, _question), result in zip(jobs, results):
        if isinstance(result, Exception):
            provider_errors.setdefault(provider.name, str(result))
            continue
        responses.append(result)
    return responses, provider_errors

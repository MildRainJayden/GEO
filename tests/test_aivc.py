from __future__ import annotations

import asyncio
import os
import unittest

os.environ["AIVC_DISABLE_REAL_PROVIDERS"] = "1"
os.environ["AIVC_DISABLE_WEB_RESEARCH"] = "1"

from backend.aivc.cli import NIKE_REQUEST
from backend.aivc.analysis.scoring import apply_competitive_voice_score, compute_visibility_score
from backend.aivc.models import AuditRequest, BrandInput, BrandMentionAnalysis, CompetitorMetric, ProviderResponse, Question
from backend.aivc.providers.base import ProviderClient, ProviderRegistry
from backend.aivc.providers.simulated import ProviderProfile, SimulatedProvider
from backend.aivc.analysis.recommendation import build_industry_benchmark_matrix
from backend.aivc.services.research_service import enrich_request
from backend.aivc.question_generation import generate_questions
from backend.aivc.services.audit_service import AuditService


class AIVCTestCase(unittest.TestCase):
    def test_question_generation_reaches_requested_count(self) -> None:
        questions = generate_questions(NIKE_REQUEST, 60)
        self.assertEqual(len(questions), 60)
        self.assertEqual(len({q.text for q in questions}), 60)

    def test_nike_audit_end_to_end(self) -> None:
        async def run() -> None:
            service = AuditService()
            record = await service.create_audit(NIKE_REQUEST)
            self.assertEqual(record.status, "completed")
            self.assertIsNotNone(record.result)
            result = record.result
            assert result is not None
            self.assertEqual(len(result.questions), 60)
            self.assertEqual(len(result.responses), 60 * 5)
            self.assertGreater(result.score.total_score, 50)
            self.assertEqual(len(result.tasks), 30)
            self.assertTrue(result.geo_suggestions)
            self.assertIn("Nike", result.report_html or "")

        asyncio.run(run())

    def test_midea_empty_fields_are_enriched(self) -> None:
        async def run() -> None:
            service = AuditService()
            record = await service.create_audit(AuditRequest(brand_name="美的", providers=["deepseek"]))
            self.assertEqual(record.status, "completed")
            result = record.result
            assert result is not None
            self.assertTrue(result.input.website)
            self.assertTrue(result.input.industry)
            self.assertTrue(result.input.products)
            self.assertTrue(result.input.competitors)
            self.assertGreaterEqual(len(result.questions), 30)
            self.assertEqual(len(result.responses), len(result.questions))

        asyncio.run(run())

    def test_blank_website_and_provider_aliases_validate(self) -> None:
        request = AuditRequest(brand_name="美的", website="", industry="", providers="DeepSeek")
        self.assertIsNone(request.website)
        self.assertEqual(request.providers, ["DeepSeek"])
        self.assertEqual(str(AuditRequest(brand_name="美的", website="www.midea.com").website), "https://www.midea.com/")

        async def run() -> None:
            service = AuditService()
            record = await service.create_audit(request.model_copy(update={"question_count": 10}))
            self.assertEqual(record.status, "completed")
            result = record.result
            assert result is not None
            self.assertEqual({response.provider for response in result.responses}, {"deepseek"})

        asyncio.run(run())

    def test_small_sample_without_quality_signals_is_capped(self) -> None:
        analyses = [
            BrandMentionAnalysis(
                provider="deepseek",
                question_id=str(index),
                brand_mentioned=True,
                mention_count=1,
                recommendation_position="Top5",
                sentiment="积极",
                description_correct=True,
                industry_terms_covered=["家电"],
            )
            for index in range(10)
        ]
        responses = [
            ProviderResponse(
                provider="deepseek",
                model_version="test",
                question_id=str(index),
                question="美的怎么样",
                answer="美的是家电品牌。",
                latency_ms=1,
                token_count=10,
            )
            for index in range(10)
        ]
        score = compute_visibility_score(analyses, responses, provider_count=1)
        self.assertLess(score.total_score, 100)
        self.assertEqual(score.total_score, 82.0)

    def test_low_competitive_voice_reduces_total_score(self) -> None:
        analyses = [
            BrandMentionAnalysis(
                provider="deepseek",
                question_id=str(index),
                brand_mentioned=True,
                mention_count=1,
                recommendation_position="Top5",
                sentiment="积极",
                description_correct=True,
                industry_terms_covered=["家电"],
            )
            for index in range(60)
        ]
        responses = [
            ProviderResponse(
                provider="deepseek",
                model_version="test",
                question_id=str(index),
                question="长虹怎么样",
                answer="长虹是家电品牌。",
                latency_ms=1,
                token_count=10,
            )
            for index in range(60)
        ]
        score = compute_visibility_score(analyses, responses, provider_count=2)
        score.total_score = 92.0
        score.base_visibility_score = 92.0
        adjusted = apply_competitive_voice_score(
            score,
            "长虹",
            [
                CompetitorMetric(
                    brand="美的",
                    mention_rate=0.35,
                    top3_rate=1,
                    industry_coverage=1,
                    scenario_coverage=1,
                    citation_count=0,
                    accuracy_rate=1,
                    voice_share=0.35,
                    occurrence_rate=1,
                    average_rank=1,
                    effective_sample_count=5,
                    scenario_sample_count=1,
                ),
                CompetitorMetric(
                    brand="长虹",
                    mention_rate=0.05,
                    top3_rate=0,
                    industry_coverage=0.1,
                    scenario_coverage=0,
                    citation_count=0,
                    accuracy_rate=0.4,
                    voice_share=0.05,
                    occurrence_rate=0.4,
                    average_rank=6,
                    effective_sample_count=5,
                    scenario_sample_count=1,
                ),
            ],
        )
        self.assertEqual(adjusted.base_visibility_score, 92.0)
        self.assertLess(adjusted.total_score, 75.0)

    def test_provider_failure_does_not_fail_entire_audit(self) -> None:
        async def run() -> None:
            registry = ProviderRegistry()
            registry.register(SimulatedProvider(ProviderProfile("deepseek", "test-ok", 1.0, 0.0, 0.0)))
            registry.register(FailingProvider())
            service = AuditService(registry=registry)
            request = AuditRequest(
                brand_name="Nike",
                website="https://www.nike.com",
                industry="sportswear",
                products=["shoes"],
                competitors=["Adidas"],
                providers=["deepseek", "doubao"],
                question_count=10,
            )
            record = await service.create_audit(request)
            self.assertEqual(record.status, "completed")
            result = record.result
            assert result is not None
            self.assertEqual({response.provider for response in result.responses}, {"deepseek"})
            self.assertEqual(len(result.responses), len(result.questions))

        asyncio.run(run())

    def test_industry_benchmark_uses_neutral_brand_context(self) -> None:
        async def run() -> None:
            provider = EchoBrandProvider()
            brand = BrandInput(
                brand_name="美的",
                industry="家电制造",
                products=["空调"],
                competitors=["格力"],
            )
            await build_industry_benchmark_matrix(brand, [provider])
            self.assertTrue(all(name.startswith("候选品牌池：") for name in provider.seen_brand_names))
            self.assertNotEqual(provider.seen_brand_names[0], "美的")

        asyncio.run(run())

    def test_industry_benchmark_uses_relative_voice_share(self) -> None:
        async def run() -> None:
            provider = EchoBrandProvider()
            brand = BrandInput(
                brand_name="海信",
                industry="家电制造",
                products=["电视"],
                competitors=["海尔", "美的", "格力"],
            )
            matrix = await build_industry_benchmark_matrix(brand, [provider])
            share_sum = sum(item.mention_rate for item in matrix)
            self.assertAlmostEqual(share_sum, 1.0, places=2)
            self.assertLess(max(item.mention_rate for item in matrix), 1.0)

        asyncio.run(run())

    def test_home_appliance_industry_uses_concrete_competitors(self) -> None:
        async def run() -> None:
            service = AuditService()
            brand, _question_count, _providers = await enrich_request(
                AuditRequest(brand_name="海信", industry="家电制造", question_count=10, providers=["deepseek"]),
                service.registry,
            )
            self.assertNotIn("主要竞品", brand.competitors)
            self.assertNotIn("替代品牌", brand.competitors)
            self.assertNotIn("同类品牌", brand.competitors)
            self.assertNotIn("海信", brand.competitors)
            self.assertIn("海尔", brand.competitors)
            self.assertIn("美的", brand.competitors)

        asyncio.run(run())


class FailingProvider(ProviderClient):
    name = "doubao"
    model_version = "test-failing"

    async def query(self, question: Question, brand: BrandInput) -> ProviderResponse:
        raise RuntimeError("doubao test failure")


class EchoBrandProvider(ProviderClient):
    name = "echo"
    model_version = "test-echo"

    def __init__(self) -> None:
        self.seen_brand_names: list[str] = []

    async def query(self, question: Question, brand: BrandInput) -> ProviderResponse:
        self.seen_brand_names.append(brand.brand_name)
        return ProviderResponse(
            provider=self.name,
            model_version=self.model_version,
            question_id=question.id,
            question=question.text,
            answer="海信、美的、格力、海尔是家电制造行业常见品牌。",
            latency_ms=1,
            token_count=10,
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import asyncio
import os
import unittest

os.environ["AIVC_DISABLE_REAL_PROVIDERS"] = "1"
os.environ["AIVC_DISABLE_WEB_RESEARCH"] = "1"

from backend.aivc.cli import NIKE_REQUEST
from backend.aivc.analysis.scoring import compute_visibility_score
from backend.aivc.models import AuditRequest, BrandInput, BrandMentionAnalysis, ProviderResponse, Question
from backend.aivc.providers.base import ProviderClient, ProviderRegistry
from backend.aivc.providers.simulated import ProviderProfile, SimulatedProvider
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


class FailingProvider(ProviderClient):
    name = "doubao"
    model_version = "test-failing"

    async def query(self, question: Question, brand: BrandInput) -> ProviderResponse:
        raise RuntimeError("doubao test failure")


if __name__ == "__main__":
    unittest.main()

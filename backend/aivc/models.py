from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, HttpUrl, computed_field, field_validator


class QuestionType(str, Enum):
    BRAND = "brand"
    CATEGORY = "category"
    SCENARIO = "scenario"
    COMPARISON = "comparison"
    DECISION = "decision"
    CITATION_SOURCE = "citation_source"


class BrandInput(BaseModel):
    brand_name: str = Field(..., min_length=1, examples=["Nike"])
    website: HttpUrl | None = Field(default=None, examples=["https://www.nike.com"])
    industry: str = Field(default="", examples=["运动服饰"])
    products: list[str] = Field(default_factory=list, examples=[["运动鞋", "运动服饰", "跑步装备"]])
    competitors: list[str] = Field(default_factory=list, examples=[["Adidas", "Puma", "Under Armour"]])
    regions: list[str] = Field(default_factory=lambda: ["中国", "北京", "上海", "深圳"])

    @field_validator("website", mode="before")
    @classmethod
    def blank_website(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("www."):
                return f"https://{stripped}"
            if "." in stripped and "://" not in stripped:
                return f"https://{stripped}"
        return value

    @field_validator("industry", mode="before")
    @classmethod
    def blank_industry(cls, value: object) -> str:
        return "" if value is None else str(value).strip()

    @field_validator("products", "competitors", "regions", mode="before")
    @classmethod
    def clean_list(cls, value: object) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.replace("，", ",").split(",") if item.strip()]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    @computed_field
    @property
    def product_text(self) -> str:
        return "、".join(self.products) if self.products else self.industry or "核心产品"


class AuditRequest(BrandInput):
    question_count: int | None = Field(default=None, ge=10, le=200)
    providers: list[str] | None = None

    @field_validator("providers", mode="before")
    @classmethod
    def clean_providers(cls, value: object) -> list[str] | None:
        if value is None or value == "":
            return None
        if isinstance(value, str):
            items = [item.strip() for item in value.replace("，", ",").split(",") if item.strip()]
            return items or None
        if isinstance(value, list):
            items = [str(item).strip() for item in value if str(item).strip()]
            return items or None
        return None


class Question(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    text: str
    type: QuestionType
    region: str | None = None


class Citation(BaseModel):
    title: str
    url: str
    source_type: str
    authority: float = Field(ge=0, le=1)


class ProviderResponse(BaseModel):
    provider: str
    model_version: str
    question_id: str
    question: str
    answer: str
    latency_ms: int
    token_count: int
    citations: list[Citation] = Field(default_factory=list)
    web_enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BrandMentionAnalysis(BaseModel):
    provider: str
    question_id: str
    brand_mentioned: bool
    mention_count: int
    recommendation_position: Literal["Top1", "Top3", "Top5", "未推荐"]
    sentiment: Literal["积极", "中性", "消极"]
    description_correct: bool
    error_types: list[str] = Field(default_factory=list)
    industry_terms_covered: list[str] = Field(default_factory=list)


class PlatformScore(BaseModel):
    provider: str
    score: float
    mention_rate: float
    top3_rate: float
    accuracy_rate: float
    citation_quality: float
    explanation: str = ""


class ScoreBreakdown(BaseModel):
    total_score: float
    mention_rate_score: float
    top3_rate_score: float
    accuracy_score: float
    platform_coverage_score: float
    citation_quality_score: float
    industry_coverage_score: float
    competitive_voice_score: float = 0.0
    base_visibility_score: float = 0.0
    platform_scores: list[PlatformScore]
    platform_weights: dict[str, float] = Field(default_factory=dict)
    platform_weight_basis: dict[str, float] = Field(default_factory=dict)
    trend_score: float


class CitationSummary(BaseModel):
    source_type: str
    count: int
    share: float
    authority: float


class CompetitorMetric(BaseModel):
    brand: str
    mention_rate: float
    top3_rate: float
    industry_coverage: float
    scenario_coverage: float
    citation_count: int
    accuracy_rate: float
    voice_share: float = 0.0
    occurrence_rate: float = 0.0
    average_rank: float | None = None
    effective_sample_count: int = 0
    scenario_sample_count: int = 0


class ContentGap(BaseModel):
    question: str
    reason: str
    recommendation_type: Literal["FAQ", "博客", "案例", "产品页面", "对比文章"]
    priority: Literal["高", "中", "低"]


class GeoSuggestion(BaseModel):
    category: str
    title: str
    action: str
    copyable_content: str
    expected_impact: float


class RecommendationPrediction(BaseModel):
    provider: str
    probability: float
    reasons: list[str]


class TaskItem(BaseModel):
    day: int
    title: str
    channel: str
    status: Literal["todo", "doing", "done"] = "todo"
    expected_score_lift: float
    prompt_template: str = ""


class AuditResult(BaseModel):
    audit_id: str
    input: BrandInput
    questions: list[Question]
    responses: list[ProviderResponse]
    analyses: list[BrandMentionAnalysis]
    score: ScoreBreakdown
    citations: list[CitationSummary]
    competitors: list[CompetitorMetric]
    content_gaps: list[ContentGap]
    geo_suggestions: list[GeoSuggestion]
    recommendation_predictions: list[RecommendationPrediction]
    tasks: list[TaskItem]
    evidence_notes: list[str] = Field(default_factory=list)
    report_html: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AuditRecord(BaseModel):
    id: str
    status: Literal["queued", "running", "completed", "failed"]
    request: AuditRequest
    result: AuditResult | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

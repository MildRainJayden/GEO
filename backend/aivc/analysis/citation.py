from __future__ import annotations

from collections import defaultdict

from ..models import CitationSummary, ProviderResponse


def summarize_citations(responses: list[ProviderResponse]) -> list[CitationSummary]:
    counts: dict[str, int] = defaultdict(int)
    authority_totals: dict[str, float] = defaultdict(float)
    for response in responses:
        for citation in response.citations:
            counts[citation.source_type] += 1
            authority_totals[citation.source_type] += citation.authority

    total = sum(counts.values()) or 1
    summaries = [
        CitationSummary(
            source_type=source_type,
            count=count,
            share=round(count / total, 4),
            authority=round(authority_totals[source_type] / count, 3),
        )
        for source_type, count in counts.items()
    ]
    return sorted(summaries, key=lambda item: (-item.count, item.source_type))

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from urllib.parse import urlparse

from ..models import AuditResult


URL_PATTERN = re.compile(r"https?://[^\s<>)\"'`，。；、（）]+", re.I)
BARE_DOMAIN_PATTERN = re.compile(r"(?<!@)\b(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+\b", re.I)
KNOWN_SOURCE_NAMES = {
    "国家企业信用信息公示系统": ("www.gsxt.gov.cn", "权威机构", "查询页面"),
    "中国能效标识网": ("www.energylabel.com.cn", "权威机构", "查询页面"),
    "市场监督管理局": ("www.samr.gov.cn", "权威机构", "查询页面"),
    "工信部": ("www.miit.gov.cn", "权威机构", "政策/公告页"),
    "京东": ("jd.com", "电商平台", "商品/评价页"),
    "天猫": ("tmall.com", "电商平台", "商品/评价页"),
    "淘宝": ("taobao.com", "电商平台", "商品/评价页"),
    "苏宁": ("suning.com", "电商平台", "商品/评价页"),
    "知乎": ("zhihu.com", "社媒/社区", "问答页"),
    "小红书": ("xiaohongshu.com", "社媒/社区", "内容页"),
    "微博": ("weibo.com", "社媒/社区", "内容页"),
    "抖音": ("douyin.com", "社媒/社区", "视频页"),
    "哔哩哔哩": ("bilibili.com", "社媒/社区", "视频页"),
    "B站": ("bilibili.com", "社媒/社区", "视频页"),
    "百度百科": ("baike.baidu.com", "百科", "百科页"),
    "维基百科": ("wikipedia.org", "百科", "百科页"),
    "新浪": ("sina.com.cn", "新闻媒体", "文章/新闻"),
    "腾讯新闻": ("news.qq.com", "新闻媒体", "文章/新闻"),
    "网易": ("163.com", "新闻媒体", "文章/新闻"),
    "搜狐": ("sohu.com", "新闻媒体", "文章/新闻"),
}
OFFICIAL_HINTS = ("官网", "官方网站", "官方商城", "官方旗舰店")


@dataclass(frozen=True)
class CitationRecord:
    title: str
    url: str
    domain: str
    category: str
    page_type: str
    provider: str
    question_id: str


@dataclass(frozen=True)
class ProviderCitationInsights:
    provider: str
    total: int
    unique_domains: int
    brand_citation_share: float
    categories: list[tuple[str, int]]
    page_types: list[tuple[str, int]]
    domains: list[tuple[str, int]]
    urls: list[tuple[str, int]]


@dataclass(frozen=True)
class CitationInsights:
    total: int
    unique_domains: int
    brand_citation_share: float
    categories: list[tuple[str, int]]
    page_types: list[tuple[str, int]]
    domains: list[tuple[str, int]]
    urls: list[tuple[str, int]]
    providers: list[ProviderCitationInsights]


def build_citation_insights(result: AuditResult) -> CitationInsights:
    records = _citation_records(result)
    brand_domain = _domain(str(result.input.website or ""))
    provider_records: dict[str, list[CitationRecord]] = defaultdict(list)
    for record in records:
        provider_records[record.provider].append(record)
    aggregate = _summarize_records(records, brand_domain)
    return CitationInsights(
        total=aggregate.total,
        unique_domains=aggregate.unique_domains,
        brand_citation_share=aggregate.brand_citation_share,
        categories=aggregate.categories,
        page_types=aggregate.page_types,
        domains=aggregate.domains,
        urls=aggregate.urls,
        providers=[
            _summarize_records(items, brand_domain, provider=provider)
            for provider, items in sorted(provider_records.items())
        ],
    )


def _summarize_records(
    records: list[CitationRecord],
    brand_domain: str,
    provider: str = "综合",
) -> ProviderCitationInsights:
    total = len(records)
    brand_hits = sum(1 for record in records if brand_domain and record.domain == brand_domain)
    categories = Counter(record.category for record in records)
    page_types = Counter(record.page_type for record in records)
    domains = Counter(record.domain for record in records if record.domain)
    urls = Counter(record.url for record in records if record.url)
    return ProviderCitationInsights(
        provider=provider,
        total=total,
        unique_domains=len(domains),
        brand_citation_share=brand_hits / total if total else 0.0,
        categories=_top_counts(categories, 8),
        page_types=_top_counts(page_types, 8),
        domains=_top_counts(domains, 10),
        urls=_top_counts(urls, 10),
    )


def _citation_records(result: AuditResult) -> list[CitationRecord]:
    records: list[CitationRecord] = []
    brand_url = _clean_url(str(result.input.website or ""))
    brand_domain = _domain(brand_url)
    for response in result.responses:
        seen_in_response: set[tuple[str, str]] = set()
        for citation in response.citations:
            url = _clean_url(citation.url)
            domain = _domain(url)
            key = ("url", url.lower())
            if not url or key in seen_in_response:
                continue
            seen_in_response.add(key)
            records.append(
                CitationRecord(
                    title=citation.title or domain or "引用来源",
                    url=url,
                    domain=domain,
                    category=_normalize_category(citation.source_type, domain),
                    page_type=_page_type(url, citation.title),
                    provider=response.provider,
                    question_id=response.question_id,
                )
            )

        answer = response.answer or ""
        for url in URL_PATTERN.findall(answer):
            _append_url_record(records, seen_in_response, response.provider, response.question_id, _clean_url(url))
        answer_without_urls = URL_PATTERN.sub(" ", answer)
        for domain in BARE_DOMAIN_PATTERN.findall(answer_without_urls):
            if _looks_like_domain(domain):
                _append_url_record(records, seen_in_response, response.provider, response.question_id, f"https://{domain}")
        for name, (domain, category, page_type) in KNOWN_SOURCE_NAMES.items():
            if name in answer and not _seen_domain(seen_in_response, domain):
                seen_in_response.add(("name", domain))
                records.append(
                    CitationRecord(
                        title=name,
                        url=f"https://{domain}",
                        domain=_domain(domain),
                        category=category,
                        page_type=page_type,
                        provider=response.provider,
                        question_id=response.question_id,
                    )
                )
        if (
            brand_domain
            and any(hint in answer for hint in OFFICIAL_HINTS)
            and not _seen_domain(seen_in_response, brand_domain)
        ):
            seen_in_response.add(("official", brand_domain))
            records.append(
                CitationRecord(
                    title=f"{result.input.brand_name}官网",
                    url=brand_url,
                    domain=brand_domain,
                    category="品牌官网",
                    page_type=_page_type(brand_url, "官网"),
                    provider=response.provider,
                    question_id=response.question_id,
                )
            )
    return records


def _append_url_record(
    records: list[CitationRecord],
    seen_in_response: set[tuple[str, str]],
    provider: str,
    question_id: str,
    url: str,
) -> None:
    domain = _domain(url)
    key = ("url", url.lower())
    if not url or (domain and not _looks_like_domain(domain)) or key in seen_in_response:
        return
    seen_in_response.add(key)
    records.append(
        CitationRecord(
            title=domain or url,
            url=url,
            domain=domain,
            category=_category_from_domain(domain),
            page_type=_page_type(url, ""),
            provider=provider,
            question_id=question_id,
        )
    )


def _seen_domain(seen_in_response: set[tuple[str, str]], domain: str) -> bool:
    normalized = _domain(domain)
    for key_type, value in seen_in_response:
        if key_type == "official" and value == normalized:
            return True
        if _domain(value) == normalized:
            return True
    return False


def _top_counts(counter: Counter[str], limit: int) -> list[tuple[str, int]]:
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit]


def _clean_url(url: str) -> str:
    text = str(url or "").strip().strip("`").rstrip(".,;，。；)`")
    text = re.split(r"[`，。；、（）\s]", text, maxsplit=1)[0]
    try:
        parsed = urlparse(text if "://" in text else f"https://{text}") if text else None
    except ValueError:
        return ""
    if parsed and parsed.scheme in {"http", "https"} and parsed.netloc and parsed.path in {"", "/"} and not parsed.query:
        return f"{parsed.scheme}://{parsed.netloc.lower()}"
    return text


def _domain(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
    except ValueError:
        return ""
    host = (parsed.netloc or parsed.path.split("/")[0]).lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _looks_like_domain(value: str) -> bool:
    domain = _domain(value)
    if not domain or "." not in domain:
        return False
    if re.fullmatch(r"\d+\.[a-z]{2,4}", domain):
        return False
    return not domain.endswith((".py", ".js", ".css", ".json"))


def _normalize_category(source_type: str, domain: str) -> str:
    text = str(source_type or "").strip()
    if any(token in text for token in ["官网", "官方"]):
        return "品牌官网"
    if any(token in text for token in ["电商", "京东", "天猫", "淘宝", "苏宁"]):
        return "电商平台"
    if any(token in text for token in ["知乎", "小红书", "微博", "社媒", "社区", "抖音", "B站"]):
        return "社媒/社区"
    if any(token in text for token in ["新闻", "媒体", "文章"]):
        return "新闻媒体"
    if any(token in text for token in ["百科", "wiki"]):
        return "百科"
    if any(token in text for token in ["权威", "监管", "机构", "认证"]):
        return "权威机构"
    return text or _category_from_domain(domain)


def _category_from_domain(domain: str) -> str:
    if not domain:
        return "其他"
    if any(token in domain for token in ["gov", "edu", "org", "energylabel", "miit", "samr"]):
        return "权威机构"
    if any(token in domain for token in ["zhihu", "xiaohongshu", "weibo", "bilibili", "douyin"]):
        return "社媒/社区"
    if any(token in domain for token in ["jd", "tmall", "taobao", "amazon", "suning"]):
        return "电商平台"
    if any(token in domain for token in ["wikipedia", "baike", "wiki"]):
        return "百科"
    return "网站/媒体"


def _page_type(url: str, title: str) -> str:
    text = f"{url} {title}".lower()
    if any(token in text for token in ["product", "item", "goods", "detail", "产品", "商品"]):
        return "产品页"
    if any(token in text for token in ["news", "article", "post", "blog", "新闻", "文章", "资讯"]):
        return "文章/新闻"
    if any(token in text for token in ["faq", "help", "support", "service", "服务", "帮助", "售后"]):
        return "帮助/FAQ"
    if any(token in text for token in ["review", "compare", "vs", "评测", "对比", "评价"]):
        return "评测/对比"
    if any(token in text for token in ["search", "s?"]):
        return "搜索结果页"
    if any(token in text for token in ["gov", "energylabel", "认证", "查询", "监管"]):
        return "查询页面"
    path = urlparse(url).path.strip("/")
    if not path:
        return "首页"
    return "普通页面"

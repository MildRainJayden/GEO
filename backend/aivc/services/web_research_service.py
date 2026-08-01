from __future__ import annotations

import asyncio
import os
import re
from html import unescape
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..models import BrandInput


async def collect_web_evidence(brand: BrandInput) -> list[str]:
    """Collect lightweight public evidence for strategy prompts.

    This intentionally starts with the official site because generic search
    crawling needs a search API key to be reliable in production.
    """
    if os.environ.get("AIVC_DISABLE_WEB_RESEARCH") == "1" or not brand.website:
        return []
    return await asyncio.to_thread(_fetch_official_site, str(brand.website))


def _fetch_official_site(url: str) -> list[str]:
    request = Request(
        url,
        headers={
            "User-Agent": "AIVC/0.1 (+https://local.aivc)",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    try:
        with urlopen(request, timeout=8) as response:
            content_type = response.headers.get("Content-Type", "")
            if "html" not in content_type:
                return []
            raw = response.read(500_000).decode("utf-8", errors="ignore")
    except (HTTPError, URLError, TimeoutError, ValueError):
        return []

    title = _first_match(r"<title[^>]*>(.*?)</title>", raw)
    description = _meta_content(raw, "description")
    keywords = _meta_content(raw, "keywords")
    text = _clean_html(raw)
    snippets = [
        f"官网标题：{title}" if title else "",
        f"官网描述：{description}" if description else "",
        f"官网关键词：{keywords}" if keywords else "",
        f"官网正文摘要：{text[:900]}" if text else "",
    ]
    return [snippet for snippet in snippets if snippet]


def _first_match(pattern: str, text: str) -> str:
    match = re.search(pattern, text, re.I | re.S)
    return _clean_text(match.group(1)) if match else ""


def _meta_content(html: str, name: str) -> str:
    pattern = rf'<meta[^>]+name=["\']{re.escape(name)}["\'][^>]+content=["\'](.*?)["\']'
    value = _first_match(pattern, html)
    if value:
        return value
    pattern = rf'<meta[^>]+content=["\'](.*?)["\'][^>]+name=["\']{re.escape(name)}["\']'
    return _first_match(pattern, html)


def _clean_html(html: str) -> str:
    html = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    html = re.sub(r"<style[\s\S]*?</style>", " ", html, flags=re.I)
    html = re.sub(r"<[^>]+>", " ", html)
    return _clean_text(html)


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(text)).strip()
